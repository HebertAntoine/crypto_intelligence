"""The daily intelligence report: everything the system knows, in reading order.

Sixteen sections in a fixed order, then a conclusion of at most three lines.
The order is not cosmetic - it moves from what is measured toward what is
inferred, so a reader who stops early has read the most reliable part.

Two properties are enforced rather than hoped for:

  * MEASURED EDGE always appears immediately after ENTRY OPPORTUNITY, so a
    favourable-looking configuration can never be read without the verdict on
    whether such configurations have been shown to work;
  * a section with no data prints UNAVAILABLE with the reason, never a blank
    or a zero. A silent gap reads as "nothing notable"; an explicit gap reads
    as "we do not know", which is the truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger

log = get_logger("engines.daily_report")


@dataclass(slots=True)
class Section:
    title: str
    lines: list[str] = field(default_factory=list)
    available: bool = True
    reason: str = ""

    def render(self) -> str:
        header = self.title
        if not self.available:
            return f"{header}\n  UNAVAILABLE — {self.reason}"
        body = "\n".join(f"  {line}" for line in self.lines) or "  —"
        return f"{header}\n{body}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title, "lines": self.lines,
            "available": self.available, "reason": self.reason,
        }


class DailyReportEngine:
    """Assemble the per-asset daily read from every engine that has one."""

    def build(self, asset: Asset, as_of: datetime | None = None) -> dict[str, Any]:
        sections: list[Section] = []

        regime = self._regime(asset, sections)
        mtf = self._structure(asset, sections, as_of)
        location = self._location(asset, sections, as_of)
        opportunity = self._opportunity(asset, sections, as_of)
        edge = self._edge(asset, sections)
        self._crowding(asset, sections, as_of)
        self._volatility(asset, sections, as_of)
        self._liquidity(sections)
        self._cross_asset(asset, sections)
        self._etf(asset, sections)
        self._macro(sections)
        self._network(asset, sections)
        self._catalysts(sections)
        self._analogs(asset, sections)
        uncertainty = self._uncertainty(asset, sections, edge)
        self._what_would_change(asset, sections, location, mtf)

        self._flag_contradictions(sections, regime, mtf)
        conclusion = self._conclude(asset, regime, mtf, opportunity, edge, uncertainty)

        return {
            "asset": asset.value,
            "generated_at": (as_of or datetime.now(UTC)).isoformat(),
            "sections": [s.to_dict() for s in sections],
            "conclusion": conclusion,
            "text": self.render(asset, sections, conclusion),
        }

    def render(self, asset: Asset, sections: list[Section], conclusion: list[str]) -> str:
        parts = [f"═══ {asset.value} ═══", ""]
        for index, section in enumerate(sections, start=1):
            parts.append(f"{index}. {section.render()}")
            parts.append("")
        parts.append("CONCLUSION")
        parts.extend(f"  {line}" for line in conclusion)
        return "\n".join(parts)

    # --- sections -------------------------------------------------------

    def _regime(self, asset: Asset, sections: list[Section]) -> Any:
        section = Section("MARKET REGIME")
        try:
            from ..api.routes_lot4 import _reconstructed_regime

            regime = _reconstructed_regime(asset)
            label = regime.regime.value
            section.lines = [
                f"{label.replace('_', ' ')}",
                f"held {regime.confidence}% of the last 20 days",
                "reconstructed from price structure; the multi-domain engine "
                "needs a full pipeline run",
            ]
            sections.append(section)
            return regime
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
            sections.append(section)
            return None

    def _structure(self, asset: Asset, sections: list[Section], as_of) -> Any:
        section = Section("STRUCTURE (multi-timeframe)")
        try:
            from .multi_timeframe import MultiTimeframeEngine

            mtf = MultiTimeframeEngine().assess(asset, as_of)
            for reading in mtf.readings:
                if reading.available:
                    section.lines.append(reading.describe())
            section.lines.append(f"alignment: {mtf.alignment.value.replace('_', ' ')}")
            section.lines.append(
                "the regime above is reconstructed from DAILY price structure; "
                "the weekly line here comes from confirmed weekly swings, so the "
                "two can legitimately differ"
            )
            for conflict in mtf.conflicts:
                section.lines.append(f"conflict: {conflict}")
            missing = [r.timeframe for r in mtf.readings if not r.available]
            if missing:
                section.lines.append(f"not readable: {', '.join(missing)}")
            sections.append(section)
            return mtf
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
            sections.append(section)
            return None

    def _location(self, asset: Asset, sections: list[Section], as_of) -> Any:
        section = Section("LOCATION")
        try:
            from ..structure.location import StructuralLocationEngine

            location = StructuralLocationEngine().assess(asset, Timeframe.H4, as_of)
            detected = location.detected_range
            if detected and detected.valid and detected.top_zone and detected.bottom_zone:
                section.lines = [
                    f"4h {location.state.value.replace('_', ' ')}",
                    f"bottom zone {detected.bottom_zone.low:.2f}–{detected.bottom_zone.high:.2f} "
                    f"(quality {detected.bottom_zone.quality.score:.0f}/100, "
                    f"{detected.bottom_zone.quality.touches} touches)",
                    f"top zone {detected.top_zone.low:.2f}–{detected.top_zone.high:.2f} "
                    f"(quality {detected.top_zone.quality.score:.0f}/100, "
                    f"{detected.top_zone.quality.touches} touches)",
                    f"position {location.relative_position} · width "
                    f"{detected.width_atr} ATR · held {detected.duration_bars} bars",
                ]
            else:
                section.lines = [
                    f"4h {location.state.value.replace('_', ' ')}",
                    detected.reason if detected else "no validated range",
                ]
            sections.append(section)
            return location
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
            sections.append(section)
            return None

    def _opportunity(self, asset: Asset, sections: list[Section], as_of) -> Any:
        section = Section("ENTRY OPPORTUNITY")
        try:
            from .entry_opportunity import EntryOpportunityEngine

            opportunity = EntryOpportunityEngine().assess(asset, Timeframe.H4, as_of)
            section.lines = [f"{opportunity.state.value} ({opportunity.score})"]
            section.lines.extend(f"· {reason}" for reason in opportunity.why_now)
            if opportunity.missing:
                section.lines.append(f"not included: {'; '.join(opportunity.missing)}")
            sections.append(section)
            return opportunity
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
            sections.append(section)
            return None

    def _edge(self, asset: Asset, sections: list[Section]) -> Any:
        # Deliberately immediately after ENTRY OPPORTUNITY.
        section = Section("MEASURED EDGE")
        try:
            from .edge import EdgeEngine

            edge = EdgeEngine().assess(asset)
            section.lines = [
                edge.state.value,
                f"{edge.admitted_count} relationship(s) admitted, "
                f"{edge.rejected_count} rejected",
                "a favourable configuration with no measured edge is the normal "
                "case, not a contradiction",
            ]
            sections.append(section)
            return edge
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
            sections.append(section)
            return None

    def _crowding(self, asset: Asset, sections: list[Section], as_of) -> None:
        section = Section("CROWDING")
        try:
            from .leverage import LeverageCrowdingEngine

            engine = LeverageCrowdingEngine()
            crowding = engine.crowding(asset, as_of)
            funding = engine.funding_context(asset, as_of)
            state = engine.leverage_state(asset, as_of)
            section.lines = [
                f"{crowding.level.value}"
                + (f" ({crowding.score}/100)" if crowding.score is not None else ""),
                f"direction {crowding.direction} — open interest counts contracts, "
                "not sides",
                f"funding {funding.band.value}"
                + (f" at p{funding.percentile}" if funding.percentile else ""),
                f"leverage state {state.state.value.replace('_', ' ')}",
            ]
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
        sections.append(section)

    def _volatility(self, asset: Asset, sections: list[Section], as_of) -> None:
        section = Section("VOLATILITY")
        try:
            from .volatility import VolatilityRegimeEngine

            volatility = VolatilityRegimeEngine().assess(asset, as_of)
            section.lines = [
                f"{volatility.regime.replace('_', ' ')}, {volatility.direction.lower()}",
                f"ATR {volatility.atr_percent}% of price"
                + (f" (p{volatility.atr_percentile})" if volatility.atr_percentile else ""),
                f"annualised realised volatility {volatility.realised_vol_annualised}%",
            ]
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
        sections.append(section)

    def _liquidity(self, sections: list[Section]) -> None:
        section = Section("LIQUIDITY")
        try:
            from .cross_asset import LiquidityRegimeEngine

            liquidity = LiquidityRegimeEngine().assess()
            section.lines = [liquidity.regime.value]
            for name, value in liquidity.components.items():
                section.lines.append(f"{name}: {value['change_3m_pct']:+.2f}% ({value['direction']})")
            if liquidity.missing:
                section.lines.append(f"not included: {', '.join(liquidity.missing)}")
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
        sections.append(section)

    def _cross_asset(self, asset: Asset, sections: list[Section]) -> None:
        section = Section("CROSS-ASSET")
        try:
            from .cross_asset import CrossAssetAnalyzer, CryptoBreadthEngine

            cross = CrossAssetAnalyzer().assess(asset)
            measured = [c for c in cross.correlations if c.correlation is not None]
            for reading in sorted(measured, key=lambda c: -abs(c.correlation))[:4]:
                section.lines.append(
                    f"{reading.label}: correlation {reading.correlation:+.2f}, "
                    f"beta {reading.beta:+.2f}"
                )
            breadth = CryptoBreadthEngine().assess()
            section.lines.append(
                f"breadth {breadth.state} ({breadth.score}/100) — three assets only"
            )
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
        sections.append(section)

    def _etf(self, asset: Asset, sections: list[Section]) -> None:
        section = Section("ETF")
        if asset is Asset.SOL:
            section.available = False
            section.reason = "no spot ETF tracked for SOL"
            sections.append(section)
            return
        try:
            from ..db import repo

            observation = repo.latest_observation(asset, "etf.flow")
            if observation is None:
                section.available = False
                section.reason = "no ETF flow stored"
            else:
                section.lines = [
                    f"latest net flow {observation.value:+.1f}M USD",
                    f"as of {str(observation.timestamp)[:10]}",
                    "ETF flows correlate with same-day price and showed no measured "
                    "forward information (LOT 3)",
                ]
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
        sections.append(section)

    def _macro(self, sections: list[Section]) -> None:
        section = Section("MACRO")
        try:
            from ..history import store

            lines = []
            for metric, label in (
                ("macro.dxy", "US dollar"), ("macro.vix", "VIX"),
                ("macro.us10y_yahoo", "10Y yield"), ("macro.nasdaq", "Nasdaq"),
            ):
                series = store.load_macro(metric)
                if len(series) >= 21:
                    change = (series.iloc[-1] / series.iloc[-21] - 1) * 100
                    lines.append(f"{label}: {change:+.2f}% over 20 sessions")
            section.lines = lines or ["no macro series long enough"]
            section.available = bool(lines)
            if not lines:
                section.reason = "macro series too short"
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
        sections.append(section)

    def _network(self, asset: Asset, sections: list[Section]) -> None:
        section = Section("NETWORK FUNDAMENTALS")
        section.available = False
        section.reason = (
            "on-chain history not ingested; blockchain.info offers ~5 years for BTC "
            "and is planned, ETH and SOL need separate sources"
        )
        sections.append(section)

    def _catalysts(self, sections: list[Section]) -> None:
        section = Section("TOP CATALYSTS")
        try:
            from ..db import repo

            events = repo.upcoming_events(days=14, limit=20)
            if events:
                section.lines = [
                    f"{str(e['scheduled_at'])[:10]} · {e['name']} "
                    f"(in {e['hours_until']:.0f}h, {e['importance']})"
                    for e in events[:5]
                ]
            else:
                section.lines = ["no scheduled event in the next 14 days"]
        except Exception as exc:
            section.available = False
            section.reason = f"macro calendar unavailable: {exc}"[:120]
        sections.append(section)

    def _analogs(self, asset: Asset, sections: list[Section]) -> None:
        section = Section("HISTORICAL ANALOGS")
        try:
            from ..history import store
            from .historical import HistoricalSimilarityEngine

            df = store.load_candles(asset, Timeframe.D1)
            analysis = HistoricalSimilarityEngine().analyze(asset, df, Timeframe.D1)
            if not analysis.available:
                section.available = False
                section.reason = analysis.unavailable_reason or "unavailable"
            elif analysis.matches:
                section.lines = [
                    f"{analysis.sample_size} comparable configurations (raw count)",
                ]
                for horizon, value in analysis.avg_forward_returns.items():
                    if value is not None:
                        hit = analysis.hit_rate.get(horizon)
                        section.lines.append(
                            f"{horizon}: mean {value:+.2f}%"
                            + (f", positive {hit:.0f}% of the time" if hit else "")
                        )
                section.lines.append(
                    "raw count only — overlapping windows mean the effective "
                    "sample is far smaller, and these analogues are descriptive"
                )
            else:
                section.available = False
                section.reason = "no comparable configuration found"
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
        sections.append(section)

    def _uncertainty(self, asset: Asset, sections: list[Section], edge) -> Any:
        section = Section("UNCERTAINTY")
        try:
            from .edge import UncertaintyEngine
            from .leverage import LeverageCrowdingEngine

            crowding = LeverageCrowdingEngine().crowding(asset)
            uncertainty = UncertaintyEngine().assess(asset, edge, crowding=crowding)
            section.lines = [f"{uncertainty.level} ({uncertainty.score}/100)"]
            section.lines.extend(
                f"+{d['contribution']} {d['driver']}" for d in uncertainty.drivers[:3]
            )
            sections.append(section)
            return uncertainty
        except Exception as exc:
            section.available = False
            section.reason = str(exc)[:120]
            sections.append(section)
            return None

    def _what_would_change(self, asset: Asset, sections: list[Section], location, mtf) -> None:
        section = Section("WHAT WOULD CHANGE THE VIEW?")
        improve: list[str] = []
        deteriorate: list[str] = []

        # Only levels the range engine actually validated are quoted. Inventing
        # a round number here would be exactly the fabrication this project
        # exists to avoid.
        detected = getattr(location, "detected_range", None)
        if detected and detected.valid and detected.top_zone and detected.bottom_zone:
            improve.append(
                f"a 4h close above {detected.top_zone.high:.2f} would break the "
                "range top"
            )
            deteriorate.append(
                f"a 4h close below {detected.bottom_zone.low:.2f} would break the "
                "range bottom"
            )
        else:
            improve.append("no validated range, so no objective level can be quoted")

        if mtf is not None and getattr(mtf, "conflicts", None):
            improve.append("the lower timeframes resolving in the direction of the higher")
            deteriorate.append("the higher timeframe turning to match the lower ones")

        deteriorate.append("volatility expanding while crowding rises")
        section.lines = (
            ["Would improve:"] + [f"· {x}" for x in improve]
            + ["Would deteriorate:"] + [f"· {x}" for x in deteriorate]
        )
        sections.append(section)

    def _flag_contradictions(self, sections: list[Section], regime, mtf) -> None:
        """Say when two sections of this report disagree.

        The regime label and the weekly structure are produced by different
        methods over different bar sizes, so they can point opposite ways. That
        is legitimate, but printing both without comment leaves the reader to
        notice the contradiction on their own - or worse, to miss it.
        """
        if regime is None or mtf is None:
            return
        weekly = next(
            (r for r in mtf.readings if r.timeframe == "1w" and r.available), None
        )
        if weekly is None or weekly.direction is None:
            return

        label = regime.regime.value
        regime_direction = 1 if "BULLISH" in label else -1 if "BEARISH" in label else 0
        if regime_direction == 0 or weekly.direction == 0:
            return
        if regime_direction == weekly.direction:
            return

        section = Section("⚠ CONTRADICTION WITHIN THIS REPORT")
        section.lines = [
            f"the daily regime reads {label.replace('_', ' ')} while the weekly "
            f"structure reads {weekly.structure.replace('_', ' ')}",
            "both are computed correctly: the regime is an EMA/ADX summary of "
            "daily bars, the weekly structure is a sequence of confirmed weekly "
            "swings, and they respond at different speeds",
            "treat the direction as genuinely unsettled rather than picking the "
            "one that suits",
        ]
        # Insert right after STRUCTURE so the reader meets it immediately.
        sections.insert(2, section)

    def _conclude(self, asset, regime, mtf, opportunity, edge, uncertainty) -> list[str]:
        direction = (
            regime.regime.value.replace("_", " ").lower() if regime else "undetermined"
        )
        alignment = mtf.alignment.value.replace("_", " ").lower() if mtf else "unknown"
        state = opportunity.state.value if opportunity else "INSUFFICIENT_DATA"
        edge_state = edge.state.value if edge else "UNKNOWN"
        level = uncertainty.level if uncertainty else "UNKNOWN"

        return [
            f"{asset.value} is {direction}; timeframes are in {alignment}.",
            f"Configuration reads {state}, and the measured edge is {edge_state}.",
            (
                f"Uncertainty {level}. "
                + (
                    "Nothing here has been shown to predict returns, so this is a "
                    "description of conditions, not a reason to act."
                    if edge_state != "POSITIVE_EDGE"
                    else "An edge was measured; see the research pages for its size "
                         "and stability."
                )
            ),
        ]


def build_all(assets: list[Asset] | None = None) -> dict[str, Any]:
    engine = DailyReportEngine()
    assets = assets or Asset.tradables()
    reports = {a.value: engine.build(a) for a in assets}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "assets": reports,
        "text": "\n\n".join(r["text"] for r in reports.values()),
    }
