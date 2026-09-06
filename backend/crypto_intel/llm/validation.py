"""Anti-hallucination guard: numbers cited must exist in the supplied context.

The single most dangerous failure mode for this tool is a model inventing a
price, a flow or a macro figure. Schema validation cannot catch that - a
fabricated number is perfectly well-formed JSON.

So every number the model writes is checked against the numbers we gave it.
Unmatched figures are reported, and the caller decides whether to retry or to
strip the offending claim.

The check is intentionally tolerant of formatting (1,234.5 / 1234.50 / 1.23K)
and of arithmetic the model may legitimately do (percentages, sums), so it
flags invention rather than punishing presentation.
"""

from __future__ import annotations

import re

# Bare small integers are counters, ordinals and list positions - checking them
# produces noise, not safety. Anything with a decimal part, or any large number,
# is treated as a claimed datapoint and must be traceable to the context.
_IGNORE_INTEGER_BELOW = 1000.0
_YEAR_RANGE = range(1990, 2101)

_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
# A figure written as a percentage or a multiple is usually derived by the model
# from values it was given (a change, a ratio), so it is not evidence of
# invention and is checked far more loosely.
_DERIVED_SUFFIX_RE = re.compile(r"\s*(%|x\b|percent|pct)", re.I)


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
    """Numbers that assert a datapoint, excluding derived percentages/ratios."""
    out: list[float] = []
    for match in _NUMBER_RE.finditer(text):
        token = match.group()
        value = _normalize(token)
        if value is None:
            continue
        # "+3.2%" or "1.8x" - the model computed it, do not treat as a raw claim.
        if _DERIVED_SUFFIX_RE.match(text[match.end() : match.end() + 8]):
            continue
        is_integer = "." not in token
        if is_integer and abs(value) < _IGNORE_INTEGER_BELOW:
            continue
        if is_integer and int(value) in _YEAR_RANGE:
            continue
        out.append(value)
    return out


def collect_context_numbers(context: str) -> set[float]:
    """Every number the model was allowed to see."""
    return set(extract_numbers(context))


def find_unsupported_numbers(
    output_text: str, context: str, tolerance_pct: float = 1.0
) -> list[float]:
    """Numbers in the output that cannot be traced to the context.

    Tolerance covers rounding and unit scaling: a model writing 64,000 when the
    context said 64,012.34, or 1.26 for 1_260_000_000_000, is summarising rather
    than hallucinating.
    """
    allowed = collect_context_numbers(context)

    derived: set[float] = set()
    for a in allowed:
        derived.add(round(a, 2))
        derived.add(round(a))
        if a != 0:
            for scale in (1_000.0, 1_000_000.0, 1e9, 1e12):
                derived.add(round(a / scale, 2))
                derived.add(round(a * scale, 2))

    universe = allowed | derived
    unsupported: list[float] = []

    for value in _claimed_numbers(output_text):
        ok = False
        for candidate in universe:
            if candidate == 0:
                if value == 0:
                    ok = True
                    break
                continue
            if abs(value - candidate) / abs(candidate) * 100.0 <= tolerance_pct:
                ok = True
                break
        if not ok:
            unsupported.append(value)

    return unsupported


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
6. Probabilities you produce are analytical estimates, not calibrated model
   outputs. Do not claim statistical certainty.
7. Never recommend a trade, a position size, or an entry/exit. You explain what
   the data shows; the human decides.
8. Base every statement on the DATA section. If you are unsure, say so
   explicitly rather than filling the gap.
""".strip()
