"""The rule that matters most: missing data is never replaced by a number."""

from __future__ import annotations

from crypto_intel.core.enums import Asset, Direction, Freshness, Reliability
from crypto_intel.engines.derivatives import DerivativesAnalyzer
from crypto_intel.engines.etf_flows import ETFFlowAnalyzer
from crypto_intel.engines.liquidity import DefiAnalyzer, StablecoinLiquidityAnalyzer
from crypto_intel.engines.macro import MacroAnalyzer
from crypto_intel.engines.news import NewsEngine
from crypto_intel.engines.onchain import OnChainAnalyzer
from crypto_intel.engines.regulation import RegulationAndPoliticsAnalyzer
from crypto_intel.engines.whales import WhaleAnalyzer


class TestEmptyInputsNeverFabricate:
    def test_etf(self):
        r = ETFFlowAnalyzer().analyze(Asset.BTC, [])
        assert r.available is False
        assert r.latest_total is None and r.ma_5d is None and r.cumulative_30d is None

    def test_derivatives(self):
        r = DerivativesAnalyzer().analyze(Asset.BTC, [])
        assert r.available is False
        assert r.funding_rate is None and r.open_interest is None
        assert r.funding_state == "UNAVAILABLE"

    def test_onchain(self):
        r = OnChainAnalyzer().analyze(Asset.ETH, [])
        assert r.available is False
        assert r.metrics == {}

    def test_liquidity(self):
        r = StablecoinLiquidityAnalyzer().analyze([])
        assert r.available is False
        assert r.total_supply is None

    def test_defi(self):
        r = DefiAnalyzer().analyze(Asset.SOL, [])
        assert r.available is False
        assert r.tvl is None

    def test_macro(self):
        r = MacroAnalyzer().analyze([])
        assert r.available is False
        assert r.metrics == {}

    def test_news(self):
        r = NewsEngine().analyze([])
        assert r.available is False
        assert r.clusters == []

    def test_regulation(self):
        r = RegulationAndPoliticsAnalyzer().analyze([])
        assert r.available is False
        assert r.events == []


class TestWhaleSignalsRequireASource:
    def test_no_provider_means_no_signal(self):
        """A fabricated whale signal is the most dangerous possible output."""
        r = WhaleAnalyzer().analyze(Asset.BTC, [])
        assert r.available is False
        assert r.signals == []
        assert r.exchange_netflow is None
        assert r.confidence == 0.0
        assert "not configured" in r.unavailable_reason

    def test_threshold_is_per_asset(self):
        """100 BTC and 50000 SOL are different amounts of conviction."""
        btc = WhaleAnalyzer().analyze(Asset.BTC, [])
        eth = WhaleAnalyzer().analyze(Asset.ETH, [])
        sol = WhaleAnalyzer().analyze(Asset.SOL, [])
        assert btc.threshold == 100 and btc.threshold_unit == "BTC"
        assert eth.threshold == 1000
        assert sol.threshold == 50000
        assert len({btc.threshold, eth.threshold, sol.threshold}) == 3

    def test_reliability_defaults_to_unverified(self):
        assert WhaleAnalyzer().analyze(Asset.BTC, []).reliability is Reliability.UNVERIFIED


class TestUnavailableIsNotNeutral:
    def test_inconclusive_differs_from_neutral(self):
        """'We cannot tell' is not the same claim as 'the market is balanced'."""
        r = ETFFlowAnalyzer().analyze(Asset.BTC, [])
        assert r.direction is Direction.INCONCLUSIVE
        assert r.direction is not Direction.NEUTRAL

    def test_unavailable_freshness_on_missing_data(self):
        assert OnChainAnalyzer().analyze(Asset.BTC, []).freshness is Freshness.UNAVAILABLE
