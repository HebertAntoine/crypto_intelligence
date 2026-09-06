"""Daily Intelligence Report - the whole market in two minutes.

The structure is fixed on purpose: global context first, then one compact
block per asset, then the three things worth watching and what would change
the view. Anything longer does not get read daily.

The nuance the brief asks for - "favourable trend but poor timing" - comes for
free here because regime and entry timing are computed independently and
printed side by side.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

WIDTH = 76
SEP = "=" * WIDTH
SUB = "-" * WIDTH


def _fmt(value: Any, decimals: int = 2, unit: str = "", signed: bool = False) -> str:
    if value is None:
        return "UNAVAILABLE"
    if isinstance(value, int | float):
        if abs(value) >= 1e9:
            return f"{value / 1e9:,.2f}B{unit}"
        if abs(value) >= 1e6:
            return f"{value / 1e6:,.2f}M{unit}"
        prefix = "+" if signed and value >= 0 else ""
        return f"{prefix}{value:,.{decimals}f}{unit}"
    return str(value)


def _trend_timing_line(regime: dict, timing: dict) -> str:
    """The headline nuance: direction and moment are separate answers."""
    regime_label = regime.get("regime", "UNDETERMINED")
    timing_label = timing.get("timing", "UNDETERMINED")

    favourable_regime = regime_label in ("BULLISH", "STRONGLY_BULLISH")
    poor_timing = timing_label in ("WAIT", "UNFAVORABLE", "VERY_UNFAVORABLE")
    adverse_regime = regime_label in ("BEARISH", "STRONGLY_BEARISH")
    good_timing = timing_label in ("FAVORABLE", "VERY_FAVORABLE")

    if favourable_regime and poor_timing:
        return "Trend is favourable but the immediate entry is not."
    if adverse_regime and good_timing:
        return "Trend is adverse; short-term conditions look stretched to the downside."
    if favourable_regime and good_timing:
        return "Trend and timing agree on the constructive side."
    if adverse_regime and poor_timing:
        return "Trend and timing agree on the cautious side."
    return "No strong alignment between trend and timing."


def render_daily_report(
    analyses: list[Any],
    global_view: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    add = lines.append
    now = datetime.now(UTC)

    add(SEP)
    add("CRYPTO INTELLIGENCE - DAILY")
    add(SEP)
    add(f"{now:%Y-%m-%d %H:%M} UTC")
    add("")

    # --- GLOBAL -----------------------------------------------------------
    add(SUB)
    add("GLOBAL")
    add(SUB)
    gv = global_view or {}
    add(f"  Risk regime      : {gv.get('risk_regime', 'UNAVAILABLE')}")
    add(f"  Avg conviction   : {_fmt(gv.get('average_conviction'), 1, signed=True)}")

    macro = gv.get("macro") or {}
    if macro.get("available"):
        add(f"  Macro            : risk appetite {macro.get('risk_appetite')}, "
            f"dollar {macro.get('dollar_trend')}, rates {macro.get('rates_trend')}")
    else:
        add(f"  Macro            : UNAVAILABLE - {macro.get('unavailable_reason', 'no data')}")

    liquidity = gv.get("liquidity") or {}
    if liquidity.get("available"):
        add(f"  Liquidity        : {liquidity.get('regime')} "
            f"({_fmt(liquidity.get('change_7d_pct'), 2, '%', signed=True)} over 7d, "
            f"total {_fmt(liquidity.get('total_supply'), 1, ' USD')})")
    else:
        add("  Liquidity        : UNAVAILABLE")

    geo = gv.get("geopolitics") or {}
    if geo.get("available"):
        add(f"  Geopolitical     : {geo.get('level')} ({geo.get('score', 0):.0f}/100)")

    calendar = gv.get("calendar") or []
    if calendar:
        nxt = calendar[0]
        add(f"  Next major event : {nxt['name']} in {nxt['hours_until']:.0f}h "
            f"({nxt['importance']})")
    else:
        add("  Next major event : none scheduled in the calendar window")
    add("")

    # --- PER ASSET ---------------------------------------------------------
    for analysis in analyses:
        regime = analysis.regime or {}
        timing = analysis.entry_timing or {}
        conviction = analysis.conviction or {}
        domains = analysis.domains or {}
        daily_tech = (analysis.technical or {}).get("1d") or {}

        add(SUB)
        add(f"{analysis.asset.value}")
        add(SUB)
        add(f"  Price            : {_fmt(analysis.price, 2, ' USD')}   "
            f"24h {_fmt(analysis.change_24h_pct, 2, '%', signed=True)}   "
            f"7d {_fmt(analysis.change_7d_pct, 2, '%', signed=True)}")
        add(f"  Market regime    : {regime.get('regime', 'UNDETERMINED')} "
            f"({_fmt(regime.get('regime_score'), 0, signed=True)}, "
            f"conf {regime.get('confidence', 0):.0f}%)"
            + (f"  [{', '.join(regime.get('conditions', [])[:2])}]"
               if regime.get("conditions") else ""))
        add(f"  Entry timing     : {timing.get('timing', 'UNDETERMINED')} "
            f"({_fmt(timing.get('timing_score'), 0, signed=True)}, "
            f"conf {timing.get('confidence', 0):.0f}%)")
        add(f"  -> {_trend_timing_line(regime, timing)}")
        add("")

        short = conviction.get("short") or {}
        medium = conviction.get("medium") or {}
        long_ = conviction.get("long") or {}
        add(f"  Conviction       : short {_fmt(short.get('score'), 1, signed=True)} | "
            f"medium {_fmt(medium.get('score'), 1, signed=True)} | "
            f"long {_fmt(long_.get('score'), 1, signed=True)} "
            f"(confidence {conviction.get('overall_confidence', 0):.0f}%)")

        # ETF
        etf = domains.get("etf") or {}
        if etf.get("available"):
            add(f"  ETF              : latest {_fmt(etf.get('latest_total'), 1, 'M USD', signed=True)}, "
                f"5d avg {_fmt(etf.get('ma_5d'), 1, 'M', signed=True)}, "
                f"{etf.get('streak_days', 0)} day {etf.get('streak_direction') or 'streak'}"
                + (f", {etf['flow_price_divergence']}" if etf.get("flow_price_divergence") else ""))
        else:
            add(f"  ETF              : UNAVAILABLE - {etf.get('unavailable_reason', 'no data')[:52]}")

        # Technical
        if daily_tech:
            supports = daily_tech.get("levels_support") or []
            resistances = daily_tech.get("levels_resistance") or []
            add(f"  Technical        : RSI {_fmt(daily_tech.get('rsi'), 1)} "
                f"({daily_tech.get('rsi_state')}), trend "
                f"{(daily_tech.get('trend') or {}).get('direction')}, "
                f"structure {daily_tech.get('structure')}")
            add(f"  Levels           : support "
                f"{', '.join(_fmt(s['price'], 0) for s in supports[:2]) or 'none'} | "
                f"resistance "
                f"{', '.join(_fmt(r['price'], 0) for r in resistances[:2]) or 'none'}")

        # Derivatives
        deriv = domains.get("derivatives") or {}
        if deriv.get("available"):
            add(f"  Derivatives      : funding {deriv.get('funding_state')} "
                f"({_fmt(deriv.get('funding_annualized_pct'), 1, '% ann', signed=True)}), "
                f"OI {_fmt(deriv.get('oi_change_24h_pct'), 1, '% 24h', signed=True)}")
        else:
            add("  Derivatives      : UNAVAILABLE")

        # ETF: participation and predictive value are separate answers.
        etf_split = analysis.etf_split or {}
        if etf_split.get("available"):
            add(f"  ETF context      : {etf_split.get('context_label')} "
                f"({_fmt(etf_split.get('context_score'), 0, signed=True)})")
            if etf_split.get("predictive_available"):
                add(f"  ETF predictive   : "
                    f"{_fmt(etf_split.get('predictive_score'), 0, signed=True)} "
                    f"(confidence {etf_split.get('predictive_confidence', 0):.0f}%)")
            else:
                add("  ETF predictive   : no component with demonstrated forward value")

        # Analytical confidence and empirical frequency are different things.
        probability = analysis.probability or {}
        if probability:
            add(f"  Analytical conf  : {probability.get('analytical_confidence', 0):.0f}/100")
            if probability.get("empirical_available"):
                add(f"  Empirical evid.  : {probability['empirical_probability']:.0f}% of "
                    f"{probability['empirical_sample']} comparable past days ended higher "
                    f"at {probability['empirical_horizon']}")
            else:
                add(f"  Empirical evid.  : UNAVAILABLE - "
                    f"{probability.get('empirical_reason', 'no comparable sample')[:44]}")

        empirical = analysis.empirical or {}
        risk_reward = empirical.get("risk_reward") or {}
        if risk_reward.get("available"):
            add(f"  Reward/risk      : MFE median {risk_reward['mfe_median']:+.1f}%, "
                f"MAE median {risk_reward['mae_median']:+.1f}%, "
                f"ratio {risk_reward.get('reward_risk_ratio')} "
                f"(n={risk_reward['n']}, historical analogues)")

        # Data quality, stated rather than implied.
        conviction_block = analysis.conviction or {}
        missing = conviction_block.get("domains_missing") or []
        sources_ok = sum(1 for src in analysis.sources if src.ok)
        add(f"  Data quality     : {sources_ok}/{len(analysis.sources)} sources, "
            f"{conviction_block.get('domains_available', 0)} domains available"
            + (f", missing: {', '.join(missing[:3])}" if missing else ""))

        # Timing detail: what is blocking or helping
        if timing.get("negatives"):
            add("  Timing blockers  :")
            for n in timing["negatives"][:3]:
                add(f"     - {n[:66]}")
        if timing.get("positives"):
            add("  Timing support   :")
            for p in timing["positives"][:2]:
                add(f"     + {p[:66]}")

        if timing.get("invalidation_level"):
            add(f"  Invalidation     : {_fmt(timing['invalidation_level'], 2)} "
                f"- {timing.get('invalidation_reason', '')[:52]}")

        contradictions = (analysis.contradictions or {}).get("contradictions") or []
        if contradictions:
            add(f"  Main conflict    : {contradictions[0]['description'][:64]}")

        # DATA SAYS vs KNOWLEDGE BASE SAYS - only when they actually disagree.
        for confrontation in (analysis.confrontations or []):
            if confrontation.get("agreement") != "CONTRADICTS":
                continue
            add("")
            add("  DATA SAYS:")
            for chunk in _wrap(confrontation["data_says"], 64):
                add(f"     {chunk}")
            if confrontation.get("knowledge_says"):
                add("  KNOWLEDGE BASE SAYS:")
                for chunk in _wrap(confrontation["knowledge_says"], 64):
                    add(f"     {chunk}")
            add("  CONCLUSION:")
            for chunk in _wrap(confrontation["conclusion"], 64):
                add(f"     {chunk}")

        risks = timing.get("risks") or []
        if risks:
            add(f"  Main risk        : {risks[0][:64]}")
        add("")

    # --- TOP 3 THINGS TO WATCH --------------------------------------------
    add(SUB)
    add("TOP 3 THINGS TO WATCH")
    add(SUB)
    for i, item in enumerate(_top_watch(analyses, gv), start=1):
        add(f"  {i}. {item}")
    add("")

    # --- WHAT WOULD CHANGE THE VIEW ---------------------------------------
    add(SUB)
    add("WHAT WOULD CHANGE THE VIEW")
    add(SUB)
    for item in _what_would_change(analyses)[:4]:
        add(f"  - {item}")
    add("")

    # --- RESEARCH CAVEAT ---------------------------------------------------
    if research and research.get("summary", {}).get("useless_or_weak_signals"):
        add(SUB)
        add("MEASURED SIGNAL QUALITY (from `make research`)")
        add(SUB)
        for item in research["summary"]["useless_or_weak_signals"][:3]:
            add(f"  ! {item[:70]}")
        add("")

    add(SEP)
    add("Analysis only. No orders are placed and no advice is given.")
    add(SEP)
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width) or [""]


def _top_watch(analyses: list[Any], global_view: dict[str, Any]) -> list[str]:
    """Rank what actually deserves attention today.

    Priority order reflects how actionable each item is: a scheduled release
    with a known time beats a slow-moving flow trend, which beats a technical
    level that may never be reached.
    """
    items: list[tuple[int, str]] = []

    calendar = global_view.get("calendar") or []
    for event in calendar[:2]:
        hours = event.get("hours_until") or 999
        if hours <= 72:
            priority = 100 if hours <= 24 else 80
            items.append((
                priority,
                f"{event['name']} in {hours:.0f}h ({event['importance']}) - "
                "volatility around the release, direction unknowable in advance",
            ))

    for analysis in analyses:
        asset = analysis.asset.value
        etf = (analysis.domains or {}).get("etf") or {}
        timing = analysis.entry_timing or {}
        regime = analysis.regime or {}
        daily_tech = (analysis.technical or {}).get("1d") or {}

        if etf.get("available"):
            if etf.get("flow_price_divergence") == "DISTRIBUTION_INTO_STRENGTH":
                items.append((
                    90,
                    f"{asset} ETF flows are negative while price rises - "
                    "the move lacks institutional backing",
                ))
            elif etf.get("flow_price_divergence") == "ACCUMULATION_BEFORE_PRICE":
                items.append((
                    85,
                    f"{asset} ETFs are accumulating while price falls - "
                    "institutions are buying weakness",
                ))
            elif etf.get("acceleration_pct") is not None and etf["acceleration_pct"] < -40:
                items.append((
                    70,
                    f"{asset} ETF inflows are decelerating "
                    f"({etf['acceleration_pct']:+.0f}% vs the prior 3 days)",
                ))

        if regime.get("regime") in ("BULLISH", "STRONGLY_BULLISH") and timing.get("timing") in (
            "UNFAVORABLE", "VERY_UNFAVORABLE"
        ):
            items.append((
                75,
                f"{asset} trend is {regime['regime']} but entry timing is "
                f"{timing['timing']} - "
                + (timing["negatives"][0][:60] if timing.get("negatives") else "conditions stretched"),
            ))

        resistances = daily_tech.get("levels_resistance") or []
        if resistances and analysis.price:
            distance = (resistances[0]["price"] - analysis.price) / analysis.price * 100.0
            if 0 < distance < 3:
                items.append((
                    65,
                    f"{asset} is {distance:.1f}% below daily resistance at "
                    f"{resistances[0]['price']:,.0f} ({resistances[0]['touches']} touches)",
                ))

        deriv = (analysis.domains or {}).get("derivatives") or {}
        if deriv.get("funding_state") in ("EXTREME_POSITIVE", "EXTREME_NEGATIVE"):
            items.append((
                80,
                f"{asset} funding is {deriv['funding_state']} - crowded positioning "
                "raises squeeze risk",
            ))

    items.sort(key=lambda x: -x[0])
    seen: set[str] = set()
    result: list[str] = []
    for _, text in items:
        head = text[:28]
        if head in seen:
            continue
        seen.add(head)
        result.append(text)
        if len(result) == 3:
            break

    while len(result) < 3:
        result.append("No further high-priority item identified from the available data.")
    return result


def _what_would_change(analyses: list[Any]) -> list[str]:
    out: list[str] = []
    for analysis in analyses:
        asset = analysis.asset.value
        timing = analysis.entry_timing or {}
        synthesis = analysis.synthesis or {}

        if timing.get("invalidation_level"):
            out.append(
                f"{asset}: a daily close below {timing['invalidation_level']:,.2f} would "
                "invalidate the constructive technical read"
            )
        for item in (synthesis.get("what_would_change_my_mind") or [])[:1]:
            out.append(f"{asset}: {item}")
    return out
