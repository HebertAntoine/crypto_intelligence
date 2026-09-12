"""One analysis, one identity.

Every endpoint used to recompute what it needed. Two calls a second apart could
therefore describe two different moments, and the screen had no way to tell:
the regime came from one run, the funding from the next, the structure from a
third. Nothing was wrong in any single number, and the combination was still
false.

So an analysis is now a value with a name. `AnalysisContextSnapshot` holds
every reading that belongs to one decision, and `analysis_id` names it. Any
endpoint describing that decision returns the same id, and an endpoint that
read fresher inputs necessarily returns a different one — which is the signal
the UI needs in order to refuse to combine them.

The id is content-addressed, not allocated. It is the hash of a fingerprint of
the inputs: how many rows each stored series holds and when each one last
advanced, plus the scheduled macro calendar and a five-minute clock bucket.
Two processes reading the same database therefore agree on the id without
sharing any state, and the id changes exactly when the inputs do.

The live price is deliberately outside all of this. It moves every second; the
analysis does not. `price_at_analysis` is the last closed 4H bar, the price the
reading was actually computed on, and the drift between the two is reported
rather than hidden.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from ..core import labels_fr
from ..core.enums import Asset, Timeframe
from ..core.usability import (
    DataCoverage,
    FamilyState,
    Freshness,
    assess_coverage,
    freshness_for,
)
from ..logging_setup import get_logger

log = get_logger("engines.analysis_context")

# Bumped whenever the meaning of a snapshot field changes, so a deployed
# version never serves an id that names a differently-computed analysis.
ANALYSIS_SCHEMA_VERSION = "2026-09-07.1"

# The clock granularity of an analysis. Long enough that the id is stable
# across the several requests one screen makes; short enough that a macro
# countdown expressed in hours, and every family freshness, stay honest.
ANALYSIS_BUCKET_SECONDS = 300


def _bucket(now: datetime) -> str:
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(
        epoch - epoch % ANALYSIS_BUCKET_SECONDS, tz=UTC
    ).isoformat()


def data_fingerprint(asset: Asset) -> dict[str, Any]:
    """The inputs alone, with no clock in them.

    Separate from `input_fingerprint` because the two answer different
    questions. This one asks "has anything we read changed?", which is what
    decides whether a cached analysis is still about the present. The full
    fingerprint adds the clock bucket, and is what the id is computed from.
    """
    from ..db import repo
    from ..engines.macro import MacroAnalyzer
    from ..history import store

    try:
        calendar = [
            [event.kind, str(event.scheduled_at), event.importance]
            for event in MacroAnalyzer().load_calendar()
            if not event.is_past
        ]
    except (OSError, ValueError) as exc:  # a malformed calendar must not 500
        log.warning("calendar_fingerprint_failed", error=str(exc))
        calendar = []
    return {
        "schema": ANALYSIS_SCHEMA_VERSION,
        "asset": asset.value,
        "series": store.series_fingerprint(asset),
        "observations": repo.observation_fingerprint(asset),
        "calendar": sorted(calendar, key=lambda row: (row[1], row[0])),
    }


def input_fingerprint(asset: Asset, now: datetime | None = None) -> dict[str, Any]:
    """Name the inputs an analysis is built from, cheaply enough to check often."""
    return {**data_fingerprint(asset), "bucket": _bucket(now or datetime.now(UTC))}


def analysis_id_for(fingerprint: dict[str, Any]) -> str:
    payload = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"), default=str)
    return "an_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --- input families -------------------------------------------------------

def family_states(
    asset: Asset, now: datetime | None = None
) -> dict[str, FamilyState]:
    """Every stored input family, answered four ways from its real observation.

    The timestamps come from the store rather than from the engines, because an
    engine will happily compute on whatever it was given: the question here is
    not what came out but how old what went in actually is.

    The live price is not here. It is not stored, it is fetched per request,
    and folding it in would make an analysis look older or newer than it is.
    """
    from ..db import repo
    from ..history import store

    reference = now or datetime.now(UTC)
    states: dict[str, FamilyState] = {}

    def candles(family: str, timeframe: Timeframe, minimum: int) -> FamilyState:
        coverage = store.candle_coverage(asset, timeframe)
        rows = coverage.get("rows", 0)
        return FamilyState(
            family=family, available=rows > 0, valid=rows >= minimum,
            freshness=freshness_for(family, coverage.get("end"), reference),
            observed_at=coverage.get("end"), source="candle store", points=rows,
            reason=(
                "" if rows >= minimum
                else f"{rows} bougies, moins que les {minimum} nécessaires"
            ),
        )

    states["ohlcv_daily"] = candles("ohlcv_daily", Timeframe.D1, 200)
    states["ohlcv_4h"] = candles("ohlcv_4h", Timeframe.H4, 60)

    # Structure and realised volatility are computations, not sources: they are
    # exactly as fresh as the bars they read and no fresher.
    states["structure"] = FamilyState(
        family="structure",
        available=states["ohlcv_4h"].available,
        valid=states["ohlcv_4h"].valid,
        freshness=states["ohlcv_4h"].freshness,
        observed_at=states["ohlcv_4h"].observed_at,
        source="MarketStructureEngine sur bougies 4H",
        points=states["ohlcv_4h"].points,
        reason=states["ohlcv_4h"].reason,
    )
    states["volatility"] = FamilyState(
        family="volatility",
        available=states["ohlcv_daily"].available,
        valid=states["ohlcv_daily"].valid,
        freshness=freshness_for("volatility", states["ohlcv_daily"].observed_at, reference),
        observed_at=states["ohlcv_daily"].observed_at,
        source="VolatilityRegimeEngine sur bougies journalières",
        points=states["ohlcv_daily"].points,
    )

    derivatives = store.derivatives_coverage(asset)
    for metric, family in (
        ("funding.rate", "funding"),
        ("oi.contracts_bybit", "open_interest"),
        ("dvol.index", "dvol"),
    ):
        entry = derivatives.get(metric)
        if entry is None and family == "open_interest":
            entry = derivatives.get("oi.value")
        if entry is None:
            states[family] = FamilyState(
                family=family, available=False, valid=False,
                freshness=Freshness.UNAVAILABLE, source=metric,
                reason=(
                    "aucune série DVOL n'existe pour cet actif; la volatilité "
                    "repose sur l'ATR réalisé"
                    if family == "dvol" else "aucune observation stockée"
                ),
            )
            continue
        states[family] = FamilyState(
            family=family, available=entry["rows"] > 0, valid=entry["rows"] >= 30,
            freshness=freshness_for(family, entry["end"], reference),
            observed_at=entry["end"], source=metric, points=entry["rows"],
        )

    observations = repo.observation_fingerprint(asset)

    def from_observations(family: str, key: str, source: str, minimum: int = 1) -> FamilyState:
        rows, last = observations.get(key, [0, None])
        observed = datetime.fromisoformat(last) if last else None
        return FamilyState(
            family=family, available=rows > 0, valid=rows >= minimum,
            freshness=freshness_for(family, observed, reference),
            observed_at=observed, source=source, points=rows,
        )

    states["etf"] = from_observations("etf", "etf_flows", "Farside Investors, flux par émetteur")
    states["macro"] = from_observations("macro", "observations:macro.", "séries macro FRED/Stooq")
    states["onchain"] = from_observations("onchain", "observations:onchain.", "fournisseurs on-chain")
    states["whales"] = FamilyState(
        family="whales", source="fournisseur on-chain vérifié",
        reason=(
            "aucun fournisseur baleines fiable n'est configuré; suivre les gros "
            "portefeuilles demande un service payant, et rien n'est estimé à la place"
        ),
    )
    states["exchange_flows"] = FamilyState(
        family="exchange_flows", source="connecteur de flux spot/exchange",
        reason="aucune série fiable de flux net spot/exchange n'est configurée",
    )

    # Cross-asset correlation reads index candles from the macro store; without
    # them the correlation is not stale, it does not exist.
    macro_series = store.macro_coverage()
    proxies = [entry for name, entry in macro_series.items()
               if any(token in name.lower() for token in ("nasdaq", "spx", "dxy", "ndx"))]
    latest = max((entry.get("end") for entry in proxies if entry.get("end")), default=None)
    states["cross_asset"] = FamilyState(
        family="cross_asset", available=bool(proxies), valid=bool(latest),
        freshness=freshness_for("cross_asset", latest, reference),
        observed_at=latest, source="indices actions et dollar (séries macro)",
        points=len(proxies),
    )
    return states


def price_family(market: dict[str, Any] | None, now: datetime | None = None) -> FamilyState:
    """The live price, judged on its own cadence and never on the analysis clock."""
    observed = None
    if market:
        raw = market.get("as_of") or market.get("timestamp")
        if isinstance(raw, str):
            try:
                observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                observed = None
    value = (market or {}).get("price_usd")
    return FamilyState(
        family="price",
        available=value is not None,
        valid=isinstance(value, int | float) and value > 0,
        freshness=freshness_for("price", observed, now),
        observed_at=observed,
        source=(market or {}).get("method", "") or "market price engine",
        points=(market or {}).get("provider_count"),
    )


# --- inputs the engines need ----------------------------------------------

class _ReconstructedRegime:
    """Minimal stand-in carrying the same attributes the summary reads."""

    def __init__(self, label: str, confidence: float) -> None:
        self.regime = type("R", (), {"value": label})()
        self.confidence = confidence


def reconstructed_regime(asset: Asset) -> _ReconstructedRegime:
    from ..history import store
    from ..research.regime_conditioned import reconstruct_regime

    df = store.load_candles(asset, Timeframe.D1)
    if df.empty or len(df) < 200:
        return _ReconstructedRegime("UNDETERMINED", 0.0)
    labels = reconstruct_regime(df).dropna()
    if labels.empty:
        return _ReconstructedRegime("UNDETERMINED", 0.0)

    label = str(labels.iloc[-1])
    # Confidence from persistence: a label that just flipped is less settled
    # than one that has held for weeks.
    recent = labels.iloc[-20:]
    return _ReconstructedRegime(label, round(float((recent == label).mean() * 100), 1))


def technical_snapshots(asset: Asset) -> dict[Timeframe, Any]:
    """Indicator snapshots for the timeframes the timing engine reads.

    The engine existed and computed a -100..+100 score with named factors;
    `/today` simply never handed it its inputs, so entry timing stayed
    UNDETERMINED while the calculation was available. Support and resistance
    levels come out of the same snapshots, so they are computed once here.
    """
    from ..core.models import Candle, OHLCVSeries, Provenance
    from ..engines.technical.engine import TechnicalAnalysisEngine
    from ..history import store

    engine = TechnicalAnalysisEngine()
    snapshots: dict[Timeframe, Any] = {}
    for timeframe in (Timeframe.D1, Timeframe.H4, Timeframe.H1):
        df = store.load_candles(asset, timeframe)
        if df.empty or len(df) < 60:
            continue
        candles = [
            Candle(
                timestamp=ts, open=row.open, high=row.high, low=row.low,
                close=row.close, volume=row.volume,
            )
            for ts, row in df.tail(400).iterrows()
        ]
        try:
            snapshots[timeframe] = engine.analyze(
                OHLCVSeries(
                    asset=asset, timeframe=timeframe, candles=candles,
                    provenance=Provenance(source="local history", provider="ohlcv_store"),
                )
            )
        except (ValueError, KeyError) as exc:
            log.warning("timing_snapshot_failed", timeframe=timeframe.value, error=str(exc))
    return snapshots


def upcoming_macro(asset: Asset, days: int = 14, now: datetime | None = None) -> list[dict[str, Any]]:
    """Scheduled macro events that touch this asset.

    Events come from the rich store populated by primary-source collectors. A
    near deadline predicts nothing, but it explains why waiting can be
    reasonable.
    """
    from ..db import repo
    from ..future_events.models import FutureEventCategory

    reference = now or datetime.now(UTC)
    out: list[dict[str, Any]] = []
    events = repo.list_future_events(
        asset=asset,
        start=reference,
        end=reference + timedelta(days=days),
        limit=100,
    )
    for event in events:
        if event.category not in {
            FutureEventCategory.MACRO,
            FutureEventCategory.MONETARY_POLICY,
        } or event.scheduled_at is None:
            continue
        assets = [item.value for item in event.affected_assets]
        scheduled = event.scheduled_at
        hours = (scheduled - reference).total_seconds() / 3600.0
        out.append({
            "id": event.id,
            "kind": event.event_type,
            "name": event.title,
            "scheduled_at": scheduled.isoformat(),
            "importance": event.importance.value,
            "hours_until": round(hours, 1),
            "days_until": round(hours / 24.0, 1),
            "assets": assets,
            "source": event.source,
            "source_tier": event.source_tier.value,
            "source_url": event.source_url,
            "directional_effect": event.directional_effect.value,
            "magnitude_effect": event.magnitude_effect.value,
        })
    out.sort(key=lambda event: event["hours_until"])
    return out[:5]


def breakout_title(state: str, direction: str | None) -> str:
    """The French name of a break or a reintegration."""
    sens = {"up": "par le haut", "down": "par le bas"}.get((direction or "").lower(), "")
    base = labels_fr.BREAKOUT_FR.get(state, state.replace("_", " ").capitalize())
    return f"{base} {sens}".strip()


def breakout_sentence(breakout: Any) -> str:
    """A readable sentence built from the measurements, not translated.

    Quality is said to be what it is: a description of the move, not a
    prediction of what follows it.
    """
    quality = getattr(breakout, "quality_score", None)
    bars = getattr(breakout, "bars_since_break", None)
    quand = (
        f"il y a {bars} bougie{'s' if bars and bars > 1 else ''} en 4H"
        if bars is not None else "récemment"
    )
    if quality is None:
        return f"Mouvement détecté {quand}. Sa qualité ne prédit pas sa suite."
    jugement = (
        "de bonne facture" if quality >= 60
        else "de qualité moyenne" if quality >= 40
        else "de qualité limitée"
    )
    return (
        f"Mouvement {jugement} ({quality:.0f}/100), {quand}. La qualité décrit "
        "le mouvement passé; elle ne prédit pas sa suite."
    )


def _is_synthetic(observations: list[Any]) -> bool:
    """An observation from the fixtures must never carry weight.

    The database holds observations recorded with the fixtures' source,
    ingested while MOCK_MODE was on. They then present themselves like any
    other measurement: without this filter, "Liquidité stablecoin: expansion"
    appeared among the positive factors of a production decision, sourced
    "MOCK FIXTURES (synthetic)".
    """
    for observation in observations:
        source = (getattr(observation.provenance, "source", "") or "").upper()
        if "MOCK" in source or "SYNTHETIC" in source or "FIXTURE" in source:
            return True
    return False


def evidence_context(asset: Asset, now: datetime) -> dict[str, Any]:
    """Run the deterministic engines the decision reads, once.

    The page does not need every available metric. This collector keeps the
    full outputs for audit and promotes only material readings to ranked
    ``DecisionFactor`` objects. An unavailable family stays unavailable.
    """
    from ..db import repo
    from ..engines.breakout import BreakoutQualityEngine
    from ..engines.buy_opportunity import Category, DecisionFactor, Polarity
    from ..engines.cross_asset import CrossAssetAnalyzer
    from ..engines.historical import HistoricalSimilarityEngine
    from ..engines.implied_volatility import ImpliedVolatilityEngine
    from ..engines.liquidity import StablecoinLiquidityAnalyzer
    from ..engines.macro import MacroAnalyzer
    from ..engines.onchain import OnChainAnalyzer
    from ..engines.whales import WhaleAnalyzer
    from ..history import store
    from ..pattern_learning.quality_gate import apply_independent_live_gate
    from ..research.structural_shadow import live_track_record
    from ..structure.market_structure import MarketStructureEngine
    from ..structure.patterns import build_context, detect_all

    since = now - timedelta(days=45)
    factors: list[DecisionFactor] = []

    def latest_meta(observations: list[Any], fallback: str) -> tuple[str, str, str]:
        if not observations:
            return fallback, now.isoformat(), "UNAVAILABLE"
        last = max(observations, key=lambda item: item.timestamp)
        return (
            last.provenance.source or fallback,
            last.timestamp.isoformat(),
            last.freshness.value,
        )

    mtf = MarketStructureEngine().multi_timeframe(
        asset, [Timeframe.W1, Timeframe.D1, Timeframe.H4, Timeframe.H1]
    )
    bullish = mtf["bullish_timeframes"]
    bearish = mtf["bearish_timeframes"]
    conflict = mtf["conflict"]
    measured = len(bullish) + len(bearish)
    if measured:
        structural_score = (len(bullish) - len(bearish)) / measured * 100
        factors.append(DecisionFactor(
            id="structure.multi_timeframe", category=Category.STRUCTURE,
            title="Structures multi-unités contradictoires" if conflict else
                  f"Structure dominante sur {measured} unité(s)",
            short_text=conflict or (
                f"Haussière: {', '.join(bullish) or 'aucune'}; "
                f"baissière: {', '.join(bearish) or 'aucune'}."
            ),
            raw_value={"bullish": bullish, "bearish": bearish,
                       "contradiction": 1.0 if conflict else 0.0},
            normalized_value=round(structural_score, 1),
            polarity=(Polarity.WAIT if conflict else
                      Polarity.POSITIVE if structural_score > 0 else
                      Polarity.NEGATIVE if structural_score < 0 else Polarity.NEUTRAL),
            importance=84, confidence=min(.9, measured / 4),
            timeframe="1W/1D/4H/1H", source="MarketStructureEngine",
            as_of=now.isoformat(), freshness="RECENT",
        ))

    breakout = BreakoutQualityEngine().assess(asset, Timeframe.H4)
    breakout_state = breakout.state.value
    if breakout_state != "NONE":
        failed = breakout_state in ("FAILED_BREAKOUT", "FAKEOUT", "REINTEGRATION")
        factors.append(DecisionFactor(
            id="structure.breakout", category=Category.STRUCTURE,
            # `interpretation` is the engine's English sentence. It stays in
            # raw_value for the evidence screen; the page receives French.
            title=breakout_title(breakout_state, breakout.direction),
            short_text=breakout_sentence(breakout),
            raw_value={"state": breakout_state, "direction": breakout.direction,
                       "quality": breakout.quality_score,
                       "recent_change": 1.0 if breakout.bars_since_break is not None
                       and breakout.bars_since_break <= 3 else 0.3},
            normalized_value=(
                -(breakout.quality_score or 50) if failed
                else (breakout.quality_score or 50)
            ),
            polarity=Polarity.NEGATIVE if failed else Polarity.WAIT,
            importance=76, confidence=.72, timeframe="4H",
            source="BreakoutQualityEngine", as_of=now.isoformat(), freshness="RECENT",
        ))

    # The pattern engine names its states in English enums. They belong in
    # raw_value for the evidence screen; the sentence the page reads gets
    # French, like every other engine output that reaches a person.
    pattern_state_fr = labels_fr.PATTERN_STATE_FR
    pattern_edge_fr = labels_fr.PATTERN_EDGE_FR

    h4_candles = store.load_candles(asset, Timeframe.H4)
    pattern_context = build_context(h4_candles, Timeframe.H4)
    patterns = detect_all(pattern_context) if pattern_context is not None else []
    pattern_gate = apply_independent_live_gate(patterns, h4_candles["close"])
    promoted_patterns = pattern_gate["accepted"]
    if promoted_patterns:
        pattern = promoted_patterns[0]
        gate_decision = next(
            decision for decision in pattern_gate["decisions"]
            if decision["pattern"] == pattern.name and decision["promoted"]
        )
        factors.append(DecisionFactor(
            id="structure.pattern", category=Category.STRUCTURE,
            title=f"Figure reconnue: {pattern.name}",
            short_text=(
                f"Reconnaissance {pattern.recognition_confidence:.0f}/100, "
                f"{pattern_state_fr.get(pattern.state.value, 'état indéterminé')}; "
                f"avantage mesuré séparément : "
                f"{pattern_edge_fr.get(pattern.edge_state.value, 'non évalué')}. "
                "La reconnaissance n’est pas une probabilité."
            ),
            raw_value={"recognition_confidence": pattern.recognition_confidence,
                       "state": pattern.state.value,
                       "edge_state": pattern.edge_state.value,
                       "independent_agreement": 1.0,
                       "temporal_iou": gate_decision["temporal_iou"],
                       "lmw_score": gate_decision["lmw_score"]},
            normalized_value=pattern.recognition_confidence,
            polarity=Polarity.WAIT, importance=48, confidence=.7,
            evidence_level="COMPUTATION", timeframe="4H",
            source="StructuralPatternConsensus", as_of=pattern.detected_at.isoformat(),
            freshness="RECENT",
        ))

    onchain_observations = repo.observations_since(asset, "onchain.", since)
    if _is_synthetic(onchain_observations):
        onchain_observations = []
    onchain = OnChainAnalyzer().analyze(asset, onchain_observations)
    if onchain.available and abs(onchain.strength) > 12:
        source, observed_at, freshness = latest_meta(onchain_observations, "on-chain provider")
        factors.append(DecisionFactor(
            id="onchain.activity", category=Category.ONCHAIN,
            title="Activité on-chain en amélioration" if onchain.strength > 0
                  else "Activité on-chain en retrait",
            short_text="; ".join(onchain.findings[:2]), raw_value=onchain.metrics,
            normalized_value=onchain.strength,
            polarity=Polarity.POSITIVE if onchain.strength > 0 else Polarity.NEGATIVE,
            importance=54, confidence=.65, evidence_level="COMPUTATION",
            timeframe="7D", source=source, as_of=observed_at, freshness=freshness,
        ))

    liquidity_observations = repo.observations_since(None, "stablecoin.", since)
    if _is_synthetic(liquidity_observations):
        liquidity_observations = []
    liquidity = StablecoinLiquidityAnalyzer().analyze(liquidity_observations)
    if liquidity.available and abs(liquidity.strength) > 12:
        source, observed_at, freshness = latest_meta(
            liquidity_observations, "stablecoin supply providers"
        )
        factors.append(DecisionFactor(
            id="liquidity.stablecoins", category=Category.LIQUIDITY,
            title=f"Liquidité stablecoin: {liquidity.regime.lower()}",
            short_text="; ".join(liquidity.findings[:2]),
            raw_value={"change_1d_pct": liquidity.change_1d_pct,
                       "change_7d_pct": liquidity.change_7d_pct},
            normalized_value=liquidity.strength,
            polarity=Polarity.POSITIVE if liquidity.strength > 0 else Polarity.NEGATIVE,
            importance=62, confidence=.72, timeframe="7D",
            source=source, as_of=observed_at, freshness=freshness,
        ))

    macro_observations = repo.observations_since(None, "macro.", since)
    if _is_synthetic(macro_observations):
        macro_observations = []
    macro = MacroAnalyzer().analyze(macro_observations, now=now)
    if macro.available and abs(macro.strength) > 12:
        source, observed_at, freshness = latest_meta(macro_observations, "macro providers")
        factors.append(DecisionFactor(
            id="macro.context", category=Category.MACRO,
            title="Contexte macro porteur" if macro.strength > 0 else "Contexte macro contraignant",
            short_text="; ".join(macro.findings[:2]),
            raw_value={"risk_appetite": macro.risk_appetite,
                       "dollar_trend": macro.dollar_trend,
                       "rates_trend": macro.rates_trend},
            normalized_value=macro.strength,
            polarity=Polarity.POSITIVE if macro.strength > 0 else Polarity.NEGATIVE,
            importance=68, confidence=.68, timeframe="5D",
            source=source, as_of=observed_at, freshness=freshness,
        ))

    cross_asset = CrossAssetAnalyzer().assess(asset)
    if cross_asset.risk_proxy_correlation is not None and abs(
        cross_asset.risk_proxy_correlation
    ) >= .4:
        factors.append(DecisionFactor(
            id="cross_asset.nasdaq", category=Category.CROSS_ASSET,
            title="Dépendance élevée aux actifs risqués",
            short_text=cross_asset.interpretation,
            raw_value={"nasdaq_correlation": cross_asset.risk_proxy_correlation},
            normalized_value=abs(cross_asset.risk_proxy_correlation) * 100,
            polarity=Polarity.WAIT, importance=50, confidence=.65,
            timeframe="90D", source="CrossAssetAnalyzer (OHLCV + indices)",
            as_of=now.isoformat(), freshness="TODAY",
        ))

    daily = store.load_candles(asset, Timeframe.D1)
    historical = HistoricalSimilarityEngine().analyze(asset, daily, Timeframe.D1)
    historical_summary = None
    if historical.available:
        historical_summary = {
            "raw_n": historical.sample_size,
            "effective_n": historical.effective_sample_size,
            "median_return": historical.median_forward_returns.get("7d"),
            "mfe": historical.median_mfe_7d_pct,
            "mae": historical.median_mae_7d_pct,
            "hit_rate": historical.hit_rate.get("7d"),
        }

    live = live_track_record(asset)
    rows = live.get("rows") or []
    track_summary = {
        "status": "TOO_EARLY",
        "matured_predictions": sum(int(row.get("matured_predictions", 0)) for row in rows),
    }
    if rows and all(row.get("verdict") != "TOO_EARLY" for row in rows):
        track_summary["status"] = "MATURE"

    whale_observations = repo.observations_since(asset, "whale.", since)
    if _is_synthetic(whale_observations):
        whale_observations = []
    whales = WhaleAnalyzer().analyze(
        asset, whale_observations,
        unavailable_reason=None if whale_observations else
        "Aucun fournisseur baleines fiable n'est configuré : suivre les gros "
        "portefeuilles demande un service on-chain payant, et rien n'est estimé "
        "à la place.",
    )
    implied = ImpliedVolatilityEngine().assess(asset)
    return {
        "factors": factors, "multi_timeframe": mtf,
        "breakout": breakout.model_dump(mode="json"),
        "patterns": [
            {
                **pattern.to_dict(),
                "independent_quality_gate": pattern_gate["decisions"][index],
            }
            for index, pattern in enumerate(patterns[:3])
        ],
        "pattern_quality_gate": {
            **pattern_gate["summary"],
            "edge_claim": pattern_gate["edge_claim"],
        },
        "onchain": onchain.model_dump(mode="json"),
        "liquidity": liquidity.model_dump(mode="json"),
        "macro": macro.model_dump(mode="json"),
        "cross_asset": cross_asset.model_dump(mode="json"),
        "historical": historical_summary,
        "live_track_record": track_summary,
        "whales": whales,
        "implied_volatility": implied,
    }


# --- the snapshot ---------------------------------------------------------

@dataclass(slots=True)
class AnalysisContextSnapshot:
    """Every reading that belongs to one decision, under one identity.

    Built from stored data only. Nothing here depends on the live price, so a
    tick does not silently produce a new analysis, and two endpoints reading
    the same store agree by construction rather than by luck.
    """

    analysis_id: str
    asset: str
    analysis_time: datetime
    price_at_analysis: float | None
    fingerprint: dict[str, Any]

    families: dict[str, FamilyState] = field(default_factory=dict)
    coverage: DataCoverage | None = None

    regime: Any = None
    structure: dict[str, Any] = field(default_factory=dict)
    location: Any = None
    location_by_timeframe: dict[str, Any] = field(default_factory=dict)
    supports: list[Any] = field(default_factory=list)
    resistances: list[Any] = field(default_factory=list)

    funding: Any = None
    leverage_state: Any = None
    crowding: Any = None
    volatility: Any = None
    implied_volatility: Any = None
    etf: dict[str, Any] = field(default_factory=dict)

    macro_events: list[dict[str, Any]] = field(default_factory=list)
    macro_context: dict[str, Any] = field(default_factory=dict)
    edge: Any = None
    analogs: dict[str, Any] | None = None
    uncertainty: Any = None
    decision_summary: Any = None

    timing: Any = None
    entry: Any = None
    pressure: Any = None
    opportunity: Any = None

    breakout: dict[str, Any] = field(default_factory=dict)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    onchain: dict[str, Any] = field(default_factory=dict)
    liquidity: dict[str, Any] = field(default_factory=dict)
    cross_asset: dict[str, Any] = field(default_factory=dict)
    live_track_record: dict[str, Any] = field(default_factory=dict)
    whales: Any = None
    factors: list[Any] = field(default_factory=list)
    technical: dict[str, Any] = field(default_factory=dict)
    future_events: list[Any] = field(default_factory=list)
    future_families: Any = None
    future_decision: Any = None
    future_horizons: dict[str, Any] = field(default_factory=dict)

    @property
    def provenance(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "analysis_time": self.analysis_time.isoformat(),
            "bucket_seconds": ANALYSIS_BUCKET_SECONDS,
            "price_at_analysis": self.price_at_analysis,
            "price_source": "dernière clôture 4H du magasin de bougies",
            "llm_used": False,
            "inputs": self.fingerprint,
        }

    def identity(self) -> dict[str, Any]:
        """The three fields every endpoint of this analysis repeats verbatim."""
        return {
            "analysis_id": self.analysis_id,
            "analysis_time": self.analysis_time.isoformat(),
            "price_at_analysis": self.price_at_analysis,
        }


_CACHE: dict[str, AnalysisContextSnapshot] = {}


def context_for(
    asset: Asset, now: datetime | None = None, *, refresh: bool = False
) -> AnalysisContextSnapshot:
    """The current analysis for this asset, computed once per input change.

    A cached snapshot is reused while its inputs are unchanged and it is
    younger than one bucket. Holding it for the whole bucket, rather than
    recomputing whenever the wall clock crosses a boundary, is what keeps a
    burst of calls from one screen inside one analysis: without it, two
    endpoints called a second apart either side of :05 returned two ids and
    the client had to treat a perfectly consistent pair as a mismatch.

    The identity itself is still content-addressed. The cache decides when a
    new analysis is built, never what it is called.
    """
    reference = now or datetime.now(UTC)
    inputs = data_fingerprint(asset)
    cached = _CACHE.get(asset.value)
    if (
        cached is not None
        and not refresh
        and {k: v for k, v in cached.fingerprint.items() if k != "bucket"} == inputs
        and (reference - cached.analysis_time).total_seconds() < ANALYSIS_BUCKET_SECONDS
    ):
        return cached
    fingerprint = {**inputs, "bucket": _bucket(reference)}
    snapshot = build_context(asset, fingerprint, analysis_id_for(fingerprint), reference)
    _CACHE[asset.value] = snapshot
    return snapshot


def reset_cache() -> None:
    _CACHE.clear()


def build_context(
    asset: Asset,
    fingerprint: dict[str, Any] | None = None,
    analysis_id: str | None = None,
    now: datetime | None = None,
) -> AnalysisContextSnapshot:
    """Run every engine one decision needs, once, in one consistent moment."""
    from ..engines.edge import EdgeEngine, UncertaintyEngine, build_decision_summary
    from ..engines.entry_opportunity import EntryOpportunityEngine
    from ..engines.entry_timing import EntryTimingEngine
    from ..engines.future_context import build_five_family_snapshot
    from ..engines.future_decision import FutureDecisionEngine, horizon_decisions
    from ..engines.leverage import LeverageCrowdingEngine
    from ..engines.market_pressure import assess_pressure
    from ..engines.volatility import VolatilityRegimeEngine
    from ..history import store
    from ..structure.location import StructuralLocationEngine

    reference = now or datetime.now(UTC)
    fingerprint = fingerprint if fingerprint is not None else input_fingerprint(asset, reference)
    analysis_id = analysis_id or analysis_id_for(fingerprint)

    families = family_states(asset, reference)

    candles = store.load_candles(asset, Timeframe.H4)
    price_at_analysis = float(candles["close"].iloc[-1]) if not candles.empty else None

    leverage_engine = LeverageCrowdingEngine()
    crowding = leverage_engine.crowding(asset)
    funding = leverage_engine.funding_context(asset)
    leverage_state = leverage_engine.leverage_state(asset)
    edge = EdgeEngine().assess(asset)
    volatility = VolatilityRegimeEngine().assess(asset)
    regime = reconstructed_regime(asset)

    snapshots = technical_snapshots(asset)
    timing = EntryTimingEngine().assess(asset, {"snapshots": snapshots})

    freshness_map = {
        name: ("OK" if state.usable else state.freshness.value)
        for name, state in families.items()
    }
    uncertainty = UncertaintyEngine().assess(
        asset, edge, regime=regime, crowding=crowding, freshness=freshness_map,
    )
    decision_summary = build_decision_summary(
        asset, edge, uncertainty, regime=regime, timing=timing,
        crowding=crowding, volatility=volatility,
    )

    evidence = evidence_context(asset, reference)
    location_engine = StructuralLocationEngine()
    location = location_engine.assess(asset, Timeframe.H4)
    location_by_timeframe = location_engine.multi_timeframe(
        asset, [Timeframe.W1, Timeframe.D1, Timeframe.H4, Timeframe.H1]
    )

    pressure = assess_pressure(
        asset,
        funding_percentile=funding.percentile,
        funding_usable=families["funding"].usable if "funding" in families else False,
        leverage_state=str(getattr(leverage_state, "state", "")),
        positioning_usable=(
            families["open_interest"].usable if "open_interest" in families else False
        ),
        whale_analysis=evidence["whales"],
        family_states=families,
    )

    entry = EntryOpportunityEngine().assess(asset, Timeframe.H4)
    macro_events = upcoming_macro(asset, now=reference)

    from ..db import repo
    from ..future_events.models import FutureEventStatus

    future_events = [
        event
        for event in repo.list_future_events(
            asset=asset,
            start=reference - timedelta(days=7),
            end=reference + timedelta(days=30),
            limit=250,
        )
        if (
            (event.scheduled_at is not None and event.scheduled_at >= reference)
            or event.runtime_status(reference)
            in {FutureEventStatus.ACTIVE, FutureEventStatus.SURPRISE, FutureEventStatus.DECAYING}
        )
    ]
    future_families = build_five_family_snapshot(
        analysis_id=analysis_id,
        as_of=reference,
        states=families,
        events=future_events,
        macro_context=evidence["macro"],
        liquidity=evidence["liquidity"],
        pressure=pressure,
        structure=evidence["multi_timeframe"],
        regime=regime,
        volatility=volatility,
        implied_volatility=evidence["implied_volatility"],
    )
    uncertainty_fraction = min(1.0, max(0.0, float(uncertainty.score or 0) / 100.0))
    future_engine = FutureDecisionEngine()
    future_decision = future_engine.decide(
        asset,
        future_events,
        future_families,
        as_of=reference,
        analysis_uncertainty=uncertainty_fraction,
    )
    future_horizon_views = horizon_decisions(
        future_engine,
        asset,
        future_events,
        future_families,
        as_of=reference,
        analysis_uncertainty=uncertainty_fraction,
    )

    from ..engines.buy_opportunity import decide

    opportunity = decide(
        asset,
        entry=entry, edge=edge, uncertainty=uncertainty,
        macro_events=macro_events, crowding=crowding, pressure=pressure,
        unusable_families=[name for name, state in families.items() if not state.usable],
        critical_missing_families=[
            name for name in ("ohlcv_daily",)
            if name not in families or not families[name].usable
        ],
        regime=regime, timing=timing, volatility=volatility,
        implied_volatility=evidence["implied_volatility"],
        historical_analogs=evidence["historical"],
        live_track_record=evidence["live_track_record"],
        extra_factors=evidence["factors"],
        location=location,
        future_decision=future_decision.to_dict(),
    )

    h4 = snapshots.get(Timeframe.H4)
    supports = list(getattr(h4, "levels_support", []) or [])
    resistances = list(getattr(h4, "levels_resistance", []) or [])

    snapshot = AnalysisContextSnapshot(
        analysis_id=analysis_id,
        asset=asset.value,
        analysis_time=reference,
        price_at_analysis=price_at_analysis,
        fingerprint=fingerprint,
        families=families,
        coverage=assess_coverage(asset.value, families),
        regime=regime,
        structure=evidence["multi_timeframe"],
        location=location,
        location_by_timeframe=location_by_timeframe,
        supports=supports,
        resistances=resistances,
        funding=funding,
        leverage_state=leverage_state,
        crowding=crowding,
        volatility=volatility,
        implied_volatility=evidence["implied_volatility"],
        etf=_etf_summary(pressure),
        macro_events=macro_events,
        macro_context=evidence["macro"],
        edge=edge,
        analogs=evidence["historical"],
        uncertainty=uncertainty,
        decision_summary=decision_summary,
        timing=timing,
        entry=entry,
        pressure=pressure,
        opportunity=opportunity,
        breakout=evidence["breakout"],
        patterns=evidence["patterns"],
        onchain=evidence["onchain"],
        liquidity=evidence["liquidity"],
        cross_asset=evidence["cross_asset"],
        live_track_record=evidence["live_track_record"],
        whales=evidence["whales"],
        factors=evidence["factors"],
        technical={
            timeframe.value: snapshot_value
            for timeframe, snapshot_value in snapshots.items()
        },
        future_events=future_events,
        future_families=future_families,
        future_decision=future_decision,
        future_horizons=future_horizon_views,
    )
    log.info(
        "analysis_built", asset=asset.value, analysis_id=analysis_id,
        state=opportunity.state.value,
        coverage=snapshot.coverage.summary_line if snapshot.coverage else "",
    )
    return snapshot


def _etf_summary(pressure: Any) -> dict[str, Any]:
    """The ETF reading as the page states it, without the raw table.

    Taken from the pressure component rather than recomputed, so the flows
    quoted here and the ETF contribution to buying pressure are the same
    numbers from the same fetch.
    """
    for component in getattr(pressure, "components", []) or []:
        if getattr(component, "name", "") != "institutions":
            continue
        raw = getattr(component, "raw_value", None) or {}
        available = bool(getattr(component, "available", False))
        net_5 = raw.get("net_5d_musd")
        return {
            "available": available,
            "headline": (
                "Flux récents positifs" if available and (net_5 or 0) > 0
                else "Flux récents négatifs" if available and (net_5 or 0) < 0
                else "Flux récents équilibrés" if available
                else "Indisponible"
            ),
            "latest_musd": raw.get("latest_musd"),
            "net_5d_musd": net_5,
            "net_20d_musd": raw.get("net_20d_musd"),
            "streak_sessions": raw.get("streak_sessions"),
            "source": getattr(component, "source", ""),
            "as_of": getattr(component, "as_of", None),
            "freshness": getattr(component, "freshness", "UNAVAILABLE"),
            "reason": getattr(component, "reason", ""),
            "caveat": "Flux observés ≠ avantage prédictif démontré.",
        }
    return {"available": False, "headline": "Indisponible",
            "caveat": "Flux observés ≠ avantage prédictif démontré."}


# --- the live layer -------------------------------------------------------
#
# Price moves by the second; the analysis is recomputed far less often.
# Presenting them under one timestamp let the screen show "analyse hors ligne"
# above a "LIVE" price, which is true on both sides and incomprehensible
# together. So they are two layers, joined only by an explicit drift figure.

DRIFT_THRESHOLD_PCT = 1.5
DRIFT_SEVERE_PCT = 3.0


class AnalysisFreshness(StrEnum):
    """L'âge d'une lecture, et ce qu'elle a encore le droit d'affirmer.

    Une analyse de quatre heures présentée comme « maintenant » est le défaut
    le plus coûteux de cette page: en crypto, le prix sur lequel elle a été
    calculée n'existe plus. Au-delà du dernier seuil le verdict n'est plus
    présenté comme une décision active — il reste lisible, daté, et annoncé
    comme non actualisé.
    """

    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"

    @property
    def is_actionable(self) -> bool:
        return self in (AnalysisFreshness.FRESH, AnalysisFreshness.AGING)


def _freshness_limits() -> dict[str, int]:
    from ..config_loader import threshold

    raw = threshold("analysis_freshness", default={}) or {}
    return {
        "fresh": int(raw.get("fresh_seconds", 900)),
        "aging": int(raw.get("aging_seconds", 3600)),
        "stale": int(raw.get("stale_seconds", 10800)),
    }


def analysis_freshness(age_seconds: float) -> AnalysisFreshness:
    limits = _freshness_limits()
    if age_seconds <= limits["fresh"]:
        return AnalysisFreshness.FRESH
    if age_seconds <= limits["aging"]:
        return AnalysisFreshness.AGING
    if age_seconds <= limits["stale"]:
        return AnalysisFreshness.STALE
    return AnalysisFreshness.EXPIRED


def _age_label(age_seconds: float) -> str:
    """« il y a 8 min », « 3 h 52 » — jamais un nombre de secondes brut."""
    minutes = max(0, int(age_seconds // 60))
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d}"


def freshness_sentence(
    status: AnalysisFreshness, age_seconds: float, offline: bool = False
) -> str:
    age = _age_label(age_seconds)
    if offline:
        return f"Mode hors ligne · analyse non actualisée depuis {age}"
    return {
        AnalysisFreshness.FRESH: f"Actualisée il y a {age}",
        AnalysisFreshness.AGING: f"Analyse datant de {age}",
        AnalysisFreshness.STALE: f"Analyse ancienne · {age}",
        AnalysisFreshness.EXPIRED: f"Analyse non actualisée · {age}",
    }[status]


def live_layer(
    snapshot: AnalysisContextSnapshot,
    market: dict[str, Any] | None,
    now: datetime | None = None,
    drift_threshold_pct: float = DRIFT_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Join the live price to a stored analysis without merging the two clocks."""
    from ..core.usability import assess_engine, page_status

    reference = now or datetime.now(UTC)
    families = dict(snapshot.families)
    families["price"] = price_family(market, reference)

    engines = {
        name: assess_engine(
            name, families, mode="price_only_fallback" if name == "direction" else "full"
        )
        for name in (
            "price", "direction", "persistence", "volatility", "funding",
            "positioning", "crowding", "edge", "action",
        )
    }
    status, status_reason = page_status(families, engines)

    live_price = (market or {}).get("price_usd")
    analysis_price = snapshot.price_at_analysis
    drift_pct = None
    if analysis_price and live_price:
        drift_pct = round((live_price / analysis_price - 1) * 100, 3)
    severity = (
        "NONE" if drift_pct is None or abs(drift_pct) < drift_threshold_pct
        else "SEVERE" if abs(drift_pct) >= DRIFT_SEVERE_PCT
        else "NOTABLE"
    )
    age_seconds = round((reference - snapshot.analysis_time).total_seconds(), 1)
    # Une analyse vieille de quatre heures n'est pas une analyse actuelle.
    # L'état est calculé ici et voyage avec le payload: laisser l'écran le
    # deviner, c'est laisser chaque écran le deviner différemment.
    freshness = analysis_freshness(age_seconds)
    return {
        "analysis": {
            "analysis_id": snapshot.analysis_id,
            "computed_at": snapshot.analysis_time.isoformat(),
            "age_seconds": age_seconds,
            "freshness_status": freshness.value,
            "freshness_sentence": freshness_sentence(freshness, age_seconds),
            "verdict_is_actionable": freshness.is_actionable,
            "freshness_limits": _freshness_limits(),
            "price_at_analysis": analysis_price,
            "live_price": live_price,
            "price_drift_pct": drift_pct,
            # Beyond this, the reading describes a price the market has left.
            "drift_threshold_pct": drift_threshold_pct,
            "drift_severity": severity,
            "stale_for_current_price": severity != "NONE",
            "price_freshness": families["price"].freshness.value,
            "note": (
                "Le prix est en direct; l'analyse est calculée sur la dernière "
                "clôture 4H. L'écart entre les deux est affiché, jamais absorbé."
            ),
        },
        "families": families,
        "engines": engines,
        "overall_status": status,
        "overall_status_reason": status_reason,
    }
