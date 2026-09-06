"""AlertEngine - notify on what changed, not on what is simply true.

The failure mode of a naive alerting system is spam: a condition that stays
true for three days fires on every collection cycle, and the user stops
reading. Two mechanisms prevent that here:

  * **dedup_key** - a stable identity for "the same alert". A funding-extreme
    alert on BTC has one key regardless of when it fires.
  * **cooldown** - per alert kind, how long the same key stays silent after
    firing. Set from how fast the underlying condition can meaningfully change.

State-change alerts (regime, entry timing) additionally encode the transition
in their key, so BULLISH->NEUTRAL fires even if BULLISH->BEARISH fired
yesterday: those are genuinely different events.

Every alert carries a `reason` explaining what triggered it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from ..config_loader import threshold
from ..core.enums import AlertImportance, AlertKind, Asset
from ..core.models import Alert
from ..db.base import AlertRow
from ..db.session import session_scope
from ..logging_setup import get_logger

log = get_logger("engines.alerts")

# How long the same dedup_key stays silent, in minutes. Tuned to the pace of
# the underlying condition: funding can stay extreme for days, a breakout is a
# one-off event.
COOLDOWN_MINUTES: dict[str, int] = {
    AlertKind.ETF_INFLOW_SPIKE.value: 1440,
    AlertKind.ETF_OUTFLOW_SPIKE.value: 1440,
    AlertKind.FUNDING_EXTREME.value: 720,
    AlertKind.OPEN_INTEREST_SPIKE.value: 360,
    AlertKind.BREAKOUT.value: 720,
    AlertKind.RSI_DIVERGENCE.value: 720,
    AlertKind.MAJOR_REGULATORY_NEWS.value: 2880,
    AlertKind.FOMC_TODAY.value: 360,
    AlertKind.CPI_TODAY.value: 360,
    AlertKind.WHALE_MOVEMENT.value: 720,
    AlertKind.STABLECOIN_LIQUIDITY_SHIFT.value: 1440,
    AlertKind.HIGH_CONTRADICTION.value: 720,
    AlertKind.MARKET_REGIME_CHANGE.value: 60,
    "ENTRY_TIMING_CHANGE": 120,
    "FAKE_BREAKOUT": 720,
}
DEFAULT_COOLDOWN_MINUTES = 360


def recent_keys(within_minutes: int = 2880) -> dict[str, datetime]:
    """Most recent firing time per dedup key."""
    cutoff = datetime.now(UTC) - timedelta(minutes=within_minutes)
    with session_scope() as s:
        rows = s.execute(
            select(AlertRow.dedup_key, AlertRow.triggered_at)
            .where(AlertRow.triggered_at >= cutoff, AlertRow.dedup_key.isnot(None))
        ).all()

    latest: dict[str, datetime] = {}
    for key, triggered in rows:
        triggered = triggered if triggered.tzinfo else triggered.replace(tzinfo=UTC)
        if key not in latest or triggered > latest[key]:
            latest[key] = triggered
    return latest


class AlertEngine:
    name = "alert_engine"

    def __init__(self) -> None:
        self.t = threshold("alerts", default={}) or {}
        self.t_deriv = threshold("derivatives", default={}) or {}

    def evaluate(
        self,
        asset: Asset,
        ctx: dict[str, Any],
        previous: dict[str, Any] | None = None,
        apply_cooldown: bool = True,
    ) -> list[Alert]:
        """Build the candidate alerts, then filter them through the cooldown.

        `previous` carries the last known regime/timing so state CHANGES can be
        detected - the alerts that matter most are transitions, not levels.
        """
        candidates: list[tuple[Alert, str]] = []

        def add(
            kind: str, importance: AlertImportance, title: str,
            detail: str, reason: str, dedup: str, evidence: list[str] | None = None,
        ) -> None:
            candidates.append((
                Alert(
                    kind=kind, importance=importance.value, asset=asset,
                    title=title, detail=detail, triggered_at=datetime.now(UTC),
                    evidence_ids=evidence or [],
                ),
                f"{asset.value}:{dedup}",
            ))
            candidates[-1][0].__dict__.setdefault("reason", reason)

        # --- state changes: the highest-signal alerts ------------------------
        regime = ctx.get("regime")
        if regime is not None and getattr(regime, "regime", None):
            current = regime.regime.value
            prior = (previous or {}).get("regime")
            if prior and prior != current:
                add(
                    AlertKind.MARKET_REGIME_CHANGE.value, AlertImportance.IMPORTANT,
                    f"{asset.value} market regime: {prior} -> {current}",
                    regime.summary,
                    reason=(
                        f"The multi-factor regime score moved to {regime.regime_score:+.0f}, "
                        f"crossing the boundary from {prior} into {current}. "
                        f"Confidence {regime.confidence:.0f}%."
                    ),
                    # The transition is part of the key: a different transition
                    # is a different event and should not be suppressed.
                    dedup=f"regime:{prior}->{current}",
                    evidence=regime.evidence_ids[:5],
                )

        timing = ctx.get("entry_timing")
        if timing is not None and getattr(timing, "timing", None):
            current = timing.timing.value
            prior = (previous or {}).get("entry_timing")
            if prior and prior != current:
                # Only report moves that cross a meaningful boundary, not every
                # wobble around a threshold.
                order = ["VERY_UNFAVORABLE", "UNFAVORABLE", "WAIT", "FAVORABLE", "VERY_FAVORABLE"]
                if prior in order and current in order:
                    distance = abs(order.index(current) - order.index(prior))
                else:
                    distance = 2
                if distance >= 1:
                    importance = (
                        AlertImportance.IMPORTANT if distance >= 2 else AlertImportance.WATCH
                    )
                    add(
                        "ENTRY_TIMING_CHANGE", importance,
                        f"{asset.value} entry timing: {prior} -> {current}",
                        timing.summary,
                        reason=(
                            f"Timing score is now {timing.timing_score:+.0f}. "
                            + (f"Main driver: {timing.negatives[0]}" if timing.negatives
                               else f"Main driver: {timing.positives[0]}" if timing.positives
                               else "Driven by the weighted factor set.")
                        ),
                        dedup=f"timing:{prior}->{current}",
                        evidence=timing.evidence_ids[:5],
                    )

        # --- LOT 4 state changes ---------------------------------------------
        # These describe conditions, never actions. An edge appearing or
        # disappearing is the most consequential change the system can report,
        # because it changes whether anything is actionable at all.
        edge = ctx.get("edge")
        if edge is not None and getattr(edge, "state", None):
            current = edge.state.value
            prior = (previous or {}).get("edge_state")
            if prior and prior != current:
                importance = (
                    AlertImportance.CRITICAL
                    if current == "POSITIVE_EDGE" or prior == "POSITIVE_EDGE"
                    else AlertImportance.IMPORTANT
                )
                add(
                    "EDGE_STATE_CHANGE", importance,
                    f"{asset.value} measured edge: {prior} -> {current}",
                    edge.statement[:200],
                    reason=(
                        f"{edge.admitted_count} relationship(s) now pass every filter "
                        f"and {edge.rejected_count} were rejected. This is a statement "
                        "about demonstrated predictive ability, not about direction."
                    ),
                    dedup=f"edge:{prior}->{current}",
                )

        crowding = ctx.get("crowding")
        if crowding is not None and getattr(crowding, "level", None):
            current = crowding.level.value
            prior = (previous or {}).get("crowding")
            if prior and prior != current and current in ("ELEVATED", "EXTREME", "LOW"):
                add(
                    "CROWDING_CHANGE",
                    AlertImportance.IMPORTANT if current == "EXTREME"
                    else AlertImportance.WATCH,
                    f"{asset.value} leverage crowding: {prior} -> {current}",
                    crowding.interpretation[:200],
                    reason=(
                        f"Crowding score {crowding.score}/100. Direction remains UNKNOWN: "
                        "open interest counts contracts, not sides."
                    ),
                    dedup=f"crowding:{prior}->{current}",
                )

        volatility = ctx.get("volatility_regime")
        if volatility is not None and getattr(volatility, "regime", None):
            current = str(volatility.regime)
            prior = (previous or {}).get("volatility_regime")
            if prior and prior != current and current != "UNKNOWN":
                add(
                    "VOLATILITY_REGIME_CHANGE", AlertImportance.WATCH,
                    f"{asset.value} volatility regime: {prior} -> {current}",
                    volatility.interpretation[:200],
                    reason=(
                        f"ATR sits at the {volatility.atr_percentile}th percentile and is "
                        f"{volatility.direction.lower()}. This is the size of moves, not "
                        "their direction."
                    ),
                    dedup=f"volatility:{prior}->{current}",
                )

        leverage_state = ctx.get("leverage_state")
        if leverage_state is not None and getattr(leverage_state, "state", None):
            current = leverage_state.state.value
            prior = (previous or {}).get("leverage_state")
            if prior and prior != current and current != "UNDETERMINED":
                add(
                    "LEVERAGE_STATE_CHANGE", AlertImportance.WATCH,
                    f"{asset.value} leverage state: {prior} -> {current}",
                    leverage_state.interpretation[:200],
                    reason=(
                        f"Price moved {leverage_state.price_change_pct}% while open "
                        f"interest moved {leverage_state.oi_change_pct}% over the window."
                    ),
                    dedup=f"leverage:{prior}->{current}",
                )

        # --- LOT 5 structural alerts -----------------------------------------
        # Every one of these describes a structural condition. None says to buy
        # or sell, and each carries the measured edge alongside so the reader
        # sees immediately that the structure is descriptive.
        location = ctx.get("structural_location")
        edge_state = str(
            getattr(ctx.get("edge"), "state", None).value
            if getattr(ctx.get("edge"), "state", None) else "NO_MEASURABLE_EDGE"
        )

        if location is not None and getattr(location, "state", None):
            current = location.state.value
            prior = (previous or {}).get("structural_location")
            detected = getattr(location, "detected_range", None)

            approach_states = {
                "AT_RANGE_BOTTOM": ("RANGE_BOTTOM_APPROACH", AlertImportance.IMPORTANT),
                "NEAR_RANGE_BOTTOM": ("RANGE_BOTTOM_APPROACH", AlertImportance.WATCH),
                "AT_RANGE_TOP": ("RANGE_TOP_APPROACH", AlertImportance.IMPORTANT),
                "NEAR_RANGE_TOP": ("RANGE_TOP_APPROACH", AlertImportance.WATCH),
                "ABOVE_RANGE": ("RANGE_BREAKOUT_ATTEMPT", AlertImportance.IMPORTANT),
                "BELOW_RANGE": ("RANGE_BREAKOUT_ATTEMPT", AlertImportance.IMPORTANT),
            }
            if prior and prior != current and current in approach_states:
                kind, importance = approach_states[current]
                zone_note = ""
                if detected and detected.valid:
                    zone = (
                        detected.bottom_zone if "BOTTOM" in current or current == "BELOW_RANGE"
                        else detected.top_zone
                    )
                    if zone:
                        zone_note = (
                            f" Zone {zone.low:.2f}-{zone.high:.2f}, tested "
                            f"{zone.quality.touches} times, quality "
                            f"{zone.quality.score:.0f}/100."
                        )
                add(
                    kind, importance,
                    f"{asset.value} {location.timeframe} structure: {prior} -> {current}",
                    (location.range_summary or "")[:200],
                    reason=(
                        f"Price moved to {current.replace('_', ' ').lower()}.{zone_note} "
                        f"Measured edge: {edge_state}. This describes where price sits, "
                        "not what it will do."
                    ),
                    dedup=f"location:{location.timeframe}:{prior}->{current}",
                )

        breakout = ctx.get("breakout")
        if breakout is not None and getattr(breakout, "state", None):
            current = breakout.state.value
            prior = (previous or {}).get("breakout_state")
            interesting = {
                "CONFIRMED_BREAKOUT": ("RANGE_BREAKOUT_CONFIRMED", AlertImportance.IMPORTANT),
                "FAKEOUT": ("RANGE_DEVIATION", AlertImportance.IMPORTANT),
                "REINTEGRATION": ("RANGE_REINTEGRATION", AlertImportance.WATCH),
                "BREAKOUT_RETEST": ("HIGH_QUALITY_RETEST", AlertImportance.WATCH),
            }
            if prior and prior != current and current in interesting:
                kind, importance = interesting[current]
                quality = getattr(breakout, "quality_score", None)
                # A retest is only worth flagging when the break was convincing.
                if kind == "HIGH_QUALITY_RETEST" and (quality or 0) < 60:
                    pass
                else:
                    add(
                        kind, importance,
                        f"{asset.value} breakout state: {prior} -> {current}",
                        (breakout.interpretation or "")[:200],
                        reason=(
                            f"Break conviction {quality}/100. Measured edge: {edge_state}. "
                            "Conviction scores how clean the break is, not what follows."
                        ),
                        dedup=f"breakout:{prior}->{current}",
                    )

        structure = ctx.get("market_structure")
        if structure is not None and getattr(structure, "state", None):
            current = structure.state.value
            prior = (previous or {}).get("market_structure")
            if prior and prior != current and current != "UNCLEAR":
                add(
                    "MARKET_STRUCTURE_CHANGED", AlertImportance.IMPORTANT,
                    f"{asset.value} market structure: {prior} -> {current}",
                    (structure.interpretation or "")[:200],
                    reason=(
                        f"Confirmed swing sequence [{' '.join(structure.labels)}]. "
                        f"Measured edge: {edge_state}. BOS and CHOCH are descriptions, "
                        "not signals."
                    ),
                    dedup=f"structure:{prior}->{current}",
                )

        opportunity = ctx.get("entry_opportunity")
        if opportunity is not None and getattr(opportunity, "state", None):
            current = opportunity.state.value
            prior = (previous or {}).get("entry_opportunity")
            if prior and prior != current and current != "INSUFFICIENT_DATA":
                order = [
                    "VERY_UNFAVORABLE", "UNFAVORABLE", "NEUTRAL",
                    "FAVORABLE", "VERY_FAVORABLE",
                ]
                distance = (
                    abs(order.index(current) - order.index(prior))
                    if prior in order and current in order else 2
                )
                if distance >= 1:
                    add(
                        "ENTRY_OPPORTUNITY_CHANGED",
                        AlertImportance.IMPORTANT if distance >= 2 else AlertImportance.WATCH,
                        f"{asset.value} entry opportunity: {prior} -> {current}",
                        (opportunity.statement or "")[:200],
                        reason=(
                            "Why now: "
                            + "; ".join(opportunity.why_now[:3])
                            + f". Measured edge: {opportunity.measured_edge_state}. "
                            "This describes the configuration; it is not a "
                            "recommendation to act."
                        ),
                        dedup=f"opportunity:{prior}->{current}",
                    )

        pattern = ctx.get("structural_patterns")
        if pattern:
            for detected_pattern in pattern[:3]:
                state = getattr(detected_pattern, "state", None)
                if state is None:
                    continue
                prior_key = f"pattern:{detected_pattern.name}"
                prior = (previous or {}).get(prior_key)
                if prior == state.value or state.value not in ("CONFIRMED", "FAILED"):
                    continue
                add(
                    "PATTERN_CONFIRMED" if state.value == "CONFIRMED" else "PATTERN_FAILED",
                    AlertImportance.WATCH,
                    f"{asset.value} {detected_pattern.name} {state.value.lower()}",
                    detected_pattern.notes[:200],
                    reason=(
                        f"Recognition confidence {detected_pattern.recognition_confidence:.0f}/100 "
                        f"({detected_pattern.pattern_class.value}). Textbook reading: "
                        f"{detected_pattern.direction_if_textbook.lower()}. Measured edge: "
                        f"{detected_pattern.edge_state.value}. Recognition confidence is "
                        "NOT a probability of any outcome."
                    ),
                    dedup=f"pattern:{detected_pattern.name}:{state.value}",
                )

        # --- ETF -------------------------------------------------------------
        etf = ctx.get("etf")
        if etf is not None and getattr(etf, "available", False) and etf.latest_total is not None:
            inflow_threshold = float(self.t.get("etf_inflow_spike_musd", 500))
            outflow_threshold = float(self.t.get("etf_outflow_spike_musd", -500))
            day = etf.latest_date.strftime("%Y-%m-%d") if etf.latest_date else "unknown"
            if etf.latest_total >= inflow_threshold:
                add(
                    AlertKind.ETF_INFLOW_SPIKE.value, AlertImportance.IMPORTANT,
                    f"{asset.value} ETF inflow spike: {etf.latest_total:+.0f}M USD",
                    f"Daily net flow on {day}",
                    reason=(
                        f"Net daily flow of {etf.latest_total:+.1f}M USD exceeds the "
                        f"{inflow_threshold:.0f}M alert threshold. 5-day average: "
                        f"{etf.ma_5d:+.1f}M." if etf.ma_5d is not None else
                        f"Net daily flow of {etf.latest_total:+.1f}M USD exceeds the threshold."
                    ),
                    dedup=f"etf_inflow:{day}", evidence=etf.evidence_ids[:5],
                )
            elif etf.latest_total <= outflow_threshold:
                add(
                    AlertKind.ETF_OUTFLOW_SPIKE.value, AlertImportance.IMPORTANT,
                    f"{asset.value} ETF outflow spike: {etf.latest_total:+.0f}M USD",
                    f"Daily net flow on {day}",
                    reason=(
                        f"Net daily flow of {etf.latest_total:+.1f}M USD is below the "
                        f"{outflow_threshold:.0f}M alert threshold."
                    ),
                    dedup=f"etf_outflow:{day}", evidence=etf.evidence_ids[:5],
                )

            if etf.flow_price_divergence in (
                "ACCUMULATION_BEFORE_PRICE", "DISTRIBUTION_INTO_STRENGTH"
            ):
                add(
                    AlertKind.ETF_INFLOW_SPIKE.value, AlertImportance.WATCH,
                    f"{asset.value} ETF/price divergence: {etf.flow_price_divergence}",
                    etf.divergence_detail or "",
                    reason=(
                        "Flows and price are moving in opposite directions over the "
                        "lookback window. " + (etf.divergence_detail or "")
                    ),
                    dedup=f"etf_divergence:{etf.flow_price_divergence}",
                )

        # --- derivatives -----------------------------------------------------
        deriv = ctx.get("derivatives")
        if deriv is not None and getattr(deriv, "available", False):
            if deriv.funding_state in ("EXTREME_POSITIVE", "EXTREME_NEGATIVE"):
                add(
                    AlertKind.FUNDING_EXTREME.value, AlertImportance.IMPORTANT,
                    f"{asset.value} funding {deriv.funding_state}",
                    f"Funding {deriv.funding_rate:.6f} per 8h",
                    reason=(
                        f"Funding rate {deriv.funding_rate:.6f} per 8h "
                        f"({deriv.funding_annualized_pct:+.1f}% annualised) crossed the "
                        f"extreme threshold. Crowded positioning raises squeeze risk in "
                        f"the opposite direction."
                    ),
                    dedup=f"funding:{deriv.funding_state}",
                    evidence=deriv.evidence_ids[:5],
                )
            oi_change = deriv.oi_change_24h_pct
            if oi_change is not None and abs(oi_change) >= float(self.t.get("oi_spike_pct", 15)):
                add(
                    AlertKind.OPEN_INTEREST_SPIKE.value, AlertImportance.WATCH,
                    f"{asset.value} open interest {oi_change:+.1f}% in 24h",
                    deriv.regime_interpretation or "",
                    reason=(
                        f"Open interest moved {oi_change:+.1f}% over 24h, past the "
                        f"{self.t.get('oi_spike_pct', 15)}% threshold. "
                        + (deriv.regime_interpretation or "")
                    ),
                    dedup=f"oi_spike:{'up' if oi_change > 0 else 'down'}",
                )

        # --- technical events -------------------------------------------------
        snapshots_ctx = ctx.get("snapshots") or {}
        for tf, snap in snapshots_ctx.items():
            if snap is None or not snap.has_data:
                continue
            tf_code = getattr(tf, "value", str(tf))
            for pattern in snap.patterns:
                if pattern.pattern == "breakout" and pattern.confirmation_state.value == "CONFIRMED":
                    add(
                        AlertKind.BREAKOUT.value, AlertImportance.IMPORTANT,
                        f"{asset.value} {tf_code} breakout confirmed ({pattern.direction.value})",
                        pattern.notes,
                        reason=(
                            f"Price closed decisively beyond the prior range on "
                            f"{tf_code} with volume confirmation. {pattern.notes}"
                        ),
                        dedup=f"breakout:{tf_code}:{pattern.direction.value}",
                    )
                elif pattern.pattern == "fake_breakout":
                    add(
                        "FAKE_BREAKOUT", AlertImportance.IMPORTANT,
                        f"{asset.value} {tf_code} fake breakout ({pattern.direction.value})",
                        pattern.notes,
                        reason=f"A breakout was rejected within a few bars. {pattern.notes}",
                        dedup=f"fake_breakout:{tf_code}:{pattern.direction.value}",
                    )
            for div in snap.divergences:
                if div.strength >= 55:
                    add(
                        AlertKind.RSI_DIVERGENCE.value, AlertImportance.WATCH,
                        f"{asset.value} {tf_code} {div.indicator} {div.kind} divergence",
                        f"Strength {div.strength:.0f}/100",
                        reason=(
                            f"Price and {div.indicator} disagree across two confirmed pivots "
                            f"on {tf_code} (strength {div.strength:.0f}/100). A divergence is "
                            "a warning, not a signal - it needs structural confirmation."
                        ),
                        dedup=f"divergence:{tf_code}:{div.indicator}:{div.kind}",
                    )

        # --- macro --------------------------------------------------------------
        macro = ctx.get("macro")
        if macro is not None and getattr(macro, "imminent_event", None):
            event = macro.imminent_event
            kind = (
                AlertKind.FOMC_TODAY.value if event.kind == "FOMC"
                else AlertKind.CPI_TODAY.value if event.kind == "CPI"
                else AlertKind.MAJOR_REGULATORY_NEWS.value
            )
            add(
                kind, AlertImportance.CRITICAL,
                f"{event.name} in {event.hours_until:.1f}h",
                f"Importance {event.importance}",
                reason=(
                    f"{event.name} is scheduled for "
                    f"{event.scheduled_at:%Y-%m-%d %H:%M} UTC, within the imminent window. "
                    "Volatility around scheduled releases is elevated and direction is "
                    "not forecastable."
                ),
                dedup=f"macro_event:{event.kind}:{event.scheduled_at:%Y-%m-%d}",
            )

        # --- liquidity ----------------------------------------------------------
        liq = ctx.get("liquidity")
        if (
            liq is not None and getattr(liq, "available", False)
            and liq.regime in ("STRONG_EXPANSION", "STRONG_CONTRACTION")
        ):
            add(
                AlertKind.STABLECOIN_LIQUIDITY_SHIFT.value, AlertImportance.IMPORTANT,
                f"Stablecoin liquidity {liq.regime}",
                f"7-day change {liq.change_7d_pct:+.2f}%" if liq.change_7d_pct is not None else "",
                reason=(
                    f"Aggregate stablecoin supply changed {liq.change_7d_pct:+.2f}% over 7 days, "
                    "crossing the strong-move threshold. This is the closest proxy the system "
                    "has to crypto money supply."
                    if liq.change_7d_pct is not None else f"Liquidity regime {liq.regime}."
                ),
                dedup=f"liquidity:{liq.regime}",
            )

        # --- regulation ---------------------------------------------------------
        reg = ctx.get("regulation")
        if reg is not None and getattr(reg, "available", False):
            for event in reg.events[:3]:
                if event.legal_status.is_binding and event.importance >= 70:
                    add(
                        AlertKind.MAJOR_REGULATORY_NEWS.value, AlertImportance.IMPORTANT,
                        f"[{event.legal_status.value}] {event.institution}: {event.title[:80]}",
                        event.summary[:200],
                        reason=(
                            f"A binding regulatory action ({event.legal_status.value}) was "
                            f"published by {event.institution} on "
                            f"{event.published_at:%Y-%m-%d} with estimated importance "
                            f"{event.importance:.0f}/100."
                        ),
                        dedup=f"regulation:{event.source_url or event.title[:60]}",
                    )

        # --- contradictions -----------------------------------------------------
        contradictions = ctx.get("contradictions")
        if contradictions is not None and getattr(contradictions, "is_high", False):
            top = contradictions.contradictions[0] if contradictions.contradictions else None
            add(
                AlertKind.HIGH_CONTRADICTION.value, AlertImportance.WATCH,
                f"{asset.value}: signals strongly contradictory",
                contradictions.summary,
                reason=(
                    f"Contradiction strength reached "
                    f"{contradictions.max_strength:.0f}/100. "
                    + (f"Strongest conflict: {top.description}" if top else "")
                ),
                dedup="contradiction:high",
            )

        # --- whales ---------------------------------------------------------------
        whale = ctx.get("whale")
        if (
            whale is not None and getattr(whale, "available", False)
            and whale.behaviour in ("to_exchange", "from_exchange")
        ):
            add(
                AlertKind.WHALE_MOVEMENT.value, AlertImportance.WATCH,
                f"{asset.value} whale flow: {whale.behaviour}",
                f"Reliability {whale.reliability.value}",
                reason=(
                    f"Large-holder exchange flow classified as {whale.behaviour} "
                    f"with {whale.reliability.value} reliability, using a "
                    f"{whale.threshold:.0f} {whale.threshold_unit} whale threshold."
                ),
                dedup=f"whale:{whale.behaviour}",
            )

        if not apply_cooldown:
            return [alert for alert, _ in candidates]

        return self._filter_cooldown(candidates)

    def _filter_cooldown(self, candidates: list[tuple[Alert, str]]) -> list[Alert]:
        """Drop alerts whose key fired recently enough to still be on cooldown."""
        latest = recent_keys()
        now = datetime.now(UTC)
        kept: list[Alert] = []
        seen_in_batch: set[str] = set()

        for alert, key in candidates:
            # Two identical keys inside one run is always a duplicate.
            if key in seen_in_batch:
                continue
            seen_in_batch.add(key)

            cooldown = COOLDOWN_MINUTES.get(alert.kind, DEFAULT_COOLDOWN_MINUTES)
            last = latest.get(key)
            if last is not None and (now - last) < timedelta(minutes=cooldown):
                log.debug("alert_suppressed", key=key, kind=alert.kind)
                continue

            payload = alert.model_dump()
            payload["dedup_key"] = key
            payload["reason"] = alert.__dict__.get("reason", "")
            kept.append(Alert(**{k: v for k, v in payload.items() if k in Alert.model_fields}))
            kept[-1].__dict__["dedup_key"] = key
            kept[-1].__dict__["reason"] = payload["reason"]

        return kept

    @staticmethod
    def to_rows(alerts: list[Alert]) -> list[dict[str, Any]]:
        """Serialise for persistence, carrying dedup_key and reason through."""
        rows = []
        for alert in alerts:
            row = alert.model_dump(mode="json")
            row["dedup_key"] = alert.__dict__.get("dedup_key")
            row["reason"] = alert.__dict__.get("reason", "")
            rows.append(row)
        return rows
