"""Anti-hallucination guard: numbers cited must exist in the supplied context.

The single most dangerous failure mode for this tool is a model inventing a
price, a flow or a macro figure. Schema validation cannot catch that - a
fabricated number is perfectly well-formed JSON.

So every number the model writes is checked against the numbers we gave it.
Unmatched figures are reported, and the caller decides whether to retry or to
strip the offending claim.

The check is intentionally tolerant of formatting (1,234.5 / 1234.50) and
documented unit scaling, but every numeric assertion still has to be traceable
to the supplied context.  Percentages, ratios and small integers are claims too:
blanket exemptions for them would let fabricated values through.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_NUMBER_RE = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
_COMBINED_CURRENCY_RE = re.compile(r"^\s*(?P<prefix>[KMBT])?(?P<unit>USD|USDT|EUR)\b")
_MULTIPLIER_RE = re.compile(
    r"^\s*(?P<multiplier>k|m|b|t|thousand|million|billion|trillion|milliards?)\b",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"^\s*(?P<unit>%|percent|pct|bps?|x\b|USD\b|USDT\b|EUR\b|€|\$|hours?\b|h\b|days?\b|d\b)",
    re.IGNORECASE,
)
_SCALE = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
    "milliard": 1_000_000_000.0,
    "milliards": 1_000_000_000.0,
    "t": 1_000_000_000_000.0,
    "trillion": 1_000_000_000_000.0,
}
_GENERIC_TOKENS = {
    "a",
    "about",
    "and",
    "at",
    "current",
    "currently",
    "de",
    "des",
    "du",
    "en",
    "et",
    "for",
    "from",
    "in",
    "is",
    "la",
    "latest",
    "le",
    "les",
    "measured",
    "near",
    "normal",
    "of",
    "on",
    "or",
    "reached",
    "rose",
    "score",
    "the",
    "to",
    "trades",
    "un",
    "une",
    "validated",
    "value",
    "with",
}


@dataclass(frozen=True, slots=True)
class _NumericMention:
    raw_value: float
    canonical_value: float
    unit: str | None
    subject_tokens: frozenset[str]


def _normalize(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def extract_numbers(text: str) -> list[float]:
    out: list[float] = []
    for match in _NUMBER_RE.finditer(text):
        value = _normalize(match.group())
        if value is not None:
            out.append(value)
    return out


def _claimed_numbers(text: str) -> list[float]:
    """Every numeric assertion, regardless of size, unit or suffix."""
    return extract_numbers(text)


def collect_context_numbers(context: str) -> set[float]:
    """Every number the model was allowed to see."""
    return set(extract_numbers(context))


def _canonical_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    unit = raw.strip().upper()
    if unit in {"%", "PERCENT", "PCT"}:
        return "PERCENT"
    if unit in {"BP", "BPS"}:
        return "BPS"
    if unit == "X":
        return "RATIO"
    if unit in {"$", "USD", "USDT"}:
        return "USD"
    if unit in {"€", "EUR"}:
        return "EUR"
    if unit in {"H", "HOUR", "HOURS"}:
        return "HOURS"
    if unit in {"D", "DAY", "DAYS"}:
        return "DAYS"
    return unit


def _normalise_subject_token(token: str) -> str:
    lowered = token.lower()
    return {
        "bitcoin": "btc",
        "ethereum": "eth",
        "solana": "sol",
        "flows": "flow",
        "inflow": "flow",
        "inflows": "flow",
        "outflow": "flow",
        "outflows": "flow",
    }.get(lowered, lowered)


def _subject_tokens(fragment: str) -> frozenset[str]:
    tokens = {
        _normalise_subject_token(token)
        for token in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ_-]*", fragment)
    }
    return frozenset(token for token in tokens if token not in _GENERIC_TOKENS)


def _mentions(text: str) -> list[_NumericMention]:
    matches = list(_NUMBER_RE.finditer(text))
    mentions: list[_NumericMention] = []
    previous_end = 0
    for index, match in enumerate(matches):
        raw_value = _normalize(match.group())
        if raw_value is None:
            previous_end = match.end()
            continue

        sentence_start = max(
            text.rfind(".", previous_end, match.start()),
            text.rfind(";", previous_end, match.start()),
            text.rfind("\n", previous_end, match.start()),
            previous_end - 1,
        ) + 1
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sentence_end_candidates = [
            position
            for delimiter in (".", ";", "\n")
            if (position := text.find(delimiter, match.end(), next_start)) >= 0
        ]
        right_end = min(sentence_end_candidates, default=next_start)
        left = text[sentence_start : match.start()][-80:]
        right = text[match.end() : right_end][:50]

        tail = text[match.end() : match.end() + 40]
        scale = 1.0
        unit: str | None = None
        consumed = 0
        combined = _COMBINED_CURRENCY_RE.match(tail)
        if combined:
            prefix = combined.group("prefix")
            scale = _SCALE.get((prefix or "").lower(), 1.0)
            unit = _canonical_unit(combined.group("unit"))
            consumed = combined.end()
        else:
            multiplier = _MULTIPLIER_RE.match(tail)
            if multiplier:
                scale = _SCALE[multiplier.group("multiplier").lower()]
                consumed = multiplier.end()
            remaining = tail[consumed:]
            unit_match = _UNIT_RE.match(remaining)
            if unit_match:
                unit = _canonical_unit(unit_match.group("unit"))

        prefix = text[max(0, match.start() - 2) : match.start()].strip()
        if prefix.endswith("$"):
            unit = "USD"
        elif prefix.endswith("€"):
            unit = "EUR"

        mentions.append(
            _NumericMention(
                raw_value=raw_value,
                canonical_value=raw_value * scale,
                unit=unit,
                subject_tokens=_subject_tokens(f"{left} {right}"),
            )
        )
        previous_end = match.end()
    return mentions


def _subjects_compatible(claim: _NumericMention, evidence: _NumericMention) -> bool:
    if claim.subject_tokens and evidence.subject_tokens:
        return bool(claim.subject_tokens & evidence.subject_tokens)
    return not claim.subject_tokens and not evidence.subject_tokens


def _units_compatible(claim: _NumericMention, evidence: _NumericMention) -> bool:
    # Omitting a unit in prose is acceptable when the subject still identifies
    # the metric. Supplying an explicit unit requires an exact dimension/currency.
    return claim.unit is None or claim.unit == evidence.unit


def _values_close(claim: float, evidence: float, tolerance_pct: float) -> bool:
    if evidence == 0:
        return claim == 0
    return abs(claim - evidence) / abs(evidence) * 100.0 <= tolerance_pct


def find_unsupported_numbers(
    output_text: str, context: str, tolerance_pct: float = 1.0
) -> list[float]:
    """Numbers in the output that cannot be traced to the context.

    Tolerance covers rounding and unit scaling: a model writing 64,000 when the
    context said 64,012.34, or 1.26 for 1_260_000_000_000, is summarising rather
    than hallucinating.
    """
    evidence_mentions = _mentions(context)
    unsupported: list[float] = []

    for claim in _mentions(output_text):
        supported = any(
            _units_compatible(claim, evidence)
            and _subjects_compatible(claim, evidence)
            and _values_close(
                claim.canonical_value,
                evidence.canonical_value,
                tolerance_pct,
            )
            for evidence in evidence_mentions
        )
        if not supported:
            unsupported.append(claim.raw_value)

    return unsupported


def find_evidence_reference_errors(
    findings: Iterable[Any],
    allowed_references: set[str],
) -> list[str]:
    """Validate that narrative findings cite only evidence exposed to the LLM."""

    errors: list[str] = []
    for finding in findings:
        statement = str(getattr(finding, "statement", "")).strip()
        references = list(getattr(finding, "evidence_refs", []) or [])
        if not references:
            errors.append(f"finding has no evidence reference: {statement}")
            continue
        for reference in references:
            if reference not in allowed_references:
                errors.append(f"unknown evidence reference '{reference}'")
    return list(dict.fromkeys(errors))


ANTI_HALLUCINATION_RULES = """
ABSOLUTE RULES - violating any of these makes your entire answer invalid:

1. You may ONLY use numbers that appear in the DATA section below. Never invent
   or estimate a price, an ETF flow, a funding rate, an on-chain metric, a macro
   figure, a whale movement or a source.
2. If a datapoint is absent, write exactly: UNAVAILABLE
3. If a datapoint is present but marked STALE, treat it as stale and say so.
4. If the evidence does not support a conclusion, write exactly: INCONCLUSIVE
5. Never present a legislative proposal as adopted law. Respect the
   legal_status field exactly as given.
6. Never produce a scenario probability. A probability may be displayed only
   when a separate calibrated, out-of-sample-tested model supplies its value,
   target definition, source and observation time.
7. Never recommend a trade, a position size, or an entry/exit. You explain what
   the data shows; the human decides.
8. Base every statement on the DATA section. If you are unsure, say so
   explicitly rather than filling the gap.
""".strip()
