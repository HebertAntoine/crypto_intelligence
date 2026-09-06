"""Educational sources: definitions and testable claims, not market facts.

Copyright is respected by construction. Nothing here reproduces a source
article. What is stored is:

  * provenance (URL, title, language, ingestion date);
  * the CONCEPTS the source covers;
  * our own paraphrase of each definition, written from general chart-analysis
    knowledge and attributed to the source as a reference;
  * the testable claim implied by the concept.

The distinction that matters: a definition tells the detector what shape to
look for, and a claim ("a falling wedge generally resolves upward") is a
hypothesis the research layer must test. Neither is ever treated as true
because a source said so - and GoodCrypto sits at TIER 4, so it cannot
override anything measured.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from ..logging_setup import get_logger
from .models import ClaimType, EducationalClaim

log = get_logger("trader_knowledge.educational")

GOODCRYPTO = {
    "source": "goodcrypto",
    "url": "https://goodcrypto.app/fr/chart-patterns-for-crypto-trading-trading-patterns-explained/",
    "title": "Chart patterns for crypto trading, patterns explained",
    "language": "fr",
    "note": (
        "Reference only. No text from this article is reproduced; the definitions "
        "below are our own paraphrases of standard chart-analysis concepts, recorded "
        "so the corresponding claims can be tested against data."
    ),
}


def _claim_id(source: str, concept: str, statement: str) -> str:
    digest = hashlib.sha1(f"{source}|{concept}|{statement}".encode()).hexdigest()[:12]
    return f"claim_{digest}"


# Each entry: concept, our paraphrased definition, and the directional claim
# conventional analysis attaches to it. The claim is what gets tested.
CONCEPT_LIBRARY: list[dict[str, Any]] = [
    {
        "concept": "double_top",
        "definition": (
            "Two highs at a comparable level separated by a pullback, forming a "
            "resistance the second attempt failed to clear. The neckline is the low "
            "between the two highs."
        ),
        "claim": "A double top generally resolves downward once the neckline breaks.",
        "direction": "BEARISH",
        "category": "reversal",
    },
    {
        "concept": "double_bottom",
        "definition": (
            "Two lows at a comparable level separated by a bounce, forming a support "
            "the second test held. The neckline is the high between the two lows."
        ),
        "claim": "A double bottom generally resolves upward once the neckline breaks.",
        "direction": "BULLISH",
        "category": "reversal",
    },
    {
        "concept": "triple_top",
        "definition": "Three failed attempts at a comparable resistance level.",
        "claim": "A triple top generally resolves downward.",
        "direction": "BEARISH",
        "category": "reversal",
    },
    {
        "concept": "triple_bottom",
        "definition": "Three successful defences of a comparable support level.",
        "claim": "A triple bottom generally resolves upward.",
        "direction": "BULLISH",
        "category": "reversal",
    },
    {
        "concept": "head_and_shoulders",
        "definition": (
            "Three highs where the middle one is clearly the highest and the two "
            "outer ones sit at a comparable, lower level. The neckline joins the lows "
            "between them."
        ),
        "claim": "A head and shoulders generally precedes a downward reversal.",
        "direction": "BEARISH",
        "category": "reversal",
    },
    {
        "concept": "inverse_head_and_shoulders",
        "definition": (
            "The mirror of head and shoulders: a lowest middle low flanked by two "
            "comparable higher lows."
        ),
        "claim": "An inverse head and shoulders generally precedes an upward reversal.",
        "direction": "BULLISH",
        "category": "reversal",
    },
    {
        "concept": "ascending_triangle",
        "definition": (
            "A flat resistance repeatedly tested while lows rise toward it, "
            "compressing price into the apex."
        ),
        "claim": "An ascending triangle generally breaks upward.",
        "direction": "BULLISH",
        "category": "continuation",
    },
    {
        "concept": "descending_triangle",
        "definition": "A flat support repeatedly tested while highs fall toward it.",
        "claim": "A descending triangle generally breaks downward.",
        "direction": "BEARISH",
        "category": "continuation",
    },
    {
        "concept": "symmetrical_triangle",
        "definition": "Highs falling and lows rising at comparable rates.",
        "claim": (
            "A symmetrical triangle is directionally neutral and resolves in the "
            "direction of the break."
        ),
        "direction": "NEUTRAL",
        "category": "continuation",
    },
    {
        "concept": "rising_wedge",
        "definition": (
            "Both boundaries slope upward while converging, so each advance is "
            "smaller than the last."
        ),
        "claim": "A rising wedge generally resolves downward.",
        "direction": "BEARISH",
        "category": "reversal",
    },
    {
        "concept": "falling_wedge",
        "definition": "Both boundaries slope downward while converging.",
        "claim": "A falling wedge generally resolves upward.",
        "direction": "BULLISH",
        "category": "reversal",
    },
    {
        "concept": "bull_flag",
        "definition": (
            "A sharp advance followed by a shallow drift against it, on lower "
            "activity."
        ),
        "claim": "A bull flag generally resolves upward, continuing the prior advance.",
        "direction": "BULLISH",
        "category": "continuation",
    },
    {
        "concept": "bear_flag",
        "definition": "A sharp decline followed by a shallow drift against it.",
        "claim": "A bear flag generally resolves downward.",
        "direction": "BEARISH",
        "category": "continuation",
    },
    {
        "concept": "pennant",
        "definition": "A sharp move followed by a small symmetrical consolidation.",
        "claim": "A pennant generally continues in the direction of the prior move.",
        "direction": "NEUTRAL",
        "category": "continuation",
    },
    {
        "concept": "breakout_volume_confirmation",
        "definition": (
            "A breakout accompanied by activity above its recent average, as opposed "
            "to one on ordinary activity."
        ),
        "claim": "A breakout on elevated volume is more likely to hold than one without.",
        "direction": "NEUTRAL",
        "category": "confirmation",
    },
    {
        "concept": "breakout_retest",
        "definition": (
            "Price breaks a level, returns to test it from the other side, and the "
            "level holds in its new role."
        ),
        "claim": "A successful retest confirms a breakout and precedes continuation.",
        "direction": "NEUTRAL",
        "category": "confirmation",
    },
    {
        "concept": "range_bottom",
        "definition": (
            "The lower boundary of a range, defined by repeated reactions rather than "
            "a single price."
        ),
        "claim": "Buying near a validated range bottom is favourable within a range.",
        "direction": "BULLISH",
        "category": "location",
    },
    {
        "concept": "range_top",
        "definition": "The upper boundary of a range, defined by repeated rejections.",
        "claim": "Price near a validated range top is likely to be rejected.",
        "direction": "BEARISH",
        "category": "location",
    },
    {
        "concept": "range_deviation",
        "definition": (
            "Price leaves the range, fails to hold outside, and reintegrates - often "
            "called a sweep or fakeout."
        ),
        "claim": (
            "A deviation below a range bottom that reintegrates generally precedes a "
            "move toward the range top."
        ),
        "direction": "BULLISH",
        "category": "reversal",
    },
]


def build_goodcrypto_claims() -> list[EducationalClaim]:
    """Structured, testable claims attributed to the reference source."""
    claims: list[EducationalClaim] = []
    now = datetime.now(UTC)

    for entry in CONCEPT_LIBRARY:
        claims.append(EducationalClaim(
            id=_claim_id(GOODCRYPTO["source"], entry["concept"], entry["definition"]),
            claim_type=ClaimType.EDUCATIONAL_DEFINITION,
            concept=entry["concept"],
            statement=entry["definition"],
            implied_direction=None,
            source=GOODCRYPTO["source"],
            source_url=GOODCRYPTO["url"],
            source_title=GOODCRYPTO["title"],
            language=GOODCRYPTO["language"],
            ingested_at=now,
            paraphrase=entry["definition"],
            testable=False,
            test_note="A definition describes a shape; there is nothing to test.",
        ))
        claims.append(EducationalClaim(
            id=_claim_id(GOODCRYPTO["source"], entry["concept"], entry["claim"]),
            claim_type=ClaimType.EDUCATIONAL_CLAIM,
            concept=entry["concept"],
            statement=entry["claim"],
            implied_direction=entry["direction"],
            conditions=[entry["category"]],
            source=GOODCRYPTO["source"],
            source_url=GOODCRYPTO["url"],
            source_title=GOODCRYPTO["title"],
            language=GOODCRYPTO["language"],
            ingested_at=now,
            paraphrase=entry["claim"],
            testable=entry["direction"] in ("BULLISH", "BEARISH"),
            test_note=(
                "Directional claim - testable against forward returns."
                if entry["direction"] in ("BULLISH", "BEARISH")
                else "Non-directional claim; testable only as a conditioning variable."
            ),
        ))
    return claims


def store_claims(claims: list[EducationalClaim], path: str | None = None) -> dict[str, Any]:
    import json
    import pathlib

    target = pathlib.Path(path or "data/knowledge/educational_claims.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": [GOODCRYPTO],
        "claims": [c.to_dict() for c in claims],
        "copyright_note": (
            "No source text is reproduced. Definitions are our own paraphrases of "
            "standard chart-analysis concepts, recorded with attribution so the "
            "corresponding claims can be tested."
        ),
    }
    target.write_text(json.dumps(payload, indent=2, default=str))
    log.info("educational_claims_stored", count=len(claims), path=str(target))
    return {
        "stored": len(claims),
        "testable": sum(1 for c in claims if c.testable),
        "definitions": sum(1 for c in claims if c.claim_type is ClaimType.EDUCATIONAL_DEFINITION),
        "path": str(target),
    }


def load_claims(path: str | None = None) -> list[dict[str, Any]]:
    import json
    import pathlib

    target = pathlib.Path(path or "data/knowledge/educational_claims.json")
    if not target.exists():
        return []
    try:
        return json.loads(target.read_text()).get("claims", [])
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("claims_unreadable", error=str(exc))
        return []
