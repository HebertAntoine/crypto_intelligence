"""Parse trader transcripts into structured analysis examples.

Legality first. This module never fetches, downloads or scrapes anything. It
accepts text the user already has: a transcript they were given, captions they
obtained legitimately, exported notes, or their own writing. No YouTube
protection is touched, because nothing is retrieved at all.

The parser recognises structural vocabulary in French and English, extracts
price levels near those terms, and records what it could NOT determine. An
example missing its asset or timeframe is marked unusable rather than guessed
at - a wrongly aligned example is worse than no example, because it silently
contaminates every study built on it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..logging_setup import get_logger
from .models import DataQuality, ExtractionMethod, TraderAnalysisExample

log = get_logger("trader_knowledge.transcript")

# Structural vocabulary, French and English together. Each concept maps to the
# phrases that signal it; matching is case-insensitive and accent-tolerant.
CONCEPT_PATTERNS: dict[str, list[str]] = {
    "range": [r"\brange\b", r"\bfourchette\b", r"\bconsolidation\b", r"\bzone de trading\b"],
    "range_top": [
        r"\brange top\b", r"\bhaut du range\b", r"\bhaut de range\b",
        r"\bsommet du range\b", r"\btop of the range\b", r"\bpartie haute\b",
    ],
    "range_bottom": [
        r"\brange bottom\b", r"\bbas du range\b", r"\bbas de range\b",
        r"\bbottom of the range\b", r"\bpartie basse\b", r"\bplancher\b",
    ],
    "mid_range": [r"\bmid[- ]?range\b", r"\bmilieu du range\b", r"\bmediane\b"],
    "support": [r"\bsupport\b", r"\bsoutien\b"],
    "resistance": [r"\bresistance\b", r"\bresistence\b"],
    "breakout": [
        r"\bbreak ?out\b", r"\bcassure\b", r"\bcasse\b", r"\bfranchit\b",
        r"\bbreak(?:s|ing)? (?:above|below)\b", r"\bsortie de range\b",
    ],
    "retest": [r"\bre ?test\b", r"\bpullback\b", r"\brevient tester\b"],
    "fakeout": [
        r"\bfake ?out\b", r"\bfausse cassure\b", r"\bfaux breakout\b",
        r"\bfalse break\b", r"\bpiege\b",
    ],
    "deviation": [r"\bdeviation\b", r"\bdeviate\b", r"\bmeche sous\b", r"\bwick below\b"],
    "liquidity_sweep": [
        r"\bsweep\b", r"\bliquidity grab\b", r"\bprise de liquidite\b",
        r"\bchasse aux stops\b", r"\bstop hunt\b",
    ],
    "double_top": [r"\bdouble top\b", r"\bdouble sommet\b"],
    "double_bottom": [r"\bdouble bottom\b", r"\bdouble creux\b", r"\bdouble fond\b"],
    "head_and_shoulders": [r"\bhead and shoulders\b", r"\betl?e et epaules\b", r"\bete et epaules\b"],
    "trend": [r"\btrend\b", r"\btendance\b", r"\bhaussier\b", r"\bbaissier\b", r"\bbullish\b", r"\bbearish\b"],
    "higher_high": [r"\bhigher high\b", r"\bHH\b", r"\bplus haut plus haut\b"],
    "higher_low": [r"\bhigher low\b", r"\bHL\b", r"\bplus bas plus haut\b"],
    "lower_high": [r"\blower high\b", r"\bLH\b", r"\bplus haut plus bas\b"],
    "lower_low": [r"\blower low\b", r"\bLL\b", r"\bplus bas plus bas\b"],
    "invalidation": [
        r"\binvalidation\b", r"\binvalide\b", r"\binvalidate[sd]?\b",
        r"\bthese would be wrong\b", r"\bsi on casse\b",
    ],
    "confirmation": [r"\bconfirmation\b", r"\bconfirme\b", r"\bconfirmed\b"],
    "weekly_close": [r"\bweekly close\b", r"\bcloture hebdo\w*\b", r"\bcloture weekly\b"],
    "daily_close": [r"\bdaily close\b", r"\bcloture (?:journaliere|daily|quotidienne)\b"],
    "four_hour_close": [r"\b4 ?h close\b", r"\bcloture 4 ?h\b", r"\bh4 close\b"],
    "accumulation": [r"\baccumulation\b", r"\baccumule\b"],
    "distribution": [r"\bdistribution\b", r"\bdistribue\b"],
}

ASSET_PATTERNS: dict[str, list[str]] = {
    "BTC": [r"\bbtc\b", r"\bbitcoin\b"],
    "ETH": [r"\beth\b", r"\bethereum\b", r"\bether\b"],
    "SOL": [r"\bsol\b", r"\bsolana\b"],
}

TIMEFRAME_PATTERNS: dict[str, list[str]] = {
    "15m": [r"\b15 ?m(?:in)?\b", r"\b15 minutes\b"],
    "1h": [r"\b1 ?h\b", r"\bhourly\b", r"\bune heure\b", r"\bh1\b"],
    "4h": [r"\b4 ?h\b", r"\bh4\b", r"\bquatre heures\b"],
    "1d": [r"\bdaily\b", r"\b1 ?d\b", r"\bjournalier\b", r"\bquotidien\b", r"\bd1\b"],
    "1w": [r"\bweekly\b", r"\b1 ?w\b", r"\bhebdomadaire\b", r"\bhebdo\b", r"\bw1\b"],
}

BIAS_PATTERNS: dict[str, list[str]] = {
    "BULLISH": [r"\bbullish\b", r"\bhaussier\b", r"\blong\b", r"\bmonter\b", r"\bupside\b"],
    "BEARISH": [r"\bbearish\b", r"\bbaissier\b", r"\bshort\b", r"\bdescendre\b", r"\bdownside\b"],
}

# Numbers that look like prices: 92000, 92,000, 92k, 1.05, 0.0312
PRICE_PATTERN = re.compile(
    r"(?<![\w.])(\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s?[kK]\b|\d+\.\d+|\d{2,7})(?![\w%])"
)

ACCENT_MAP = str.maketrans("àâäéèêëïîôöùûüçÀÂÄÉÈÊËÏÎÔÖÙÛÜÇ", "aaaeeeeiioouuucAAAEEEEIIOOUUUC")


def normalise(text: str) -> str:
    """Lowercase and strip accents so French matching is robust."""
    return text.translate(ACCENT_MAP).lower()


def _parse_price(raw: str) -> float | None:
    cleaned = raw.strip().replace(",", "").replace(" ", "")
    multiplier = 1.0
    if cleaned.lower().endswith("k"):
        cleaned = cleaned[:-1]
        multiplier = 1000.0
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


@dataclass(slots=True)
class ParsedSegment:
    """One sentence and what was recognised in it."""

    text: str
    concepts: list[str] = field(default_factory=list)
    prices: list[float] = field(default_factory=list)
    position: int = 0


@dataclass(slots=True)
class TranscriptParse:
    """Everything extracted, plus everything that stayed ambiguous."""

    asset: str | None = None
    timeframe: str | None = None
    concepts: list[str] = field(default_factory=list)
    segments: list[ParsedSegment] = field(default_factory=list)
    range_top: float | None = None
    range_bottom: float | None = None
    supports: list[float] = field(default_factory=list)
    resistances: list[float] = field(default_factory=list)
    invalidation: float | None = None
    directional_bias: str | None = None
    ambiguities: list[str] = field(default_factory=list)
    data_quality: DataQuality = DataQuality.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset, "timeframe": self.timeframe,
            "concepts": self.concepts,
            "range_top": self.range_top, "range_bottom": self.range_bottom,
            "supports": self.supports, "resistances": self.resistances,
            "invalidation": self.invalidation,
            "directional_bias": self.directional_bias,
            "segments_matched": len(self.segments),
            "ambiguities": self.ambiguities,
            "data_quality": self.data_quality.value,
        }


def _attach_by_proximity(sentence: str, concepts: list[str]) -> dict[str, float]:
    """Give each price to the concept term closest before it.

    A sentence naming both range boundaries is common and unambiguous to a
    reader: the number follows the term it belongs to. Position is what
    encodes that, so position is what we use.
    """
    positions: list[tuple[int, str]] = []
    for concept in ("range_top", "range_bottom", "support", "resistance", "invalidation"):
        if concept not in concepts:
            continue
        for expression in CONCEPT_PATTERNS.get(concept, []):
            match = re.search(expression, sentence)
            if match:
                positions.append((match.start(), concept))
                break
    if not positions:
        return {}
    positions.sort()

    attached: dict[str, float] = {}
    for match in PRICE_PATTERN.finditer(sentence):
        value = _parse_price(match.group(1))
        if value is None or value <= 0:
            continue
        preceding = [(pos, name) for pos, name in positions if pos < match.start()]
        if not preceding:
            continue
        _, owner = preceding[-1]
        attached.setdefault(owner, value)
    return attached


def _find_all(text: str, patterns: dict[str, list[str]]) -> list[str]:
    found = []
    for label, expressions in patterns.items():
        if any(re.search(expression, text) for expression in expressions):
            found.append(label)
    return found


def parse_transcript(raw_text: str) -> TranscriptParse:
    """Extract structure, levels and bias from free text.

    Levels are attached to a concept only when they appear in the same sentence
    as the term. Pulling the nearest number from anywhere in the transcript
    produced confident nonsense, so proximity is required and unmatched terms
    are recorded as ambiguities instead.
    """
    parse = TranscriptParse()
    if not raw_text or not raw_text.strip():
        parse.ambiguities.append("empty transcript")
        parse.data_quality = DataQuality.UNUSABLE
        return parse

    text = normalise(raw_text)

    assets = _find_all(text, ASSET_PATTERNS)
    if len(assets) == 1:
        parse.asset = assets[0]
    elif len(assets) > 1:
        parse.ambiguities.append(
            f"multiple assets mentioned ({', '.join(assets)}); asset left unset"
        )
    else:
        parse.ambiguities.append("no asset identified")

    timeframes = _find_all(text, TIMEFRAME_PATTERNS)
    if len(timeframes) == 1:
        parse.timeframe = timeframes[0]
    elif len(timeframes) > 1:
        parse.ambiguities.append(
            f"multiple timeframes mentioned ({', '.join(timeframes)}); timeframe left unset"
        )
    else:
        parse.ambiguities.append("no timeframe identified")

    biases = _find_all(text, BIAS_PATTERNS)
    if len(biases) == 1:
        parse.directional_bias = biases[0]
    elif len(biases) > 1:
        parse.ambiguities.append("both bullish and bearish language present")

    # Sentence-level extraction so a price belongs to the concept beside it.
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    for position, sentence in enumerate(sentences):
        concepts = _find_all(sentence, CONCEPT_PATTERNS)
        if not concepts:
            continue
        prices = [
            value for value in (
                _parse_price(m.group(1)) for m in PRICE_PATTERN.finditer(sentence)
            ) if value is not None and value > 0
        ]
        parse.segments.append(
            ParsedSegment(text=sentence.strip()[:300], concepts=concepts,
                          prices=prices, position=position)
        )
        for concept in concepts:
            if concept not in parse.concepts:
                parse.concepts.append(concept)

        if prices:
            # Attach each price to the nearest preceding concept term, rather
            # than taking max for the top and min for the bottom. "the range
            # top is at 90 and the range bottom is at 95000" is a parse the
            # speaker got wrong or we misheard; silently swapping the two would
            # hide that, and "le bas du range a 88500 et le haut a 95200" - one
            # sentence naming both - must still parse correctly.
            attached = _attach_by_proximity(sentence, concepts)
            if "range_top" in attached and parse.range_top is None:
                parse.range_top = attached["range_top"]
            if "range_bottom" in attached and parse.range_bottom is None:
                parse.range_bottom = attached["range_bottom"]
            if "support" in concepts:
                parse.supports.extend(prices)
            if "resistance" in concepts:
                parse.resistances.extend(prices)
            if "invalidation" in concepts and parse.invalidation is None:
                parse.invalidation = prices[0]

    parse.supports = sorted(set(parse.supports))[:6]
    parse.resistances = sorted(set(parse.resistances))[:6]

    for concept in ("range_top", "range_bottom"):
        if concept in parse.concepts and getattr(parse, concept) is None:
            parse.ambiguities.append(
                f"'{concept}' mentioned but no price appeared in the same sentence"
            )

    # A range needs both edges the right way round.
    inverted = (
        parse.range_top is not None
        and parse.range_bottom is not None
        and parse.range_top <= parse.range_bottom
    )
    if inverted:
        parse.ambiguities.append(
            "extracted range top is not above the range bottom; both discarded"
        )
        parse.range_top = parse.range_bottom = None

    parse.data_quality = _quality(parse)
    return parse


def _quality(parse: TranscriptParse) -> DataQuality:
    if parse.asset is None or parse.timeframe is None:
        return DataQuality.UNUSABLE
    if not parse.concepts:
        return DataQuality.UNUSABLE
    has_levels = any([
        parse.range_top is not None, parse.range_bottom is not None,
        parse.supports, parse.resistances,
    ])
    if has_levels and not parse.ambiguities:
        return DataQuality.HIGH
    if has_levels or len(parse.concepts) >= 3:
        return DataQuality.MEDIUM
    return DataQuality.LOW


def build_example(
    raw_text: str,
    source: str = "lexa_moon",
    author: str = "",
    source_url: str | None = None,
    published_at: datetime | None = None,
    analysis_time: datetime | None = None,
    asset_override: str | None = None,
    timeframe_override: str | None = None,
    extraction_method: ExtractionMethod = ExtractionMethod.USER_PROVIDED_TRANSCRIPT,
) -> tuple[TraderAnalysisExample, TranscriptParse]:
    """Turn a transcript into a stored example, keeping every ambiguity visible."""
    parse = parse_transcript(raw_text)

    # Explicit overrides beat inference - the user knows what the video covered.
    asset = asset_override or parse.asset
    timeframe = timeframe_override or parse.timeframe
    if asset_override and parse.asset and asset_override != parse.asset:
        parse.ambiguities.append(
            f"user override asset={asset_override} differs from parsed {parse.asset}"
        )
    if asset_override or timeframe_override:
        parse.data_quality = _quality(
            TranscriptParse(
                asset=asset, timeframe=timeframe, concepts=parse.concepts,
                range_top=parse.range_top, range_bottom=parse.range_bottom,
                supports=parse.supports, resistances=parse.resistances,
                ambiguities=parse.ambiguities,
            )
        )

    digest = hashlib.sha1(
        f"{source}|{source_url}|{raw_text[:400]}".encode()
    ).hexdigest()[:14]

    example = TraderAnalysisExample(
        id=f"tae_{digest}",
        source=source, author=author, source_url=source_url,
        published_at=published_at,
        analysis_time=analysis_time or published_at,
        asset=asset, timeframe=timeframe,
        transcript_reference=raw_text.strip()[:280],
        concepts=parse.concepts,
        structure_type=_infer_structure(parse.concepts),
        range_top=parse.range_top, range_bottom=parse.range_bottom,
        mid_range=(
            (parse.range_top + parse.range_bottom) / 2
            if parse.range_top and parse.range_bottom else None
        ),
        supports=parse.supports, resistances=parse.resistances,
        invalidation=parse.invalidation,
        directional_bias_if_mentioned=parse.directional_bias,
        reasoning=" ".join(s.text for s in parse.segments[:4])[:600],
        data_quality=parse.data_quality,
        extraction_method=extraction_method,
        human_verified=False,
    )
    return example, parse


def _infer_structure(concepts: list[str]) -> str | None:
    for concept in (
        "double_bottom", "double_top", "head_and_shoulders",
        "liquidity_sweep", "fakeout", "deviation", "breakout", "range",
    ):
        if concept in concepts:
            return concept.upper()
    return None
