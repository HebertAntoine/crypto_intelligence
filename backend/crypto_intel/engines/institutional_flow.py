"""Multi-session ETF/institutional flow state for BTC, ETH and SOL."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from ..core.enums import Asset
from ..core.models import Observation


class InstitutionalFlowState(StrEnum):
    STRONG_INFLOW = "STRONG_INFLOW"
    INFLOW = "INFLOW"
    NEUTRAL = "NEUTRAL"
    OUTFLOW = "OUTFLOW"
    STRONG_OUTFLOW = "STRONG_OUTFLOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class InstitutionalFlowAnalysis(BaseModel):
    available: bool
    asset: Asset
    state: InstitutionalFlowState = InstitutionalFlowState.INSUFFICIENT_DATA
    latest_flow_musd: float | None = None
    rolling_3_sessions_musd: float | None = None
    rolling_5_sessions_musd: float | None = None
    rolling_20_sessions_musd: float | None = None
    acceleration_musd_per_session: float | None = None
    reversal: bool | None = None
    sessions_available: int = 0
    observed_at: datetime | None = None
    age_seconds: float | None = None
    unavailable_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: list[dict[str, str | None]] = Field(default_factory=list)
    explanation: str = ""


def _window(values: list[float], length: int) -> float | None:
    return sum(values[-length:]) if len(values) >= length else None


class InstitutionalFlowEngine:
    """Aggregate per-fund rows before applying trading-session windows."""

    def analyze(
        self,
        asset: Asset,
        observations: list[Observation],
        *,
        now: datetime | None = None,
    ) -> InstitutionalFlowAnalysis:
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        rows = [
            item
            for item in observations
            if item.asset is asset and item.metric == "etf.flow" and item.numeric_value is not None
        ]
        if not rows:
            return InstitutionalFlowAnalysis(
                available=False,
                asset=asset,
                unavailable_reason=f"UNAVAILABLE - no sourced {asset.value} institutional flow",
                explanation="No neutral value is substituted for missing ETF data.",
            )

        daily: dict[datetime, float] = defaultdict(float)
        for item in rows:
            stamp = item.timestamp if item.timestamp.tzinfo else item.timestamp.replace(tzinfo=UTC)
            day = stamp.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            daily[day] += float(item.numeric_value)
        ordered = sorted(daily.items())
        dates = [date for date, _value in ordered]
        values = [value for _date, value in ordered]
        observed_at = dates[-1]
        age = max(0.0, (reference.astimezone(UTC) - observed_at).total_seconds())

        if len(values) < 3:
            return InstitutionalFlowAnalysis(
                available=False,
                asset=asset,
                latest_flow_musd=values[-1],
                sessions_available=len(values),
                observed_at=observed_at,
                age_seconds=age,
                unavailable_reason="UNAVAILABLE - fewer than 3 reported ETF sessions",
                explanation="A single session is not treated as an institutional trend.",
            )

        # Prefer the full 20-session regime; fall back to five or three only
        # when the source has not yet accumulated a longer history.
        regime_length = 20 if len(values) >= 20 else 5 if len(values) >= 5 else 3
        regime_values = values[-regime_length:]
        regime_average = sum(regime_values) / regime_length
        absolute_scale = sorted(abs(value) for value in values if value != 0)
        median_abs = absolute_scale[len(absolute_scale) // 2] if absolute_scale else 0.0
        normalised = regime_average / median_abs if median_abs else 0.0
        if normalised >= 1.0:
            state = InstitutionalFlowState.STRONG_INFLOW
        elif normalised > 0.15:
            state = InstitutionalFlowState.INFLOW
        elif normalised <= -1.0:
            state = InstitutionalFlowState.STRONG_OUTFLOW
        elif normalised < -0.15:
            state = InstitutionalFlowState.OUTFLOW
        else:
            state = InstitutionalFlowState.NEUTRAL

        acceleration = None
        if len(values) >= 6:
            acceleration = sum(values[-3:]) / 3 - sum(values[-6:-3]) / 3
        reversal = None
        if len(values) >= 8:
            recent = sum(values[-3:])
            prior = sum(values[-8:-3])
            reversal = (recent > 0 > prior) or (recent < 0 < prior)

        provenance = {
            (
                item.provenance.source,
                item.provenance.provider,
                item.provenance.source_url,
            )
            for item in rows
        }
        return InstitutionalFlowAnalysis(
            available=True,
            asset=asset,
            state=state,
            latest_flow_musd=values[-1],
            rolling_3_sessions_musd=_window(values, 3),
            rolling_5_sessions_musd=_window(values, 5),
            rolling_20_sessions_musd=_window(values, 20),
            acceleration_musd_per_session=acceleration,
            reversal=reversal,
            sessions_available=len(values),
            observed_at=observed_at,
            age_seconds=age,
            evidence_ids=sorted({item.id for item in rows}),
            provenance=[
                {"source": source, "provider": provider, "source_url": url}
                for source, provider, url in sorted(provenance, key=lambda item: item[:2])
            ],
            explanation=(
                f"State uses the last {regime_length} reported trading sessions; "
                "the latest day is shown separately and cannot overwrite that regime alone."
            ),
        )
