"""From a timestamped transcript to what Lexa said, crypto by crypto.

    transcript -> cleaning -> cryptos named -> passages per crypto
               -> local model reads each crypto's passages (context, not numbers)
               -> verifier ties every value back to the transcript
               -> ExtractionResult

The model runs on this machine (Ollama): the subscriber's content never leaves
it. The model only proposes. The verifier decides, deterministically:

  - a price must be written in the passage at the cited timestamp (or be found
    elsewhere in that crypto's passages, and the timestamp is then corrected);
    otherwise it is rejected and never reaches the plan;
  - the evidence kept is always the transcript's own words, never the model's;
  - an allocation, a timeframe or a date the passage does not contain is
    removed and reported as ambiguous;
  - a crypto with nothing verified gets no sheet.

The prompt carries no reference values: the model is never told what to find.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..logging_setup import get_logger
from .schema import (
    CONFIDENCE_BY_BASIS,
    Argument,
    AssetAnalysis,
    Claim,
    Condition,
    Event,
    Evidence,
    ExtractionResult,
    Level,
    Rejected,
    Scenario,
    TranscriptInfo,
    VideoInfo,
)
from .transcript import (
    Segment,
    format_ts,
    mentions,
    near,
    numbers_in,
    quote_matches,
    render,
    same_value,
    topic_windows,
    value_in,
)

log = get_logger(__name__)

DEFAULT_MODEL = "gemma3:12b"
OLLAMA_URL = "http://127.0.0.1:11434"
CHUNK_CHARS = 12_000

SYSTEM_PROMPT = """Tu lis la transcription horodatée d'une vidéo d'analyse crypto en français.
Tu n'analyses PAS le marché toi-même : tu rapportes uniquement ce que dit l'auteur de la vidéo.

Règles absolues :
- N'écris jamais une valeur qui n'apparaît pas écrite dans la transcription.
- Pour chaque élément, donne l'horodatage [mm:ss] du passage et une citation copiée mot pour mot (30 mots maximum).
- Classe chaque niveau selon le CONTEXTE, pas selon le nombre seul :
  « si le prix revient vers X, ça redevient intéressant »  -> BUY_ZONE (INFERRED si le mot achat/acheter n'est pas dit)
  « j'achète / je rentre / j'accumule vers X »            -> BUY_ZONE (EXPLICIT)
  « je renforce / deuxième entrée vers Y »                 -> REINFORCEMENT
  « la cassure de X serait mauvaise »                      -> SUPPORT ou INVALIDATION, JAMAIS BUY_ZONE
  « il faut clôturer au-dessus de X en 4h »                -> CONFIRMATION, condition CLOSE_ABOVE, timeframe 4H
  « objectif / cible / TP vers Z »                         -> TARGET
  « sous W le scénario est invalidé »                      -> INVALIDATION
- basis = EXPLICIT si c'est dit clairement, INFERRED si tu le déduis du contexte, UNKNOWN si tu ne peux pas savoir.
- allocation_pct : uniquement si un pourcentage du capital ou de la position est dit pour ce niveau, même dans une phrase séparée
  (« 30 % sur la première zone et 70 % sur la deuxième » -> 30 pour la première zone d'achat, 70 pour la deuxième). Sinon null.
  Pour un objectif, le pourcentage de la position vendue à ce niveau, s'il est dit. Sinon null.
- timeframe (15M, 1H, 4H, 1D, 1W, LONG_TERM) : uniquement si c'est dit. Sinon null.
- Plusieurs scénarios conditionnels (cassure / rejet / retour sur support) : décris-les séparément dans "scenarios", ne les fusionne pas.
- direction d'un argument : uniquement si l'auteur la donne. Sinon null.
- Date d'un événement : uniquement telle que dite. Sinon null.
- En cas de doute, mets l'élément dans "ambiguous" au lieu de deviner.

Réponds uniquement avec un objet JSON de cette forme :
{
  "analysed": true,
  "price_at_video": {"value": null, "timestamp": "mm:ss", "quote": ""},
  "stance": "WAIT | BUY | SELL | NEUTRAL | UNSPECIFIED",
  "stance_basis": "EXPLICIT | INFERRED | UNKNOWN",
  "situation": [{"text": "", "basis": "", "timestamp": "mm:ss", "quote": ""}],
  "levels": [{"value": 0, "kind": "SUPPORT | RESISTANCE | BUY_ZONE | REINFORCEMENT | CONFIRMATION | INVALIDATION | TARGET | TAKE_PROFIT | OTHER",
              "role": "", "basis": "", "timeframe": null,
              "condition": {"kind": "BREAKOUT | CLOSE_ABOVE | CLOSE_BELOW | RETEST | VOLUME | HOLD_ABOVE | HOLD_BELOW | OTHER | UNKNOWN", "text": ""},
              "allocation_pct": null, "reasoning": "", "timestamp": "mm:ss", "quote": ""}],
  "scenarios": [{"id": "A", "condition": "", "direction": "UP | DOWN | RANGE | null", "levels": [], "targets": [], "invalidation": null, "timestamp": "mm:ss", "quote": ""}],
  "arguments": [{"indicator": "STRUCTURE | VOLUME | RSI | BOLLINGER | LIQUIDITY | BTC_DOMINANCE | USDT_DOMINANCE | WHALES | OPEN_INTEREST | FUNDING | ETF | FED | DOLLAR | OIL | OTHER",
                 "argument": "", "direction": null, "timestamp": "mm:ss", "quote": ""}],
  "events": [{"event": "", "date": null, "comment": "", "timestamp": "mm:ss", "quote": ""}],
  "reasoning": ["3 à 6 points résumant le raisonnement de l'auteur"],
  "ambiguous": ["passages dont le sens n'est pas clair"]
}
Si la crypto est seulement citée sans être analysée, réponds {"analysed": false}."""


def _user_prompt(symbol: str, passages: str) -> str:
    return (
        f"Crypto concernée : {symbol}\n"
        f"Passages de la vidéo où {symbol} est le sujet :\n\n{passages}\n\n"
        f"Extrais ce que l'auteur dit de {symbol}."
    )


def _chunks(segments: list[Segment]) -> list[list[Segment]]:
    out: list[list[Segment]] = [[]]
    size = 0
    for seg in segments:
        if size + len(seg.text) > CHUNK_CHARS and out[-1]:
            out.append(out[-1][-3:])  # a little overlap keeps sentences whole
            size = sum(len(s.text) for s in out[-1])
        out[-1].append(seg)
        size += len(seg.text) + 10
    return out


def call_ollama(system: str, user: str, model: str = DEFAULT_MODEL,
                base_url: str = OLLAMA_URL, timeout: float = 900) -> dict[str, Any]:
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 4096},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    last_error: Exception | None = None
    for attempt in range(3):
        if attempt:
            # A malformed answer is asked again, never patched by guesswork.
            payload["options"]["seed"] = attempt
            payload["options"]["temperature"] = 0.1 * attempt
        response = httpx.post(f"{base_url}/api/chat", json=payload, timeout=timeout)
        response.raise_for_status()
        content = (response.json().get("message") or {}).get("content", "")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(data, dict):
            return data
    raise ValueError(f"réponse JSON invalide après 3 essais ({last_error})")


# --- verification ------------------------------------------------------------------

_TIMEFRAME_WORDS = {
    "15M": r"15 ?(min|minutes|m\b)",
    "1H": r"\b(1 ?h|h1|une heure|horaire)\b",
    "4H": r"\b(4 ?h|h4|quatre heures)\b",
    "1D": r"\b(daily|journali\w+|1 ?d|d1|jour)\b",
    "1W": r"\b(weekly|hebdo\w*|semaine|1 ?w)\b",
    "LONG_TERM": r"(long terme|mensuel|monthly)",
}
_BUY_WORDS = r"(achat|achet|acheter|entr|accumul|renforc|int[ée]ressant|position)"
_BREAK_WORDS = r"(cassure|casser|casse|perd|perte|sous |en dessous|clôtur\w* sous)"


def _ts(value: Any) -> int | None:
    if isinstance(value, int | float):
        return int(value)
    if not isinstance(value, str):
        return None
    m = re.search(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})", value)
    if not m:
        return None
    h, mnt, s = m.groups()
    return int(h or 0) * 3600 + int(mnt) * 60 + int(s)


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        found = numbers_in(value)
        return found[0] if len(found) == 1 else None
    return None


def _text(segs: list[Segment]) -> str:
    return " ".join(s.text for s in segs)


def _locate_value(value: float, ts: int | None, window: list[Segment],
                  everything: list[Segment]) -> tuple[Evidence | None, str]:
    """The passage that really contains the value, nearest the cited time."""

    around = near(window, ts) or near(everything, ts)
    hits = [s for s in around if value_in(value, s.text)]
    note = ""
    if not hits:
        hits = [s for s in window if value_in(value, s.text)]
        if hits and ts is not None:
            hits.sort(key=lambda s: abs(s.start_s - ts))
            note = f"Horodatage corrigé : la valeur est dite à {format_ts(hits[0].start_s)}."
    if not hits:
        return None, ""
    seg = hits[0] if ts is None else min(hits, key=lambda s: abs(s.start_s - ts))
    return Evidence(timestamp_s=seg.start_s, quote=seg.text, verified=True,
                    verification_note=note), note


def _locate_quote(quote: str, ts: int | None, window: list[Segment],
                  everything: list[Segment]) -> Evidence | None:
    """A non-numeric claim is kept only if its quote is found in the transcript."""

    if not quote.strip():
        return None
    for pool in (near(window, ts), near(everything, ts), window):
        # One passage first, nearest the cited time; then two in a row.
        ordered = sorted(pool, key=lambda s: abs(s.start_s - ts)) if ts is not None else pool
        for seg in ordered:
            if quote_matches(quote, seg.text):
                return Evidence(timestamp_s=seg.start_s, quote=seg.text, verified=True)
        for i, seg in enumerate(pool):
            joined = " ".join(s.text for s in pool[i:i + 2])
            if quote_matches(quote, joined):
                return Evidence(timestamp_s=seg.start_s, quote=joined, verified=True)
    return None


def _allocation(level: dict, evidence: Evidence, window: list[Segment]) -> tuple[float | None, str]:
    pct = _num(level.get("allocation_pct"))
    if pct is None:
        return None, ""
    passage = _text(near(window, evidence.timestamp_s, 90)) or evidence.quote
    pattern = rf"{re.escape(format(pct, 'g')).replace('.', '[.,]')}\s*(%|pour ?cent)"
    if re.search(pattern, passage, re.I):
        return pct, ""
    return None, f"Allocation de {format(pct, 'g')} % proposée par le modèle mais absente de la transcription : retirée."


def _timeframe(value: Any, evidence: Evidence, window: list[Segment]) -> tuple[str | None, str]:
    if value not in _TIMEFRAME_WORDS:
        return None, ""
    passage = _text(near(window, evidence.timestamp_s, 60)) or evidence.quote
    if re.search(_TIMEFRAME_WORDS[value], passage, re.I):
        return value, ""
    return None, f"Unité de temps {value} non retrouvée dans le passage : retirée."


def _basis(value: Any) -> str:
    return value if value in ("EXPLICIT", "INFERRED", "UNKNOWN") else "UNKNOWN"


def _choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if value in allowed else default


def verify_asset(symbol: str, raw: dict[str, Any], window: list[Segment],
                 everything: list[Segment]) -> AssetAnalysis:
    out = AssetAnalysis(symbol=symbol)

    # Price at the time of the video.
    price = raw.get("price_at_video") or {}
    if isinstance(price, dict) and (value := _num(price.get("value"))) is not None:
        evidence, _ = _locate_value(value, _ts(price.get("timestamp")), window, everything)
        if evidence:
            out.price_at_video, out.price_at_video_evidence = value, evidence
        else:
            out.rejected.append(Rejected(what="Prix pendant la vidéo", value=value,
                                         reason="Valeur introuvable dans la transcription."))

    out.stance = _choice(raw.get("stance"), ("WAIT", "BUY", "SELL", "NEUTRAL", "UNSPECIFIED"),
                         "UNSPECIFIED")
    out.stance_basis = _basis(raw.get("stance_basis"))
    if out.stance_basis == "UNKNOWN":
        out.stance = "UNSPECIFIED"

    for item in raw.get("situation") or []:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        evidence = _locate_quote(str(item.get("quote", "")), _ts(item.get("timestamp")),
                                 window, everything)
        if evidence:
            out.situation.append(Claim(text=str(item["text"]), basis=_basis(item.get("basis")),
                                       evidence=evidence))
        else:
            out.ambiguous.append(f"Situation non rattachée à un passage : « {item['text']} »")

    seen: set[tuple[str, float]] = set()
    for item in raw.get("levels") or []:
        if not isinstance(item, dict):
            continue
        value = _num(item.get("value"))
        kind = _choice(item.get("kind"), ("SUPPORT", "RESISTANCE", "BUY_ZONE", "REINFORCEMENT",
                                          "CONFIRMATION", "INVALIDATION", "TARGET",
                                          "TAKE_PROFIT", "OTHER"), "OTHER")
        ts = _ts(item.get("timestamp"))
        if value is None or value <= 0:
            continue
        evidence, _ = _locate_value(value, ts, window, everything)
        if evidence is None:
            out.rejected.append(Rejected(what=f"Niveau {kind}", value=value, timestamp_s=ts,
                                         reason="Valeur introuvable dans la transcription."))
            continue
        if (kind, value) in seen:
            continue
        seen.add((kind, value))
        basis = _basis(item.get("basis"))
        passage = _text(near(window, evidence.timestamp_s, 20)) or evidence.quote
        if kind in ("BUY_ZONE", "REINFORCEMENT") and re.search(_BREAK_WORDS, passage, re.I) \
                and not re.search(_BUY_WORDS, passage, re.I):
            out.ambiguous.append(
                f"{format(value, 'g')} classé {kind}, mais le passage parle de cassure sans parler "
                f"d'achat ({format_ts(evidence.timestamp_s)}) : à vérifier.")
            basis = "INFERRED" if basis == "EXPLICIT" else basis
        allocation, note_a = _allocation(item, evidence, window)
        timeframe, note_t = _timeframe(item.get("timeframe"), evidence, window)
        for note in (note_a, note_t):
            if note:
                out.ambiguous.append(f"{format(value, 'g')} : {note}")
        cond = item.get("condition") if isinstance(item.get("condition"), dict) else {}
        out.levels.append(Level(
            value=value, kind=kind, role=str(item.get("role") or ""), basis=basis,
            confidence=CONFIDENCE_BY_BASIS[basis], timeframe=timeframe,
            condition=Condition(
                kind=_choice(cond.get("kind"), ("BREAKOUT", "CLOSE_ABOVE", "CLOSE_BELOW",
                                                "RETEST", "VOLUME", "HOLD_ABOVE", "HOLD_BELOW",
                                                "OTHER", "UNKNOWN"), "UNKNOWN"),
                timeframe=timeframe, text=str(cond.get("text") or "")),
            allocation_pct=allocation,
            allocation_basis="EXPLICIT" if allocation is not None else "UNKNOWN",
            allocation_evidence=evidence if allocation is not None else None,
            reasoning=str(item.get("reasoning") or ""),
            evidence=evidence,
        ))

    window_text = _text(window)
    for n, item in enumerate(raw.get("scenarios") or []):
        if not isinstance(item, dict) or not item.get("condition"):
            continue
        evidence = _locate_quote(str(item.get("quote", "")), _ts(item.get("timestamp")),
                                 window, everything)
        values = {key: [v for v in (_num(x) for x in (item.get(key) or [])) if v is not None]
                  for key in ("levels", "targets")}
        missing = [v for vs in values.values() for v in vs if not value_in(v, window_text)]
        for v in missing:
            out.rejected.append(Rejected(what=f"Valeur du scénario {item.get('id') or n + 1}",
                                         value=v, reason="Introuvable dans la transcription."))
        invalidation = _num(item.get("invalidation"))
        if invalidation is not None and not value_in(invalidation, window_text):
            out.rejected.append(Rejected(what="Invalidation de scénario", value=invalidation,
                                         reason="Introuvable dans la transcription."))
            invalidation = None
        if evidence is None:
            out.ambiguous.append(f"Scénario non rattaché à un passage : « {item['condition']} »")
            continue
        direction = item.get("direction") if item.get("direction") in ("UP", "DOWN", "RANGE") else None
        out.scenarios.append(Scenario(
            scenario_id=str(item.get("id") or chr(65 + n)), condition=str(item["condition"]),
            direction=direction,
            level_values=[v for v in values["levels"] if v not in missing],
            targets=[v for v in values["targets"] if v not in missing],
            invalidation=invalidation, evidence=evidence,
        ))

    for item in raw.get("arguments") or []:
        if not isinstance(item, dict) or not item.get("argument"):
            continue
        evidence = _locate_quote(str(item.get("quote", "")), _ts(item.get("timestamp")),
                                 window, everything)
        if evidence is None:
            out.ambiguous.append(f"Argument non rattaché à un passage : « {item['argument']} »")
            continue
        direction = item.get("direction") if item.get("direction") in ("BULLISH", "BEARISH", "NEUTRAL") else None
        out.arguments.append(Argument(indicator=str(item.get("indicator") or "OTHER"),
                                      argument=str(item["argument"]), direction=direction,
                                      evidence=evidence))

    for item in raw.get("events") or []:
        if not isinstance(item, dict) or not item.get("event"):
            continue
        evidence = _locate_quote(str(item.get("quote", "")), _ts(item.get("timestamp")),
                                 window, everything)
        if evidence is None:
            out.ambiguous.append(f"Événement non rattaché à un passage : « {item['event']} »")
            continue
        date = item.get("date")
        passage = _text(near(everything, evidence.timestamp_s, 60))
        if date and not all(tok.lower() in passage.lower()
                            for tok in re.findall(r"\w{3,}|\d+", str(date))):
            out.ambiguous.append(f"Date « {date} » de l'événement {item['event']} non retrouvée : retirée.")
            date = None
        out.events.append(Event(event=str(item["event"]), date=date, asset=symbol,
                                comment=str(item.get("comment") or ""), evidence=evidence))

    out.reasoning = [str(r) for r in (raw.get("reasoning") or []) if str(r).strip()][:6]
    out.ambiguous.extend(str(a) for a in (raw.get("ambiguous") or []) if str(a).strip())
    return out


_PCT = r"(\d+(?:[.,]\d+)?)\s*(?:%|pour ?cents?)"
_SPLIT = re.compile(
    rf"{_PCT}\s+(?:sur|pour|à|a|dans)\s+(?:la|le)\s+(?:premi[eè]re|1re|1ère|1er|premier)\b.{{0,80}}?"
    rf"{_PCT}\s+(?:sur|pour|à|a|dans)\s+(?:la|le)\s+(?:deuxi[eè]me|seconde?|2e|2ème)\b",
    re.I,
)


def split_from_text(asset: AssetAnalysis, window: list[Segment]) -> None:
    """« 40 % sur la première zone et 60 % sur la deuxième », read from the words.

    Only when the model left both entries without allocation and the sentence is
    there: the first stated share goes to the first entry, the second to the
    reinforcement. The sentence itself becomes the evidence.
    """

    entries = [lv for lv in asset.levels if lv.kind in ("BUY_ZONE", "REINFORCEMENT")]
    if len(entries) != 2 or any(lv.allocation_pct is not None for lv in entries):
        return
    first = next((lv for lv in entries if lv.kind == "BUY_ZONE"), None)
    second = next((lv for lv in entries if lv.kind == "REINFORCEMENT"), None)
    if first is None or second is None:
        return
    for seg in window:
        match = _SPLIT.search(seg.text)
        if not match:
            continue
        a, b = (float(x.replace(",", ".")) for x in match.groups())
        if a + b > 100:
            return
        evidence = Evidence(timestamp_s=seg.start_s, quote=seg.text, verified=True,
                            verification_note="Répartition lue dans ce passage.")
        for level, pct in ((first, a), (second, b)):
            level.allocation_pct, level.allocation_basis = pct, "EXPLICIT"
            level.allocation_evidence = evidence
        return


def _merge(parts: list[AssetAnalysis]) -> AssetAnalysis:
    base = parts[0]
    for part in parts[1:]:
        if base.price_at_video is None:
            base.price_at_video, base.price_at_video_evidence = (
                part.price_at_video, part.price_at_video_evidence)
        if base.stance == "UNSPECIFIED":
            base.stance, base.stance_basis = part.stance, part.stance_basis
        known = {(lv.kind, lv.value) for lv in base.levels}
        base.levels += [lv for lv in part.levels if (lv.kind, lv.value) not in known]
        for attr in ("situation", "scenarios", "arguments", "events", "reasoning",
                     "rejected", "ambiguous"):
            getattr(base, attr).extend(getattr(part, attr))
    base.reasoning = base.reasoning[:6]
    return base


# --- transcript quality ------------------------------------------------------------

_UNCERTAIN = re.compile(
    r"(inaudible|\(\?\)|\[\?\]|\?\?|\bvirgule\b|\b(un|deux|trois|quatre|cinq|six|sept|huit|neuf)\s+"
    r"(virgule|mille|cents?)\b)", re.I)


def transcript_info(segments: list[Segment], source: str) -> TranscriptInfo:
    duration = segments[-1].start_s if segments else 0
    words = sum(len(s.text.split()) for s in segments)
    per_minute = words / (duration / 60) if duration else 0
    if not segments:
        quality = "Transcription vide."
    elif per_minute < 60:
        quality = (f"Clairsemée : {per_minute:.0f} mots/min (une parole normale en compte "
                   "130 à 180). Des passages manquent probablement.")
    else:
        quality = f"Densité normale : {per_minute:.0f} mots/min."
    uncertain = [Evidence(timestamp_s=s.start_s, quote=s.text,
                          verification_note="Nombre dit en toutes lettres ou passage inaudible.")
                 for s in segments if _UNCERTAIN.search(s.text)]
    return TranscriptInfo(source=source, segments=len(segments), duration_s=duration,
                          characters=sum(len(s.text) for s in segments),
                          uncertain_passages=uncertain, quality=quality)


def extract(segments: list[Segment], *, title: str, published_at: str | None,
            source: str, model: str = DEFAULT_MODEL, llm=call_ollama) -> ExtractionResult:
    result = ExtractionResult(
        video=VideoInfo(title=title, published_at=published_at),
        transcript=transcript_info(segments, source),
        model=model,
        assets_mentioned=mentions(segments),
    )
    for symbol, window in topic_windows(segments).items():
        parts: list[AssetAnalysis] = []
        analysed = False
        for chunk in _chunks(window):
            try:
                raw = llm(SYSTEM_PROMPT, _user_prompt(symbol, render(chunk)), model=model)
            except Exception as exc:  # a model failure is reported, never papered over
                result.errors.append(f"{symbol} : le modèle local n'a pas répondu ({exc}).")
                continue
            if raw.get("analysed") is False:
                continue
            analysed = True
            parts.append(verify_asset(symbol, raw, chunk, segments))
        if not analysed or not parts:
            result.not_analysed.append(symbol)
            continue
        asset = _merge(parts)
        split_from_text(asset, window)
        # A sheet only for a crypto that is really analysed: something verified.
        if not asset.levels and len(asset.situation) < 2 and not asset.scenarios:
            result.not_analysed.append(symbol)
            continue
        result.assets.append(asset)
    return result


def reference_leak(values: list[float]) -> list[float]:
    """Values that would give the answer away if they sat in the prompt."""

    prompt_numbers = numbers_in(SYSTEM_PROMPT)
    return [v for v in values if any(same_value(v, n) for n in prompt_numbers)]
