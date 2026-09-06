"""Pipeline: collect -> compute -> analyse -> score -> synthesise -> report.

Collection runs concurrently per capability because the bottleneck is network
latency. Everything downstream is ordinary synchronous computation.

Provider failures never abort a run: each capability's failure reason is
carried through to the report as an explicit UNAVAILABLE, which is the whole
point - the user must see what is missing, not a silently thinner analysis.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from ..analysts.base import AnalystResult
from ..analysts.chief import ChiefMarketAnalyst, ChiefSynthesis
from ..analysts.evidence_confrontation import EvidenceConfrontationEngine
from ..analysts.specialists import (
    DefiAnalyst,
    DerivativesAnalyst,
    ETFAnalyst,
    HistoricalAnalyst,
    LiquidityAnalyst,
    MacroAnalyst,
    NewsAnalyst,
    OnChainAnalyst,
    RegulationAnalyst,
    TechnicalAnalyst,
    WhaleAnalyst,
)
from ..config_loader import asset_meta
from ..core.enums import Asset, FetchStatus, Timeframe
from ..core.models import Observation
from ..db import repo
from ..engines.alerts import AlertEngine
from ..engines.contradictions import ContradictionEngine, ContradictionReport
from ..engines.conviction import ConvictionResult, MarketConvictionEngine
from ..engines.derivatives import DerivativesAnalyzer
from ..engines.edge import (
    EdgeEngine,
    UncertaintyEngine,
    build_decision_summary,
)
from ..engines.empirical import EmpiricalTimingLayer, assess_probability
from ..engines.entry_timing import EntryTimingAssessment, EntryTimingEngine
from ..engines.etf_flows import ETFFlowAnalyzer
from ..engines.etf_split import ETFSplitEngine
from ..engines.geopolitics import GeopoliticalRiskAnalyzer
from ..engines.historical import HistoricalSimilarityEngine
from ..engines.leverage import LeverageCrowdingEngine
from ..engines.liquidity import DefiAnalyzer, StablecoinLiquidityAnalyzer
from ..engines.macro import MacroAnalyzer
from ..engines.mtf import MTFResult, MultiTimeframeEngine
from ..engines.news import NewsEngine
from ..engines.onchain import OnChainAnalyzer
from ..engines.regime import MarketRegimeEngine, RegimeAssessment
from ..engines.regulation import RegulationAndPoliticsAnalyzer
from ..engines.rsi_context import RSIContextEngine
from ..engines.scoring import ScoringEngine
from ..engines.technical.engine import TechnicalAnalysisEngine, TechnicalSnapshot
from ..engines.volatility import VolatilityRegimeEngine
from ..engines.whales import WhaleAnalyzer
from ..llm.factory import get_llm
from ..logging_setup import get_logger
from ..providers.base import FetchRequest, FetchResult
from ..providers.registry import get_registry

log = get_logger("pipeline")

TIMEFRAMES = [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1]


class SourceStatus(BaseModel):
    capability: str
    ok: bool
    provider: str = ""
    status: str = ""
    message: str = ""
    observations: int = 0


class AssetAnalysis(BaseModel):
    """Everything the pipeline produced for one asset."""

    asset: Asset
    generated_at: datetime
    price: float | None = None
    change_24h_pct: float | None = None
    change_7d_pct: float | None = None
    market_cap: float | None = None
    volume_24h: float | None = None
    market_regime: str = "UNDETERMINED"
    # LOT 2: trend and timing are two independent answers.
    regime: dict[str, Any] = Field(default_factory=dict)
    entry_timing: dict[str, Any] = Field(default_factory=dict)
    # LOT 3: measured context rather than assumed meaning.
    etf_split: dict[str, Any] = Field(default_factory=dict)
    rsi_context: dict[str, Any] = Field(default_factory=dict)
    empirical: dict[str, Any] = Field(default_factory=dict)
    probability: dict[str, Any] = Field(default_factory=dict)
    confrontations: list[dict[str, Any]] = Field(default_factory=list)
    # LOT 4: what has actually been MEASURED, kept apart from direction.
    edge: dict[str, Any] = Field(default_factory=dict)
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    decision_summary: dict[str, Any] = Field(default_factory=dict)
    crowding: dict[str, Any] = Field(default_factory=dict)
    leverage_state: dict[str, Any] = Field(default_factory=dict)
    funding_context: dict[str, Any] = Field(default_factory=dict)
    volatility_regime: dict[str, Any] = Field(default_factory=dict)

    scores: dict[str, Any] = Field(default_factory=dict)
    conviction: dict[str, Any] = Field(default_factory=dict)
    analysts: dict[str, Any] = Field(default_factory=dict)
    contradictions: dict[str, Any] = Field(default_factory=dict)
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    synthesis: dict[str, Any] = Field(default_factory=dict)
    technical: dict[str, Any] = Field(default_factory=dict)
    domains: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceStatus] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    llm_used: bool = False
    report_id: str = ""


class Pipeline:
    def __init__(self) -> None:
        self.registry = get_registry()
        self.tech = TechnicalAnalysisEngine()
        self.mtf = MultiTimeframeEngine()
        self.etf = ETFFlowAnalyzer()
        self.deriv = DerivativesAnalyzer()
        self.onchain = OnChainAnalyzer()
        self.liquidity = StablecoinLiquidityAnalyzer()
        self.defi = DefiAnalyzer()
        self.macro = MacroAnalyzer()
        self.regulation = RegulationAndPoliticsAnalyzer()
        self.news = NewsEngine()
        self.whales = WhaleAnalyzer()
        self.geo = GeopoliticalRiskAnalyzer()
        self.historical = HistoricalSimilarityEngine()
        self.scoring = ScoringEngine()
        self.conviction = MarketConvictionEngine()
        self.contradictions = ContradictionEngine()
        self.alerts = AlertEngine()
        self.regime_engine = MarketRegimeEngine()
        self.timing_engine = EntryTimingEngine()
        self.etf_split = ETFSplitEngine()
        self.rsi_context = RSIContextEngine()
        self.empirical = EmpiricalTimingLayer()
        self.confrontation = EvidenceConfrontationEngine()
        self.leverage = LeverageCrowdingEngine()
        self.volatility = VolatilityRegimeEngine()
        self.edge = EdgeEngine()
        self.uncertainty = UncertaintyEngine()

    # --- collection --------------------------------------------------------

    async def _fetch(self, capability: str, asset: Asset | None = None,
                     timeframe: Timeframe | None = None, limit: int = 300) -> FetchResult:
        return await self.registry.fetch(
            FetchRequest(capability=capability, asset=asset, timeframe=timeframe, limit=limit)
        )

    async def collect_asset(self, asset: Asset) -> dict[str, Any]:
        """Fetch everything for one asset, concurrently."""
        meta = asset_meta(asset.value)
        onchain_cap = {"BTC": "onchain.btc", "ETH": "onchain.eth", "SOL": "onchain.sol"}[asset.value]

        tasks: dict[str, Any] = {}
        for tf in TIMEFRAMES:
            bars = 400 if tf in (Timeframe.D1, Timeframe.W1) else 300
            tasks[f"ohlcv_{tf.value}"] = self._fetch("market.ohlcv", asset, tf, bars)

        tasks["ticker"] = self._fetch("market.ticker", asset)
        tasks["marketcap"] = self._fetch("market.marketcap", asset)
        tasks["funding"] = self._fetch("derivatives.funding", asset)
        tasks["oi"] = self._fetch("derivatives.oi", asset)
        tasks["ratio"] = self._fetch("derivatives.ratio", asset)
        tasks["liquidations"] = self._fetch("derivatives.liquidations", asset)
        tasks["onchain"] = self._fetch(onchain_cap, asset)
        tasks["whales"] = self._fetch("whales.flows", asset)
        if meta.get("has_etf"):
            tasks["etf"] = self._fetch("etf.flows", asset)
        if asset is not Asset.BTC:   # BTC L1 has no meaningful DeFi TVL
            tasks["tvl"] = self._fetch("defi.tvl", asset)
            tasks["dex"] = self._fetch("defi.dex", asset)
            tasks["fees"] = self._fetch("defi.fees", asset)

        keys = list(tasks)
        results = await asyncio.gather(*(tasks[k] for k in keys), return_exceptions=True)

        out: dict[str, FetchResult] = {}
        for key, res in zip(keys, results, strict=True):
            if isinstance(res, BaseException):
                log.warning("collect_task_failed", key=key, asset=asset.value, error=str(res))
                out[key] = FetchResult.failure(FetchStatus.NETWORK_ERROR, "pipeline", str(res))
            else:
                out[key] = res
        return out

    async def collect_global(self) -> dict[str, FetchResult]:
        # Keep the events table in sync with the YAML calendar so the API and
        # dashboard can show upcoming catalysts.
        try:
            self.macro.sync_calendar_to_db()
        except Exception as exc:
            log.warning("calendar_sync_failed", error=str(exc))

        tasks = {
            "stablecoins": self._fetch("stablecoins.supply"),
            "macro_series": self._fetch("macro.series"),
            "macro_indices": self._fetch("macro.indices"),
            "news": self._fetch("news.feed"),
            "regulation": self._fetch("regulation.feed"),
            "rwa": self._fetch("defi.rwa"),
            "global": self._fetch("market.global"),
        }
        keys = list(tasks)
        results = await asyncio.gather(*(tasks[k] for k in keys), return_exceptions=True)
        out: dict[str, FetchResult] = {}
        for key, res in zip(keys, results, strict=True):
            if isinstance(res, BaseException):
                out[key] = FetchResult.failure(FetchStatus.NETWORK_ERROR, "pipeline", str(res))
            else:
                out[key] = res
        return out

    def persist(self, results: dict[str, FetchResult]) -> int:
        observations: list[Observation] = []
        for res in results.values():
            if res.ok:
                observations.extend(res.observations)
        if not observations:
            return 0
        try:
            return repo.save_observations(observations)
        except Exception as exc:
            log.warning("persist_failed", error=str(exc))
            return 0

    # --- analysis ----------------------------------------------------------

    async def analyze_asset(
        self, asset: Asset, global_data: dict[str, FetchResult] | None = None
    ) -> AssetAnalysis:
        now = datetime.now(UTC)
        data = await self.collect_asset(asset)
        gdata = global_data if global_data is not None else await self.collect_global()
        self.persist(data)
        self.persist(gdata)

        sources: list[SourceStatus] = []
        for key, res in {**data, **gdata}.items():
            sources.append(SourceStatus(
                capability=key, ok=res.ok, provider=res.provider,
                status=res.status.value,
                message="" if res.ok else res.user_message,
                observations=len(res.observations),
            ))

        # --- technical -----------------------------------------------------
        snapshots: dict[Timeframe, TechnicalSnapshot | None] = {}
        daily_df: pd.DataFrame | None = None
        for tf in TIMEFRAMES:
            res = data.get(f"ohlcv_{tf.value}")
            if res and res.ok and res.raw is not None:
                snap = self.tech.analyze(res.raw)
                snapshots[tf] = snap
                if tf is Timeframe.D1:
                    daily_df = self.tech.to_dataframe(res.raw)
            else:
                snapshots[tf] = None

        mtf: MTFResult = self.mtf.analyze(asset, {k: v for k, v in snapshots.items() if v})

        daily = snapshots.get(Timeframe.D1)
        price = daily.price if daily and daily.has_data else None
        change_24h = daily.change_24h_pct if daily and daily.has_data else None
        change_7d = daily.change_7d_pct if daily and daily.has_data else None

        ticker = data.get("ticker")
        if ticker and ticker.ok:
            for o in ticker.observations:
                if o.metric == "price.last" and o.numeric_value:
                    price = o.numeric_value
                elif o.metric == "price.change_24h_pct" and o.numeric_value is not None:
                    change_24h = o.numeric_value

        market_cap = volume_24h = None
        mc = data.get("marketcap")
        if mc and mc.ok:
            for o in mc.observations:
                if o.metric == "market.cap":
                    market_cap = o.numeric_value
                elif o.metric == "market.volume_24h":
                    volume_24h = o.numeric_value
                elif o.metric == "market.change_7d_pct" and change_7d is None:
                    change_7d = o.numeric_value

        # --- domain engines -------------------------------------------------
        price_history = []
        d1 = data.get("ohlcv_1d")
        if d1 and d1.ok and d1.raw:
            price_history = [(c.timestamp, c.close) for c in d1.raw.candles]

        etf_res = data.get("etf")
        etf_analysis = self.etf.analyze(
            asset,
            etf_res.observations if etf_res and etf_res.ok else [],
            price_history,
            unavailable_reason=(
                None if (etf_res and etf_res.ok)
                else (etf_res.user_message if etf_res
                      else f"UNAVAILABLE - {asset.value} has no US spot ETF")
            ),
        )

        deriv_obs: list[Observation] = []
        deriv_failed = []
        for key in ("funding", "oi", "ratio", "liquidations"):
            r = data.get(key)
            if r and r.ok:
                deriv_obs.extend(r.observations)
            elif r:
                deriv_failed.append(f"{key}: {r.user_message}")
        deriv_analysis = self.deriv.analyze(
            asset, deriv_obs, change_24h,
            unavailable_reason=None if deriv_obs else "; ".join(deriv_failed) or "UNAVAILABLE",
        )

        oc = data.get("onchain")
        onchain_analysis = self.onchain.analyze(
            asset, oc.observations if oc and oc.ok else [],
            unavailable_reason=None if (oc and oc.ok) else (oc.user_message if oc else "UNAVAILABLE"),
        )

        stables = gdata.get("stablecoins")
        liquidity_analysis = self.liquidity.analyze(
            stables.observations if stables and stables.ok else [],
            unavailable_reason=None if (stables and stables.ok)
            else (stables.user_message if stables else "UNAVAILABLE"),
        )

        defi_obs: list[Observation] = []
        for key in ("tvl", "dex", "fees"):
            r = data.get(key)
            if r and r.ok:
                defi_obs.extend(r.observations)
        defi_analysis = self.defi.analyze(
            asset, defi_obs, change_7d,
            unavailable_reason=(
                None if defi_obs
                else ("DeFi TVL is not a meaningful metric for Bitcoin L1"
                      if asset is Asset.BTC else "UNAVAILABLE - no DeFi data")
            ),
        )

        macro_obs: list[Observation] = []
        for key in ("macro_series", "macro_indices"):
            r = gdata.get(key)
            if r and r.ok:
                macro_obs.extend(r.observations)
        macro_analysis = self.macro.analyze(
            macro_obs, now,
            unavailable_reason=None if macro_obs else "UNAVAILABLE - no macro data",
        )

        reg_res = gdata.get("regulation")
        reg_items = (reg_res.raw or {}).get("items", []) if reg_res and reg_res.raw else []
        regulation_analysis = self.regulation.analyze(
            reg_items, asset, now,
            unavailable_reason=None if reg_items else (
                reg_res.user_message if reg_res else "UNAVAILABLE - no regulatory feed"
            ),
        )

        news_res = gdata.get("news")
        news_items = (news_res.raw or {}).get("items", []) if news_res and news_res.raw else []
        news_analysis = self.news.analyze(
            news_items, asset,
            unavailable_reason=None if news_items else (
                news_res.user_message if news_res else "UNAVAILABLE - no news feed"
            ),
        )
        geo_analysis = self.geo.analyze(
            news_items + reg_items, now,
            unavailable_reason=None if (news_items or reg_items) else "UNAVAILABLE - no feeds",
        )

        whale_res = data.get("whales")
        whale_analysis = self.whales.analyze(
            asset, whale_res.observations if whale_res and whale_res.ok else [],
            unavailable_reason=None if (whale_res and whale_res.ok)
            else (whale_res.user_message if whale_res else None),
        )

        historical_analysis = None
        if daily_df is not None:
            historical_analysis = self.historical.analyze(asset, daily_df, Timeframe.D1)

        # --- scoring --------------------------------------------------------
        # Price observations back the technical score, so the WHY? panel can
        # show which candles and sources it rests on.
        technical_evidence = [
            o.id
            for tf in TIMEFRAMES
            for o in (data.get(f"ohlcv_{tf.value}").observations
                      if data.get(f"ohlcv_{tf.value}") and data[f"ohlcv_{tf.value}"].ok else [])
        ]
        ticker_res = data.get("ticker")
        if ticker_res and ticker_res.ok:
            technical_evidence.extend(o.id for o in ticker_res.observations)
        technical_card = self.scoring.technical(
            mtf, {k: v for k, v in snapshots.items() if v}, technical_evidence
        )
        cards = {
            "technical": technical_card,
            "etf": self.scoring.from_analysis("etf", etf_analysis, 90.0),
            "derivatives": self.scoring.from_analysis("derivatives", deriv_analysis, 85.0),
            "onchain": self.scoring.from_analysis("onchain", onchain_analysis, 80.0),
            "liquidity": self.scoring.from_analysis("liquidity", liquidity_analysis, 82.0),
            "defi": self.scoring.from_analysis("defi", defi_analysis, 80.0),
            "macro": self.scoring.from_analysis("macro", macro_analysis, 85.0),
            "regulation": self.scoring.from_analysis("regulation", regulation_analysis, 75.0),
            "news": self.scoring.from_analysis("news", news_analysis, 55.0),
            "whale": self.scoring.from_analysis("whale", whale_analysis, 50.0),
        }

        context: dict[str, Any] = {
            "snapshots": {k: v for k, v in snapshots.items() if v},
            "mtf": mtf, "technical_card": technical_card,
            "etf": etf_analysis, "derivatives": deriv_analysis, "onchain": onchain_analysis,
            "liquidity": liquidity_analysis, "defi": defi_analysis, "macro": macro_analysis,
            "regulation": regulation_analysis, "news": news_analysis, "whale": whale_analysis,
            "geopolitics": geo_analysis, "historical": historical_analysis,
            "price": price, "change_24h": change_24h, "change_7d": change_7d,
        }

        # Market regime and entry timing are computed from the same context but
        # deliberately kept independent: a strong trend can coincide with a poor
        # moment to enter, and collapsing the two would hide exactly that.
        regime_assessment: RegimeAssessment = self.regime_engine.assess(asset, context)
        timing_assessment: EntryTimingAssessment = self.timing_engine.assess(asset, context)
        context["regime"] = regime_assessment
        context["entry_timing"] = timing_assessment

        # ETF context and predictive value are separate answers: participation
        # can be strong while carrying no measured forward information.
        etf_split_result = self.etf_split.split(asset, etf_analysis)
        context["etf_split"] = etf_split_result

        # RSI read against measured history for this asset and regime, not
        # against the textbook rule.
        daily_snapshot = snapshots.get(Timeframe.D1)
        rsi_reading = None
        if daily_snapshot is not None and daily_snapshot.has_data:
            rsi_reading = self.rsi_context.interpret(
                asset, daily_snapshot.rsi, regime_assessment.regime.value, Timeframe.D1
            )
        context["rsi_context"] = rsi_reading

        # What actually followed configurations resembling this one.
        try:
            empirical_result = self.empirical.analyse(asset)
        except Exception as exc:
            log.warning("empirical_layer_failed", asset=asset.value, error=str(exc))
            empirical_result = None
        context["empirical"] = empirical_result

        # Leverage, crowding and volatility regime: risk context that is true
        # regardless of direction.
        crowding_assessment = self.leverage.crowding(asset)
        leverage_state = self.leverage.leverage_state(asset)
        funding_context = self.leverage.funding_context(asset)
        volatility_assessment = self.volatility.assess(asset)
        context["crowding"] = crowding_assessment
        context["leverage_state"] = leverage_state
        context["funding_context"] = funding_context
        context["volatility_regime"] = volatility_assessment

        contradiction_report: ContradictionReport = self.contradictions.detect(
            cards,
            {
                "price_change_24h_pct": change_24h,
                "funding_state": deriv_analysis.funding_state if deriv_analysis.available else None,
                "volume_state": daily.volume_state if daily and daily.has_data else None,
                "etf_divergence": etf_analysis.flow_price_divergence if etf_analysis.available else None,
                "whale_behaviour": whale_analysis.behaviour if whale_analysis.available else None,
                "tvl_divergence": defi_analysis.tvl_price_divergence if defi_analysis.available else None,
                "mtf_conflicts": mtf.conflicts,
            },
        )
        context["contradictions"] = contradiction_report

        conviction: ConvictionResult = self.conviction.compute(
            asset, cards, contradiction_report.max_strength
        )

        # Whether any edge has actually been MEASURED - answered from research
        # output only, never from today's regime. A bullish market with no
        # tested signal must come out as NO_MEASURABLE_EDGE.
        edge_assessment = self.edge.assess(asset)
        uncertainty_assessment = self.uncertainty.assess(
            asset, edge_assessment,
            regime=regime_assessment,
            contradictions=contradiction_report.contradictions,
            freshness={c.domain: c.freshness for c in cards if hasattr(c, "freshness")},
            crowding=crowding_assessment,
        )
        decision_summary = build_decision_summary(
            asset, edge_assessment, uncertainty_assessment,
            regime=regime_assessment, timing=timing_assessment,
            crowding=crowding_assessment, volatility=volatility_assessment,
        )
        context["edge"] = edge_assessment
        context["uncertainty"] = uncertainty_assessment
        context["decision_summary"] = decision_summary

        # --- analysts -------------------------------------------------------
        llm = get_llm()
        analyst_instances = [
            TechnicalAnalyst(llm), ETFAnalyst(llm), DerivativesAnalyst(llm),
            OnChainAnalyst(llm), LiquidityAnalyst(llm), DefiAnalyst(llm),
            MacroAnalyst(llm), RegulationAnalyst(llm), NewsAnalyst(llm),
            WhaleAnalyst(llm), HistoricalAnalyst(llm),
        ]
        analyst_results: dict[str, AnalystResult] = {}
        outputs = await asyncio.gather(
            *(a.analyze(asset, context) for a in analyst_instances), return_exceptions=True
        )
        for inst, res in zip(analyst_instances, outputs, strict=True):
            if isinstance(res, BaseException):
                log.warning("analyst_failed", analyst=inst.name, error=str(res))
                analyst_results[inst.domain] = AnalystResult(
                    analyst=inst.name, domain=inst.domain, asset=asset, available=False,
                    unavailable_reason=f"analyst error: {res}",
                )
            else:
                analyst_results[inst.domain] = res

        chief = ChiefMarketAnalyst(llm)
        synthesis: ChiefSynthesis = await chief.synthesize(
            asset, analyst_results, conviction, contradiction_report, context
        )

        # State-change alerts need to know what the previous state was.
        previous_state = self._previous_state(asset)
        probability = assess_probability(conviction, empirical_result) if empirical_result else None
        confrontations = self.confrontation.build_all(asset, context)

        alerts = self.alerts.evaluate(asset, context, previous=previous_state)
        if alerts:
            try:
                repo.save_alerts(self.alerts.to_rows(alerts))
            except Exception as exc:
                log.warning("alert_persist_failed", error=str(exc))

        regime = self._market_regime(daily, mtf)
        llm_used = synthesis.llm_used or any(a.llm_used for a in analyst_results.values())

        # Immutable record of what was predicted, for honest live evaluation.
        try:
            from ..history.immutable import record_prediction

            record_prediction(
                asset=asset, price=price,
                regime=regime_assessment.model_dump(mode="json"),
                entry_timing=timing_assessment.model_dump(mode="json"),
                conviction=conviction.model_dump(mode="json"),
                scores={k: v.model_dump(mode="json") for k, v in cards.items()},
                scenarios=[s.model_dump(mode="json") for s in synthesis.scenarios],
                data_quality={
                    "sources_ok": sum(1 for s in sources if s.ok),
                    "sources_total": len(sources),
                    "domains_available": conviction.domains_available,
                    "domains_missing": conviction.domains_missing,
                },
            )
        except Exception as exc:
            log.warning("prediction_snapshot_failed", asset=asset.value, error=str(exc))

        # Shadow model: log what the system would call, without acting on it,
        # so live performance can later be set against backtest expectation.
        try:
            from ..research.drift import ShadowModel

            direction_map = {
                "STRONGLY_BULLISH": "UP", "BULLISH": "UP",
                "BEARISH": "DOWN", "STRONGLY_BEARISH": "DOWN",
            }
            if price:
                ShadowModel().record(
                    asset=asset,
                    direction=direction_map.get(regime_assessment.regime.value, "NEUTRAL"),
                    price=float(price),
                    regime=regime_assessment.regime.value,
                    edge_state=edge_assessment.state.value,
                )
        except Exception as exc:
            log.warning("shadow_record_failed", asset=asset.value, error=str(exc))

        report_id = "rpt_" + hashlib.sha1(
            f"{asset.value}|{now.isoformat()}".encode()
        ).hexdigest()[:16]

        return AssetAnalysis(
            asset=asset, generated_at=now, price=price,
            change_24h_pct=change_24h, change_7d_pct=change_7d,
            market_cap=market_cap, volume_24h=volume_24h, market_regime=regime,
            regime=regime_assessment.model_dump(mode="json"),
            entry_timing=timing_assessment.model_dump(mode="json"),
            edge=edge_assessment.model_dump(mode="json"),
            uncertainty=uncertainty_assessment.model_dump(mode="json"),
            decision_summary=decision_summary.model_dump(mode="json"),
            crowding=crowding_assessment.model_dump(mode="json"),
            leverage_state=leverage_state.model_dump(mode="json"),
            funding_context=funding_context.model_dump(mode="json"),
            volatility_regime=volatility_assessment.model_dump(mode="json"),
            etf_split=etf_split_result.model_dump(mode="json"),
            rsi_context=rsi_reading.to_dict() if rsi_reading else {},
            empirical=empirical_result.to_dict() if empirical_result else {},
            probability=probability.to_dict() if probability else {},
            confrontations=confrontations,
            scores={k: v.model_dump(mode="json") for k, v in cards.items()},
            conviction=conviction.model_dump(mode="json"),
            analysts={k: v.model_dump(mode="json") for k, v in analyst_results.items()},
            contradictions=contradiction_report.model_dump(mode="json"),
            scenarios=[s.model_dump(mode="json") for s in synthesis.scenarios],
            synthesis={
                "text": synthesis.synthesis,
                "positives": synthesis.positives,
                "negatives": synthesis.negatives,
                "contradictions": synthesis.contradictions,
                "key_catalysts": synthesis.key_catalysts,
                "key_risks": synthesis.key_risks,
                "what_would_change_my_mind": synthesis.what_would_change_my_mind,
                "recent_decisions": synthesis.recent_decisions,
                "missing_data": synthesis.missing_data,
                "data_quality_note": synthesis.data_quality_note,
                "llm_used": synthesis.llm_used,
            },
            technical={
                tf.value: snap.model_dump(mode="json")
                for tf, snap in snapshots.items() if snap
            },
            domains={
                "mtf": mtf.model_dump(mode="json"),
                "etf": etf_analysis.model_dump(mode="json"),
                "derivatives": deriv_analysis.model_dump(mode="json"),
                "onchain": onchain_analysis.model_dump(mode="json"),
                "liquidity": liquidity_analysis.model_dump(mode="json"),
                "defi": defi_analysis.model_dump(mode="json"),
                "macro": macro_analysis.model_dump(mode="json"),
                "regulation": regulation_analysis.model_dump(mode="json"),
                "news": news_analysis.model_dump(mode="json"),
                "whale": whale_analysis.model_dump(mode="json"),
                "geopolitics": geo_analysis.model_dump(mode="json"),
                "historical": historical_analysis.model_dump(mode="json") if historical_analysis else None,
            },
            sources=sources,
            alerts=[a.model_dump(mode="json") for a in alerts],
            llm_used=llm_used,
            report_id=report_id,
        )

    def _previous_state(self, asset: Asset) -> dict[str, Any]:
        """Last recorded regime and entry timing, for change detection.

        Read from the snapshot store rather than kept in memory, so a restarted
        process still detects transitions instead of re-announcing the current
        state as if it were new.
        """
        try:
            from ..history import snapshots

            rows = snapshots.load_snapshots("analysis", asset, limit=2)
        except Exception:
            return {}
        for row in rows:
            payload = row.get("payload") or {}
            regime = (payload.get("regime") or {}).get("regime")
            timing = (payload.get("entry_timing") or {}).get("timing")
            if regime or timing:
                return {
                    "regime": regime,
                    "entry_timing": timing,
                    # LOT 4 states, so their transitions can be alerted on too.
                    "edge_state": (payload.get("edge") or {}).get("state"),
                    "crowding": (payload.get("crowding") or {}).get("level"),
                    "volatility_regime": (
                        payload.get("volatility_regime") or {}
                    ).get("regime"),
                    "leverage_state": (payload.get("leverage_state") or {}).get("state"),
                }
        return {}

    def _market_regime(self, daily, mtf) -> str:
        if not daily or not daily.has_data:
            return "UNDETERMINED"
        trend = daily.trend.direction.value
        vol = daily.volatility_state
        if trend == "RANGE":
            return f"RANGE / {vol} VOLATILITY"
        coherent = "COHERENT" if mtf.coherence >= 60 else "MIXED TIMEFRAMES"
        return f"{trend} / {vol} VOLATILITY / {coherent}"


_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline
