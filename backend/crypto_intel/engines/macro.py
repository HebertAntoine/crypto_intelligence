"""MacroAnalyzer + event calendar.

Crypto trades as a liquidity-sensitive risk asset, so rates, the dollar and
equity risk appetite matter. Event proximity is explicit: a CPI print due in
20 minutes and a figure released 10 days ago are not the same input, and the
engine weights them accordingly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from ..config_loader import threshold
from ..core.enums import Direction, Freshness
from ..core.freshness import worst_freshness
from ..core.models import MacroEvent, Observation


class MacroAnalysis(BaseModel):
    available: bool = True
    unavailable_reason: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    changes: dict[str, float] = Field(default_factory=dict)
    risk_appetite: str = "UNKNOWN"
    dollar_trend: str = "UNKNOWN"
    rates_trend: str = "UNKNOWN"
    upcoming_events: list[MacroEvent] = Field(default_factory=list)
    imminent_event: MacroEvent | None = None
    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class MacroAnalyzer:
    name = "macro_analyzer"

    def __init__(self) -> None:
        self.t = threshold("macro", default={}) or {}
        self.prox = self.t.get("event_proximity", {})

    def load_calendar(self, now: datetime | None = None) -> list[MacroEvent]:
        """Read primary-source events already normalised by the collector."""
        from ..db import repo

        now = now or datetime.now(UTC)
        events: list[MacroEvent] = []
        for event in repo.list_future_events(
            start=now - timedelta(days=7),
            end=now + timedelta(days=365),
            include_expired=True,
            limit=500,
        ):
            if event.category.value not in ("MACRO", "MONETARY_POLICY"):
                continue
            dt = event.scheduled_at
            if dt is None:
                continue
            events.append(MacroEvent(
                name=event.title, kind=event.event_type, scheduled_at=dt,
                importance=event.importance.value,
                hours_until=(dt - now).total_seconds() / 3600.0,
                is_past=dt < now, assets_impact=event.affected_assets,
            ))
        events.sort(key=lambda ev: ev.scheduled_at)
        return events

    def sync_calendar_to_db(self, now: datetime | None = None) -> int:
        """Compatibility mirror from rich official events to the legacy table."""
        import hashlib

        from ..db import repo

        rows = []
        for ev in self.load_calendar(now):
            eid = "evt_" + hashlib.sha1(
                f"{ev.kind}|{ev.name}|{ev.scheduled_at.isoformat()}".encode()
            ).hexdigest()[:16]
            rows.append({
                "id": eid, "kind": ev.kind, "name": ev.name,
                "scheduled_at": ev.scheduled_at, "importance": ev.importance,
                "summary": "", "source_name": "future_events",
                "assets": [a.value for a in ev.assets_impact],
            })
        return repo.save_events(rows)

    def analyze(
        self,
        observations: list[Observation],
        now: datetime | None = None,
        unavailable_reason: str | None = None,
    ) -> MacroAnalysis:
        now = now or datetime.now(UTC)
        calendar = self.load_calendar(now)
        upcoming = [e for e in calendar if not e.is_past][:8]
        imminent = next(
            (e for e in upcoming
             if e.hours_until is not None
             and 0 <= e.hours_until <= float(self.prox.get("imminent_hours", 4))),
            None,
        )

        if unavailable_reason or not observations:
            findings = []
            if imminent:
                findings.append(
                    f"{imminent.name} is due in {imminent.hours_until:.1f}h "
                    f"({imminent.importance}) - expect elevated volatility around the release"
                )
            return MacroAnalysis(
                available=False,
                unavailable_reason=unavailable_reason or "UNAVAILABLE - no macro data",
                upcoming_events=upcoming, imminent_event=imminent, findings=findings,
                missing=["macro series (set FRED_API_KEY) and/or indices"],
            )

        series: dict[str, list[Observation]] = {}
        for o in observations:
            series.setdefault(o.metric, []).append(o)
        for lst in series.values():
            lst.sort(key=lambda o: o.timestamp)

        metrics = {m: lst[-1].numeric_value for m, lst in series.items()
                   if lst[-1].numeric_value is not None}
        changes: dict[str, float] = {}
        for m, lst in series.items():
            values = [o.numeric_value for o in lst if o.numeric_value is not None]
            if len(values) >= 6:
                past = values[-6]
                if past:
                    changes[m] = (values[-1] - past) / abs(past) * 100.0

        findings: list[str] = []
        missing: list[str] = []
        score = 0.0

        # --- dollar ----------------------------------------------------------
        dollar_trend = "UNKNOWN"
        dxy_change = changes.get("macro.dxy") or changes.get("macro.dxy_broad")
        if dxy_change is not None:
            strong = float((self.t.get("dxy") or {}).get("strong_move_pct", 1.0))
            if dxy_change >= strong:
                dollar_trend = "STRENGTHENING"
                score -= 18
                findings.append(
                    f"Dollar strengthening ({dxy_change:+.2f}%) - historically a headwind "
                    "for crypto and risk assets"
                )
            elif dxy_change <= -strong:
                dollar_trend = "WEAKENING"
                score += 18
                findings.append(
                    f"Dollar weakening ({dxy_change:.2f}%) - historically supportive for crypto"
                )
            else:
                dollar_trend = "STABLE"
        else:
            missing.append("DXY")

        # --- rates -----------------------------------------------------------
        rates_trend = "UNKNOWN"
        us10y = metrics.get("macro.us10y") or metrics.get("macro.us10y_yahoo")
        y10_change = changes.get("macro.us10y") or changes.get("macro.us10y_yahoo")
        if us10y is not None:
            findings.append(f"US 10Y yield {us10y:.2f}%")
            if y10_change is not None:
                # ~15bp on a 4% yield is roughly a 3.75% relative move.
                if y10_change > 3:
                    rates_trend, score = "RISING", score - 12
                    findings.append(
                        f"Yields rising ({y10_change:+.1f}% relative) - tighter financial "
                        "conditions weigh on risk assets"
                    )
                elif y10_change < -3:
                    rates_trend, score = "FALLING", score + 12
                    findings.append(
                        f"Yields falling ({y10_change:.1f}% relative) - easier financial conditions"
                    )
                else:
                    rates_trend = "STABLE"
        else:
            missing.append("US Treasury yields (set FRED_API_KEY)")

        us2y = metrics.get("macro.us2y")
        if us10y is not None and us2y is not None:
            spread = us10y - us2y
            findings.append(
                f"10Y-2Y spread {spread:+.2f}pp"
                + (" (inverted - historically a recession signal)" if spread < 0 else "")
            )

        # --- risk appetite ---------------------------------------------------
        risk = "UNKNOWN"
        spx_change = changes.get("macro.sp500")
        ndx_change = changes.get("macro.nasdaq")
        vix = metrics.get("macro.vix")
        equity = ndx_change if ndx_change is not None else spx_change
        if equity is not None:
            if equity > 1.5:
                risk, score = "RISK_ON", score + 15
                findings.append(f"Equities firm ({equity:+.2f}%) - risk appetite is healthy")
            elif equity < -1.5:
                risk, score = "RISK_OFF", score - 15
                findings.append(f"Equities weak ({equity:.2f}%) - risk appetite deteriorating")
            else:
                risk = "NEUTRAL"
        else:
            missing.append("equity indices")

        if vix is not None:
            findings.append(f"VIX {vix:.1f}")
            if vix > 25:
                score -= 10
                findings.append("VIX above 25 - elevated fear in traditional markets")
            elif vix < 14:
                score += 5

        fed_funds = metrics.get("macro.fed_funds_rate")
        if fed_funds is not None:
            findings.append(f"Effective fed funds rate {fed_funds:.2f}%")
        else:
            missing.append("Fed funds rate (set FRED_API_KEY)")

        # --- event proximity --------------------------------------------------
        if imminent:
            findings.append(
                f"{imminent.name} is due in {imminent.hours_until:.1f}h ({imminent.importance}) - "
                "expect elevated volatility; positioning ahead of the release is a coin flip"
            )
            # Dampen conviction rather than pick a side before the data.
            score *= 0.6
        elif upcoming:
            nxt = upcoming[0]
            if nxt.hours_until is not None and nxt.hours_until <= float(
                self.prox.get("near_hours", 48)
            ):
                findings.append(
                    f"Next macro event: {nxt.name} in {nxt.hours_until:.0f}h ({nxt.importance})"
                )

        direction = (
            Direction.BULLISH if score > 12
            else Direction.BEARISH if score < -12
            else Direction.NEUTRAL
        )
        return MacroAnalysis(
            available=True, metrics=metrics, changes=changes,
            risk_appetite=risk, dollar_trend=dollar_trend, rates_trend=rates_trend,
            upcoming_events=upcoming, imminent_event=imminent,
            direction=direction, strength=round(max(-100.0, min(100.0, score)), 1),
            freshness=worst_freshness([lst[-1].freshness for lst in series.values()]),
            evidence_ids=[lst[-1].id for lst in series.values()],
            findings=findings, missing=missing,
        )
