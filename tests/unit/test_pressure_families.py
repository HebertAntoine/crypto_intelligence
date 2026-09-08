"""Les cinq familles, de la base de données jusqu'au titre affiché.

Deux questions distinctes sont tenues ici :

  * le câblage résout-il réellement une famille quand la donnée existe — la
    carte affichait « 1/5 » alors que quatre des cinq sources étaient
    disponibles ou obtenables ;
  * une famille sans source reste-t-elle absente — aucune valeur n'est
    fabriquée, estimée ou renommée pour remplir un compteur.

Le second point est le plus important. Un cinq sur cinq obtenu en inventant un
chiffre serait strictement pire qu'un trois sur cinq honnête.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.core.enums import Asset, Timeframe
from crypto_intel.core.models import Candle
from crypto_intel.engines.market_pressure import (
    WEIGHTS,
    Direction,
    assess_pressure,
)
from crypto_intel.history import store

FAMILIES = ("institutions", "spot", "derivatives", "funding", "whales")


@pytest.fixture(scope="module")
def local_series():
    """Des séries réalistes pour les quatre familles réellement obtenables."""
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    for asset, base in ((Asset.BTC, 60000.0), (Asset.ETH, 3000.0), (Asset.SOL, 120.0)):
        store.save_candles(asset, Timeframe.D1, [
            Candle(
                timestamp=end - timedelta(days=399 - i),
                open=base * (1 + i * .001), high=base * (1 + i * .001) * 1.01,
                low=base * (1 + i * .001) * .99, close=base * (1 + i * .001),
                volume=1000 + i,
            )
            for i in range(400)
        ], "test")
        # Funding réglé toutes les huit heures, dernier règlement il y a 3 h.
        store.save_derivatives(asset, "funding.rate", [
            (end - timedelta(hours=3 + 8 * i), 0.0001 * (1 + (i % 5)))
            for i in range(300)
        ], "test")
        store.save_derivatives(asset, "oi.contracts_bybit", [
            (end - timedelta(hours=i), 1_000_000 + i * 100) for i in range(300)
        ], "test")
        # Agressivité spot: bougies journalières, la dernière est celle du jour.
        store.save_derivatives(asset, "spot.taker_buy_ratio", [
            (end - timedelta(days=i), 0.50 + (0.01 if i < 5 else 0.0))
            for i in range(200)
        ], "test")
        store.save_derivatives(asset, "derivatives.long_account_share", [
            (end - timedelta(hours=4 * i), 0.52 - 0.001 * i) for i in range(60)
        ], "test")
    yield


def _assess(asset: Asset, **kwargs):
    return assess_pressure(
        asset, funding_percentile=kwargs.pop("percentile", 70),
        leverage_state=kwargs.pop("leverage_state", "NEW_LONGS"), **kwargs,
    )


class TestTheWiringResolvesWhatExists:
    @pytest.mark.parametrize("asset", list(Asset.tradables()), ids=lambda a: a.value)
    def test_the_four_obtainable_families_resolve(self, local_series, asset):
        """Trois sur quatre au minimum, et les raisons nommées pour le reste."""
        out = _assess(asset)
        resolved = {item.family for item in out.measured}
        # Les ETF ne sont pas seedés ici; spot, dérivés et funding le sont.
        assert {"spot", "derivatives", "funding"} <= resolved, (
            f"{asset.value}: familles non résolues, "
            f"raisons={[(i.family, i.reason) for i in out.families if not i.available]}"
        )

    def test_spot_reads_the_series_the_backfill_writes(self, local_series):
        out = _assess(Asset.BTC)
        spot = next(item for item in out.families if item.family == "spot")
        assert spot.available is True
        assert "taker" in spot.source.lower()
        assert spot.raw_value["taker_buy_ratio"] is not None
        assert spot.observation_time

    def test_derivatives_reads_open_interest_and_account_positioning(self, local_series):
        out = _assess(Asset.BTC)
        derivatives = next(
            item for item in out.families if item.family == "derivatives"
        )
        assert derivatives.available is True
        assert derivatives.raw_value["long_account_share"] is not None
        assert derivatives.raw_value["oi_change_7d_pct"] is not None

    def test_funding_stays_usable_across_its_eight_hour_cycle(self, local_series):
        """Une valeur de trois heures est la valeur courante, pas une périmée."""
        out = _assess(Asset.BTC)
        funding = next(item for item in out.families if item.family == "funding")
        assert funding.available is True
        assert funding.freshness in ("LIVE", "RECENT")

    @pytest.mark.parametrize("asset", list(Asset.tradables()), ids=lambda a: a.value)
    def test_every_family_is_accounted_for(self, local_series, asset):
        out = _assess(asset)
        assert {item.family for item in out.families} == set(FAMILIES)
        for item in out.families:
            # Disponible, sans objet, ou absente avec sa raison. Jamais un
            # silence.
            assert item.available or not item.applicable or item.reason


class TestNothingIsInvented:
    """Un cinq sur cinq obtenu par fabrication serait pire qu'un trois honnête."""

    @pytest.mark.parametrize("asset", list(Asset.tradables()), ids=lambda a: a.value)
    def test_whales_stay_absent_without_a_provider(self, local_series, asset):
        whales = next(
            item for item in _assess(asset).families if item.family == "whales"
        )
        assert whales.available is False
        assert whales.normalized_score is None
        assert whales.weighted_contribution is None
        assert "payant" in whales.reason

    def test_no_family_sources_a_fixture_or_a_mock(self, local_series):
        for asset in Asset.tradables():
            for item in _assess(asset).families:
                source = (item.source or "").upper()
                for forbidden in ("MOCK", "SYNTHETIC", "FIXTURE", "SAMPLE"):
                    assert forbidden not in source, (
                        f"{asset.value}/{item.family} sourcé {item.source}"
                    )

    def test_an_absent_family_never_reaches_the_denominator(self, local_series):
        out = _assess(Asset.BTC)
        assert out.denominator == pytest.approx(
            sum(WEIGHTS[item.family] for item in out.measured)
        )
        for item in out.families:
            if not item.available:
                assert item.weighted_contribution is None

    def test_sol_is_not_charged_for_an_etf_that_does_not_exist(self, local_series):
        out = _assess(Asset.SOL)
        institutions = next(
            item for item in out.families if item.family == "institutions"
        )
        assert institutions.applicable is False
        assert len(out.applicable) == 4


class TestPressureNeverOverridesTiming:
    """Direction haussière, pression acheteuse et timing « attendre » coexistent."""

    def test_buying_pressure_does_not_turn_a_wait_into_an_opportunity(self):
        from types import SimpleNamespace

        from crypto_intel.engines.buy_opportunity import BuyOpportunityState, decide


        # Une configuration que la pression pourrait plausiblement relever.
        entry = SimpleNamespace(
            state="FAVORABLE", score=42.0, factors=[], missing=[],
            asset="BTC", timeframe="4h",
        )
        strong_buying = assess_pressure(
            Asset.BTC, funding_percentile=95, leverage_state="NEW_LONGS"
        )
        out = decide(
            Asset.BTC,
            entry=entry,
            edge=SimpleNamespace(state="NO_MEASURABLE_EDGE", admitted_count=0, rejected_count=4),
            uncertainty=SimpleNamespace(score=65.0),
            macro_events=[], crowding=SimpleNamespace(level="NORMAL", score=40.0),
            pressure=strong_buying, unusable_families=[],
            regime=SimpleNamespace(regime=SimpleNamespace(value="STRONGLY_BULLISH"), confidence=85.0),
        )
        # L'entrée est favorable et la pression acheteuse, mais l'incertitude
        # plafonne à « attendre »: la pression est un contexte, pas un signal
        # qui écraserait le timing.
        assert out.state is BuyOpportunityState.WAIT
        assert any("Incertitude" in rail for rail in out.guard_rails_applied), (
            f"aucun garde-fou nommé: {out.guard_rails_applied}"
        )

    def test_the_three_readings_stay_separate_in_the_payload(self, local_series):
        from crypto_intel.engines.market_pressure import CoverageLevel

        out = _assess(Asset.BTC)
        payload = out.to_dict()
        # Pression et couverture sont deux nombres, jamais fusionnés.
        assert payload["pressure_score"] is not None
        assert payload["coverage"]["ratio"] is not None
        assert payload["coverage"]["level"] in {level.value for level in CoverageLevel}


class TestDataHealth:
    def test_every_asset_reports_every_source(self):
        from crypto_intel.core.data_health import check

        for asset in Asset.tradables():
            sources = {item.source for item in check(asset)}
            assert {
                "OHLCV_1D", "OHLCV_4H", "OHLCV_1H", "FUNDING", "OPEN_INTEREST",
                "SPOT", "ACCOUNTS", "ETF", "ONCHAIN", "WHALES", "MACRO",
            } <= sources

    def test_not_applicable_is_never_counted_as_missing(self):
        from crypto_intel.core.data_health import HealthStatus, check

        sol = {item.source: item for item in check(Asset.SOL)}
        assert sol["DVOL"].status is HealthStatus.NOT_APPLICABLE
        assert sol["ETF"].status is HealthStatus.NOT_APPLICABLE
        assert sol["DVOL"].detail and sol["ETF"].detail

    def test_the_report_separates_actionable_from_structural(self):
        from crypto_intel.core.data_health import report

        payload = report()
        assert set(payload["counts"]) == {
            "OK", "STALE", "UNAVAILABLE", "NOT_APPLICABLE", "ERROR"
        }
        assert "NOT_APPLICABLE" in payload["note"]

    def test_a_future_timestamp_is_an_error_not_freshness(self):
        from crypto_intel.core.data_health import HealthStatus, _classify

        status, _ = _classify(datetime.now(UTC) + timedelta(hours=5), 8.0, 10)
        assert status is HealthStatus.ERROR


class TestTheSchedulerRefreshesWhatThePageReads:
    def test_every_pressure_family_series_has_a_job(self):
        """Une famille câblée sans travail planifié se périme en silence."""
        import inspect

        from crypto_intel import scheduler

        source = inspect.getsource(scheduler.job_derivatives_sync)
        for call in (
            "backfill_funding", "backfill_open_interest",
            "backfill_bybit_open_interest", "backfill_spot_taker_flow",
            "backfill_long_short_accounts",
        ):
            assert call in source, f"{call} n'est appelé par aucun travail planifié"

    def test_the_jobs_are_registered_with_a_cadence(self):
        import inspect

        from crypto_intel import scheduler

        source = inspect.getsource(scheduler.start_scheduler)
        for job in ("derivatives_sync", "ohlcv_sync", "etf_sync"):
            assert f'"{job}"' in source

    def test_a_provider_failure_never_recycles_an_old_value_as_current(self):
        """Une panne laisse la famille absente, elle ne rejoue pas la dernière."""
        from crypto_intel.engines.market_pressure import _funding

        # Série vide: aucune valeur à recycler, et rien n'est inventé.
        item = _funding(Asset.BTC, None)
        assert item.available is False
        assert item.normalized_score is None
        assert item.direction is Direction.UNAVAILABLE


def test_the_backfills_are_importable_and_named_for_what_they_fetch():
    from crypto_intel.history import backfill

    assert asyncio.iscoroutinefunction(backfill.backfill_spot_taker_flow)
    assert asyncio.iscoroutinefunction(backfill.backfill_long_short_accounts)
