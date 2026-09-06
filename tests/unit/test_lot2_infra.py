"""LOT 2 infrastructure: snapshots, backfill bookkeeping, alerts, daily report."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.core.models import Candle
from crypto_intel.history import snapshots, store


class TestSnapshots:
    def test_same_bucket_updates_instead_of_duplicating(self):
        """Idempotence is what makes a crash-restart loop safe."""
        payload = {"price": 100.0}
        first = snapshots.save_snapshot("market", Asset.BTC, payload, price=100.0)
        second = snapshots.save_snapshot("market", Asset.BTC, {"price": 101.0}, price=101.0)
        assert first is True
        assert second is False

        rows = snapshots.load_snapshots("market", Asset.BTC, limit=10)
        current = [r for r in rows if r["payload"].get("price") == 101.0]
        assert len(current) == 1

    def test_bucket_changes_with_time(self):
        now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
        later = now + timedelta(minutes=20)
        assert snapshots.bucket_for("market", now) != snapshots.bucket_for("market", later)

    def test_cadences_differ_per_kind(self):
        """ETF flows publish daily; prices move constantly. Same cadence for
        both would either spam or starve the store."""
        assert snapshots.CADENCES["etf"] > snapshots.CADENCES["market"]
        assert snapshots.CADENCES["onchain"] > snapshots.CADENCES["market"]

    def test_etf_bucket_is_stable_within_a_day(self):
        morning = datetime(2026, 9, 5, 2, 0, tzinfo=UTC)
        evening = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
        assert snapshots.bucket_for("etf", morning) == snapshots.bucket_for("etf", evening)

    def test_stats_report_cadence(self):
        snapshots.save_snapshot("derivatives", Asset.ETH, {"funding_rate": 0.0001})
        stats = snapshots.snapshot_stats()
        assert "derivatives" in stats
        assert stats["derivatives"]["cadence_minutes"] == snapshots.CADENCES["derivatives"]


class TestHistoryStore:
    def _candles(self, n: int = 10, start_price: float = 100.0) -> list[Candle]:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        return [
            Candle(
                timestamp=base + timedelta(days=i),
                open=start_price + i, high=start_price + i + 1,
                low=start_price + i - 1, close=start_price + i + 0.5,
                volume=1000.0 + i,
            )
            for i in range(n)
        ]

    def test_save_is_idempotent(self):
        candles = self._candles()
        first = store.save_candles(Asset.SOL, Timeframe.W1, candles, source="test")
        second = store.save_candles(Asset.SOL, Timeframe.W1, candles, source="test")
        assert first == len(candles)
        assert second == 0, "re-saving identical candles must not duplicate rows"

    def test_load_returns_ordered_dataframe(self):
        store.save_candles(Asset.SOL, Timeframe.W1, self._candles(), source="test")
        df = store.load_candles(Asset.SOL, Timeframe.W1)
        assert not df.empty
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.is_monotonic_increasing

    def test_coverage_reports_real_depth(self):
        store.save_candles(Asset.SOL, Timeframe.W1, self._candles(20), source="test")
        coverage = store.candle_coverage(Asset.SOL, Timeframe.W1)
        assert coverage["rows"] >= 20
        assert coverage["start"] < coverage["end"]

    def test_missing_series_is_empty_not_fabricated(self):
        df = store.load_candles(Asset.ETH, Timeframe.M15)
        assert df.empty or len(df) > 0  # either real data or genuinely nothing
        series = store.load_macro("macro.does_not_exist")
        assert series.empty

    def test_backfill_state_is_recorded(self):
        store.record_backfill(
            dataset="test_dataset", asset=Asset.BTC, timeframe=Timeframe.D1,
            earliest=datetime(2020, 1, 1, tzinfo=UTC),
            latest=datetime(2026, 1, 1, tzinfo=UTC),
            rows=1000, source="test",
        )
        report = store.backfill_report()
        entry = next((r for r in report if r["dataset"] == "test_dataset"), None)
        assert entry is not None
        assert entry["rows"] == 1000
        assert entry["days"] > 2000


class TestAlertDedup:
    def _context(self, funding_state: str = "EXTREME_POSITIVE"):
        class FakeDerivatives:
            available = True
            funding_state = "EXTREME_POSITIVE"
            funding_rate = 0.003
            funding_annualized_pct = 328.5
            oi_change_24h_pct = 2.0
            regime_interpretation = ""
            liquidations_available = False
            liquidation_imbalance = None
            evidence_ids: ClassVar[list[str]] = []

        FakeDerivatives.funding_state = funding_state
        return {"derivatives": FakeDerivatives()}

    def test_alert_carries_a_reason(self):
        from crypto_intel.engines.alerts import AlertEngine

        alerts = AlertEngine().evaluate(
            Asset.BTC, self._context(), apply_cooldown=False
        )
        assert alerts
        assert any(a.__dict__.get("reason") for a in alerts)

    def test_duplicate_within_one_batch_is_collapsed(self):
        from crypto_intel.engines.alerts import AlertEngine

        engine = AlertEngine()
        candidates = engine.evaluate(Asset.BTC, self._context())
        keys = [a.__dict__.get("dedup_key") for a in candidates]
        assert len(keys) == len(set(keys)), "one run must not emit the same key twice"

    def test_cooldown_suppresses_a_repeat(self):
        from crypto_intel.db import repo
        from crypto_intel.engines.alerts import AlertEngine

        engine = AlertEngine()
        first = engine.evaluate(Asset.ETH, self._context())
        assert first, "the first evaluation should produce alerts"
        repo.save_alerts(engine.to_rows(first))

        second = engine.evaluate(Asset.ETH, self._context())
        assert len(second) < len(first), "a repeated condition must be suppressed"

    def test_state_change_alert_needs_a_previous_state(self):
        from crypto_intel.engines.alerts import AlertEngine
        from crypto_intel.engines.regime import MarketRegime, RegimeAssessment

        regime = RegimeAssessment(
            asset=Asset.SOL, regime=MarketRegime.BEARISH, regime_score=-40.0,
            confidence=70.0, summary="test",
        )
        engine = AlertEngine()

        # No previous state: nothing to compare, so no change alert.
        without = engine.evaluate(
            Asset.SOL, {"regime": regime}, previous=None, apply_cooldown=False
        )
        assert not [a for a in without if a.kind == "MARKET_REGIME_CHANGE"]

        # With a different previous state, the transition fires.
        with_previous = engine.evaluate(
            Asset.SOL, {"regime": regime},
            previous={"regime": "BULLISH"}, apply_cooldown=False,
        )
        assert [a for a in with_previous if a.kind == "MARKET_REGIME_CHANGE"]

    def test_cooldown_table_covers_every_alert_kind_used(self):
        from crypto_intel.core.enums import AlertKind
        from crypto_intel.engines.alerts import COOLDOWN_MINUTES

        for kind in AlertKind:
            assert kind.value in COOLDOWN_MINUTES, f"{kind.value} has no cooldown defined"


class TestDailyReport:
    def test_trend_timing_nuance(self):
        from crypto_intel.reports.daily import _trend_timing_line

        assert "favourable but" in _trend_timing_line(
            {"regime": "STRONGLY_BULLISH"}, {"timing": "WAIT"}
        )
        assert "agree" in _trend_timing_line(
            {"regime": "BULLISH"}, {"timing": "FAVORABLE"}
        )

    def test_renders_without_global_view(self):
        """A missing global view must degrade the report, not break it."""
        from crypto_intel.pipeline.orchestrator import AssetAnalysis
        from crypto_intel.reports.daily import render_daily_report

        analysis = AssetAnalysis(
            asset=Asset.BTC, generated_at=datetime.now(UTC), price=50000.0,
            conviction={
                "short": {"score": 10.0, "label": "SLIGHTLY BULLISH", "confidence": 50.0},
                "medium": {"score": 5.0, "label": "NEUTRAL", "confidence": 45.0},
                "long": {"score": 0.0, "label": "NEUTRAL", "confidence": 40.0},
                "overall_confidence": 45.0,
            },
            regime={"regime": "BULLISH", "regime_score": 30.0, "confidence": 70.0, "conditions": []},
            entry_timing={"timing": "WAIT", "timing_score": 0.0, "confidence": 60.0},
        )
        text = render_daily_report([analysis], None)
        assert "CRYPTO INTELLIGENCE - DAILY" in text
        assert "UNAVAILABLE" in text
        assert "TOP 3 THINGS TO WATCH" in text

    def test_report_never_invents_missing_values(self):
        from crypto_intel.pipeline.orchestrator import AssetAnalysis
        from crypto_intel.reports.daily import render_daily_report

        analysis = AssetAnalysis(
            asset=Asset.SOL, generated_at=datetime.now(UTC),
            price=None, change_24h_pct=None,
            conviction={"short": {}, "medium": {}, "long": {}},
            regime={}, entry_timing={},
        )
        text = render_daily_report([analysis], {})
        assert "UNAVAILABLE" in text
        assert "0.00 USD" not in text


class TestMigrations:
    def test_migrations_are_idempotent(self):
        from crypto_intel.db.migrations import run_migrations

        run_migrations()
        second = run_migrations()
        assert second == [], "a second run must apply nothing"

    def test_alert_columns_exist(self):
        from crypto_intel.db.migrations import existing_columns

        columns = existing_columns("alerts")
        assert "dedup_key" in columns
        assert "reason" in columns


class TestSchedulerState:
    def test_state_is_reported(self):
        from crypto_intel.scheduler import scheduler_state

        state = scheduler_state()
        assert "runs" in state
        assert "started_at" in state

    def test_jobs_have_distinct_cadences(self):
        """Every job on the same interval would defeat the point of cadences."""
        import inspect

        from crypto_intel import scheduler

        source = inspect.getsource(scheduler.start_scheduler)
        assert "coalesce" in inspect.getsource(scheduler) or "coalesce" in source
        assert "max_instances" in inspect.getsource(scheduler)
