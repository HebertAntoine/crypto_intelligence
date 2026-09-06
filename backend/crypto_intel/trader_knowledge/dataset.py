"""The human-example dataset: storage, corrections, quality and agreement.

Three ideas drive this module.

Corrections are VERSIONED, never destructive. When the user says "that is not
a range" or "Lexa was talking about the 4H", the original annotation is kept
and a new version is layered on top. An annotation history is evidence about
how hard the labelling is; overwriting it destroys that evidence.

Episodes, not examples, are the unit of evidence. Twenty videos about the same
BTC range are one observation. The quality dashboard reports raw counts,
episode counts and effective sample side by side so a large dataset cannot
masquerade as a diverse one.

Uncertainty drives annotation. The examples worth a human's time are the ones
where the algorithm is unsure, not the ones it already handles well.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter
from typing import Any

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger
from .models import AnnotationCorrection, TraderAnalysisExample

log = get_logger("trader_knowledge.dataset")

DATASET_DIR = pathlib.Path("data/trader_knowledge")
EXAMPLES_FILE = "examples.json"
CORRECTIONS_FILE = "corrections.json"

# Below this, a category describes its own examples and nothing more.
MIN_EPISODES_FOR_STUDY = 20


def _path(name: str) -> pathlib.Path:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    return DATASET_DIR / name


def load_examples() -> list[TraderAnalysisExample]:
    path = _path(EXAMPLES_FILE)
    if not path.exists():
        return []
    try:
        return [TraderAnalysisExample(**row) for row in json.loads(path.read_text())]
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        log.warning("examples_unreadable", error=str(exc))
        return []


def save_examples(examples: list[TraderAnalysisExample]) -> int:
    _path(EXAMPLES_FILE).write_text(
        json.dumps([e.model_dump(mode="json") for e in examples], indent=2, default=str)
    )
    return len(examples)


def add_example(example: TraderAnalysisExample) -> dict[str, Any]:
    """Store one example, refusing silent duplicates."""
    examples = load_examples()
    if any(e.id == example.id for e in examples):
        return {"status": "DUPLICATE", "id": example.id}
    examples.append(example)
    save_examples(examples)
    log.info("example_added", id=example.id, source=example.source)
    return {"status": "ADDED", "id": example.id, "total": len(examples)}


def load_corrections() -> list[AnnotationCorrection]:
    path = _path(CORRECTIONS_FILE)
    if not path.exists():
        return []
    try:
        return [AnnotationCorrection(**row) for row in json.loads(path.read_text())]
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []


def correct_example(
    example_id: str, field_name: str, new_value: Any,
    reason: str = "", corrected_by: str = "user",
) -> dict[str, Any]:
    """Apply a correction while preserving what it replaced.

    The previous value is written into the correction record before the example
    changes, so the full annotation history stays reconstructable.
    """
    examples = load_examples()
    target = next((e for e in examples if e.id == example_id), None)
    if target is None:
        return {"status": "NOT_FOUND", "id": example_id}
    if not hasattr(target, field_name):
        return {"status": "UNKNOWN_FIELD", "field": field_name}

    previous = getattr(target, field_name)
    corrections = load_corrections()
    version = target.annotation_version + 1

    corrections.append(AnnotationCorrection(
        example_id=example_id, field_name=field_name,
        previous_value=previous, new_value=new_value,
        correction_reason=reason, corrected_by=corrected_by,
        annotation_version=version,
    ))
    _path(CORRECTIONS_FILE).write_text(
        json.dumps([c.model_dump(mode="json") for c in corrections], indent=2, default=str)
    )

    setattr(target, field_name, new_value)
    target.annotation_version = version
    target.human_verified = True
    save_examples(examples)

    log.info("example_corrected", id=example_id, field=field_name, version=version)
    return {
        "status": "CORRECTED", "id": example_id, "field": field_name,
        "previous_value": previous, "new_value": new_value,
        "annotation_version": version,
        "note": "the previous value is preserved in the correction history",
    }


def annotation_history(example_id: str) -> list[dict[str, Any]]:
    return [
        c.model_dump(mode="json") for c in load_corrections()
        if c.example_id == example_id
    ]


def dataset_quality() -> dict[str, Any]:
    """What the dataset actually contains, and where the holes are."""
    examples = load_examples()
    if not examples:
        return {
            "status": "EMPTY",
            "note": (
                "No human examples stored yet. Every human-example study will report "
                "INSUFFICIENT_DATA until a gold dataset is built."
            ),
            "target": "50-100 well-aligned examples before industrialising ingestion",
        }

    episodes = {e.market_episode_id for e in examples if e.market_episode_id}
    by_asset = Counter(e.asset or "UNKNOWN" for e in examples)
    by_timeframe = Counter(e.timeframe or "UNKNOWN" for e in examples)
    by_source = Counter(e.source for e in examples)
    by_quality = Counter(e.data_quality.value for e in examples)
    by_structure = Counter(e.structure_type or "NONE" for e in examples)
    concepts = Counter(c for e in examples for c in e.concepts)

    # Effective sample: episodes, not examples. Twenty videos on one range are
    # one observation.
    effective = len(episodes) if episodes else 0

    gaps: list[str] = []
    for structure, count in by_structure.items():
        if structure == "NONE":
            continue
        structure_episodes = len({
            e.market_episode_id for e in examples
            if e.structure_type == structure and e.market_episode_id
        })
        if structure_episodes < MIN_EPISODES_FOR_STUDY:
            gaps.append(
                f"{structure}: {count} examples but only {structure_episodes} distinct "
                f"episodes - INSUFFICIENT_DATA (need {MIN_EPISODES_FOR_STUDY})"
            )

    largest = max(by_structure.values()) if by_structure else 0
    smallest = min(by_structure.values()) if by_structure else 0
    imbalance = round(largest / smallest, 2) if smallest else None

    return {
        "status": "OK",
        "number_examples": len(examples),
        "human_verified": sum(1 for e in examples if e.human_verified),
        "market_episodes": len(episodes),
        "effective_sample_size": effective,
        "examples_per_episode": (
            round(len(examples) / len(episodes), 2) if episodes else None
        ),
        "examples_per_asset": dict(by_asset),
        "examples_per_timeframe": dict(by_timeframe),
        "examples_per_source": dict(by_source),
        "examples_per_structure": dict(by_structure),
        "quality_distribution": dict(by_quality),
        "top_concepts": dict(concepts.most_common(12)),
        "class_imbalance_ratio": imbalance,
        "usable_for_study": effective >= MIN_EPISODES_FOR_STUDY,
        "gaps": gaps,
        "note": (
            "Effective sample counts EPISODES, not examples. A category with many "
            "examples but few episodes cannot support a study."
        ),
    }


def active_learning_queue(limit: int = 20) -> dict[str, Any]:
    """Cases where the algorithm is least certain - the best use of human time.

    Deliberately no ML. Uncertainty here means the detector's own recognition
    confidence sits in the ambiguous band, or the human and the algorithm
    disagree. Those are the labels that actually teach the system something.
    """
    from ..history import store
    from ..structure.ranges import RangeIntelligenceEngine

    engine = RangeIntelligenceEngine()
    candidates: list[dict[str, Any]] = []

    for asset in Asset.tradables():
        for timeframe in (Timeframe.H4, Timeframe.D1):
            df = store.load_candles(asset, timeframe)
            if df.empty or len(df) < 200:
                continue
            # Sample recent history rather than every bar: the queue is for
            # human attention, and a hundred near-identical bars help nobody.
            for offset in range(0, min(400, len(df) - 160), 20):
                window = df.iloc[: len(df) - offset]
                try:
                    detected = engine.detect_from_frame(window)
                except Exception:
                    continue
                # The ambiguous band: confident enough to be worth looking at,
                # not confident enough to trust.
                if 40 <= detected.confidence <= 62:
                    candidates.append({
                        "asset": asset.value, "timeframe": timeframe.value,
                        "timestamp": str(window.index[-1]),
                        "range_type": detected.range_type.value,
                        "recognition_confidence": detected.confidence,
                        "valid": detected.valid,
                        "top": detected.top_zone.midpoint if detected.top_zone else None,
                        "bottom": (
                            detected.bottom_zone.midpoint if detected.bottom_zone else None
                        ),
                        "question": (
                            "Is this actually a range, and are these the right "
                            "boundaries?"
                        ),
                    })

    candidates.sort(key=lambda c: abs(c["recognition_confidence"] - 50))
    return {
        "queue": candidates[:limit],
        "total_candidates": len(candidates),
        "selection_rule": (
            "range recognition confidence between 40 and 62, ordered by closeness to "
            "50 - the cases where the detector is genuinely undecided"
        ),
        "note": (
            "Annotating confident cases teaches nothing. This queue exists so human "
            "effort goes where the algorithm is actually uncertain."
        ),
    }


def human_vs_algorithm() -> dict[str, Any]:
    """Compare human annotations with what the detectors saw at the same time."""
    from .alignment import market_context

    examples = [e for e in load_examples() if e.alignable]
    if len(examples) < 5:
        return {
            "status": "INSUFFICIENT_DATA",
            "examples_available": len(examples),
            "note": (
                f"{len(examples)} alignable examples. Precision, recall and F1 need a "
                "gold dataset of at least 50 well-aligned examples; reporting them on "
                "a handful would be meaningless."
            ),
        }

    comparisons: list[dict[str, Any]] = []
    for example in examples:
        context = market_context(example)
        if context is None:
            continue

        entry: dict[str, Any] = {
            "example_id": example.id,
            "asset": example.asset, "timeframe": example.timeframe,
            "market_timestamp": context.market_timestamp.isoformat(),
            "human_structure": example.structure_type,
            "algorithm_location": context.location_at_t,
            "algorithm_structure": context.structure_at_t,
            "human_range_top": example.range_top,
            "human_range_bottom": example.range_bottom,
            "algorithm_range_top": context.range_top_at_t,
            "algorithm_range_bottom": context.range_bottom_at_t,
        }

        # Level agreement, normalised by ATR so it is comparable across assets.
        if context.atr_at_t and context.atr_at_t > 0:
            if example.range_top and context.range_top_at_t:
                entry["range_top_distance_atr"] = round(
                    abs(example.range_top - context.range_top_at_t) / context.atr_at_t, 2
                )
            if example.range_bottom and context.range_bottom_at_t:
                entry["range_bottom_distance_atr"] = round(
                    abs(example.range_bottom - context.range_bottom_at_t) / context.atr_at_t, 2
                )

        human_says_range = (example.structure_type == "RANGE") or bool(
            example.range_top and example.range_bottom
        )
        algorithm_says_range = context.location_at_t not in (None, "NO_VALID_RANGE")
        entry["both_see_a_range"] = bool(human_says_range and algorithm_says_range)
        entry["agreement"] = (
            "AGREE" if human_says_range == algorithm_says_range else "DISAGREE"
        )
        comparisons.append(entry)

    if not comparisons:
        return {"status": "NO_ALIGNED_EXAMPLES"}

    agree = sum(1 for c in comparisons if c["agreement"] == "AGREE")
    distances = [
        c[key] for c in comparisons for key in
        ("range_top_distance_atr", "range_bottom_distance_atr") if key in c
    ]

    return {
        "status": "OK",
        "compared": len(comparisons),
        "agreement_rate_pct": round(agree / len(comparisons) * 100, 1),
        "median_level_distance_atr": (
            round(float(sorted(distances)[len(distances) // 2]), 2) if distances else None
        ),
        "comparisons": comparisons[:50],
        "metrics_note": (
            "Precision, recall and F1 are NOT reported: they need a labelled gold "
            "dataset with negative examples, which does not exist yet. Agreement rate "
            "on the available examples is descriptive only."
        ),
    }
