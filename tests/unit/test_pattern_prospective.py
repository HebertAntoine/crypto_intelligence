"""The prospective pattern experiment starts now, never in historical data."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from crypto_intel.pattern_learning import ConsensusItem, ConsensusReport, ConsensusState
from crypto_intel.pattern_learning.ontology import StructuralPatternName
from crypto_intel.pattern_learning.prospective import (
    ELIGIBLE_PATTERNS,
    EXPERIMENT_ID,
    HORIZON_BARS,
    ensure_pattern_experiment,
    update_pattern_experiment,
)
from crypto_intel.research.live_experiments import LiveExperimentRegistry


def test_only_post_registration_agreements_are_recorded(tmp_path, monkeypatch):
    from crypto_intel.pattern_learning import prospective

    registry = LiveExperimentRegistry(tmp_path / "live.json")
    experiment = ensure_pattern_experiment(registry)
    index = pd.date_range("2026-01-01", periods=200, freq="h", tz="UTC")
    frame = pd.DataFrame({"close": np.linspace(200.0, 100.0, len(index))}, index=index)
    event_time = index[60].to_pydatetime()
    experiment.registered_at = index[50].isoformat()
    agreement = ConsensusItem(
        pattern=StructuralPatternName.DOUBLE_TOP,
        state=ConsensusState.INDEPENDENT_AGREEMENT,
        start_time=index[20].to_pydatetime(),
        end_time=index[55].to_pydatetime(),
        available_at=event_time,
        ours_id="ours",
        lmw_id="lmw",
        temporal_iou=0.8,
    )
    monkeypatch.setattr(prospective.store, "load_candles", lambda *args: frame)
    monkeypatch.setattr(prospective, "scan_cached", lambda *args: [])
    monkeypatch.setattr(prospective, "scan_lmw", lambda *args: [])
    monkeypatch.setattr(
        prospective,
        "compare_with_lmw",
        lambda *args: ConsensusReport(items=[agreement]),
    )

    first = update_pattern_experiment(registry)
    second = update_pattern_experiment(registry)

    stored = registry.all()[0]
    # Three simultaneous correlated assets represent one independent forward
    # window, and a second scheduler pass creates no duplicate.
    assert len(stored.observations) == 1
    assert first["maturity"]["observations_settled"] == 1
    assert second["maturity"]["observations_settled"] == 1
    assert all(item["outcome_pct"] > 0 for item in stored.observations)
    assert all(item["metadata"]["horizon_bars"] == HORIZON_BARS for item in stored.observations)


def test_an_agreement_before_registration_is_never_backfilled(tmp_path, monkeypatch):
    from crypto_intel.pattern_learning import prospective

    registry = LiveExperimentRegistry(tmp_path / "live.json")
    experiment = ensure_pattern_experiment(registry)
    experiment.registered_at = datetime(2026, 6, 1, tzinfo=UTC).isoformat()
    index = pd.date_range("2025-01-01", periods=200, freq="h", tz="UTC")
    frame = pd.DataFrame({"close": np.linspace(100.0, 120.0, len(index))}, index=index)
    old = ConsensusItem(
        pattern=StructuralPatternName.DOUBLE_BOTTOM,
        state=ConsensusState.INDEPENDENT_AGREEMENT,
        start_time=index[10].to_pydatetime(),
        end_time=index[20].to_pydatetime(),
        available_at=index[21].to_pydatetime(),
    )
    monkeypatch.setattr(prospective.store, "load_candles", lambda *args: frame)
    monkeypatch.setattr(prospective, "scan_cached", lambda *args: [])
    monkeypatch.setattr(prospective, "scan_lmw", lambda *args: [])
    monkeypatch.setattr(
        prospective,
        "compare_with_lmw",
        lambda *args: ConsensusReport(items=[old]),
    )

    update_pattern_experiment(registry)

    assert registry.all()[0].observations == []
    assert registry.all()[0].id == EXPERIMENT_ID


def test_registered_rule_does_not_expand_when_new_templates_are_added(
    tmp_path, monkeypatch
):
    from crypto_intel.pattern_learning import prospective

    assert StructuralPatternName.BULL_FLAG not in ELIGIBLE_PATTERNS
    registry = LiveExperimentRegistry(tmp_path / "live.json")
    experiment = ensure_pattern_experiment(registry)
    index = pd.date_range("2026-01-01", periods=200, freq="h", tz="UTC")
    frame = pd.DataFrame({"close": np.linspace(100.0, 150.0, len(index))}, index=index)
    experiment.registered_at = index[50].isoformat()
    new_family = ConsensusItem(
        pattern=StructuralPatternName.BULL_FLAG,
        state=ConsensusState.INDEPENDENT_AGREEMENT,
        start_time=index[40].to_pydatetime(),
        end_time=index[59].to_pydatetime(),
        available_at=index[60].to_pydatetime(),
    )
    monkeypatch.setattr(prospective.store, "load_candles", lambda *args: frame)
    monkeypatch.setattr(prospective, "scan_cached", lambda *args: [])
    monkeypatch.setattr(prospective, "scan_lmw", lambda *args: [])
    monkeypatch.setattr(
        prospective,
        "compare_with_lmw",
        lambda *args: ConsensusReport(items=[new_family]),
    )

    update_pattern_experiment(registry)

    assert registry.all()[0].observations == []
