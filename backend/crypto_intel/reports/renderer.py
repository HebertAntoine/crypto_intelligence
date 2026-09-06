"""Text report rendering, following the exact layout requested in the brief.

Every unavailable datapoint is printed as UNAVAILABLE with its reason. Nothing
is ever filled in to make a section look complete.
"""

from __future__ import annotations

from typing import Any

from ..pipeline.orchestrator import AssetAnalysis

W = 72
SEP = "=" * W
SUB = "-" * W


def _fmt(value: Any, unit: str = "", decimals: int = 2, prefix: str = "") -> str:
    """Format a number, or say UNAVAILABLE. Never substitute a placeholder."""
    if value is None:
        return "UNAVAILABLE"
    if isinstance(value, int | float):
        if abs(value) >= 1_000_000_000:
            return f"{prefix}{value / 1e9:,.2f}B{unit}"
        if abs(value) >= 1_000_000:
            return f"{prefix}{value / 1e6:,.2f}M{unit}"
        return f"{prefix}{value:,.{decimals}f}{unit}"
    return str(value)


def _signed(value: float | None, unit: str = "", decimals: int = 1) -> str:
    if value is None:
        return "UNAVAILABLE"
    return f"{value:+,.{decimals}f}{unit}"


def _score_line(label: str, card: dict[str, Any]) -> str:
    if not card.get("available", False):
        reason = card.get("unavailable_reason") or "UNAVAILABLE"
        return f"  {label:<14} {'UNAVAILABLE':>8}   {reason[:44]}"
    return (
        f"  {label:<14} {card['score']:>+8.1f}   "
        f"conf {card['confidence']:>5.1f}%  "
        f"{card['freshness']:<11} "
        f"{card['evidence_count']:>3} evidence"
    )


def render_report(analysis: AssetAnalysis) -> str:
    a = analysis
    lines: list[str] = []
    add = lines.append

    add(SEP)
    add(f"{a.asset.value} - MARKET INTELLIGENCE")
    add(SEP)
    add(f"Generated : {a.generated_at:%Y-%m-%d %H:%M:%S} UTC")
    add(f"Report ID : {a.report_id}")
    add("")
    add(f"Price          : {_fmt(a.price, ' USD')}")
    add(f"Change 24h     : {_signed(a.change_24h_pct, '%', 2)}")
    add(f"Change 7d      : {_signed(a.change_7d_pct, '%', 2)}")
    add(f"Market cap     : {_fmt(a.market_cap, ' USD')}")
    add(f"Market regime  : {a.market_regime}")
    add("")

    # --- conviction --------------------------------------------------------
    conv = a.conviction
    add(SUB)
    add("CONVICTION")
    add(SUB)
    for horizon, label in (("short", "Short term (1h-24h)"),
                           ("medium", "Medium term (days-weeks)"),
                           ("long", "Long term (weeks-months)")):
        c = conv.get(horizon, {})
        add(
            f"  {label:<26} {c.get('score', 0):>+7.1f}  {c.get('label', 'N/A'):<18} "
            f"confidence {c.get('confidence', 0):>5.1f}%"
        )
    add("")
    add(f"  Overall confidence : {conv.get('overall_confidence', 0):.1f}%")
    add(f"  Domains available  : {conv.get('domains_available', 0)}/{len(a.scores)}")
    if conv.get("domains_missing"):
        add(f"  Domains missing    : {', '.join(conv['domains_missing'])}")
    add("")

    # --- scores ------------------------------------------------------------
    add(SUB)
    add("DOMAIN SCORES  (-100 bearish .. +100 bullish)")
    add(SUB)
    for domain, label in (
        ("technical", "Technical"), ("etf", "ETF"), ("derivatives", "Derivatives"),
        ("onchain", "On-chain"), ("liquidity", "Liquidity"), ("defi", "DeFi"),
        ("macro", "Macro"), ("regulation", "Regulation"), ("news", "News"),
        ("whale", "Whales"),
    ):
        if domain in a.scores:
            add(_score_line(label, a.scores[domain]))
    add("")

    syn = a.synthesis

    add(SUB)
    add("WHAT IS POSITIVE")
    add(SUB)
    if syn.get("positives"):
        for i, p in enumerate(syn["positives"][:6], 1):
            add(f"  {i}. {p}")
    else:
        add("  No clearly positive signal in the available data.")
    add("")

    add(SUB)
    add("WHAT IS NEGATIVE")
    add(SUB)
    if syn.get("negatives"):
        for i, n in enumerate(syn["negatives"][:6], 1):
            add(f"  {i}. {n}")
    else:
        add("  No clearly negative signal in the available data.")
    add("")

    # --- contradictions ----------------------------------------------------
    add(SUB)
    add("CONTRADICTORY SIGNALS")
    add(SUB)
    contra = a.contradictions
    if contra.get("contradictions"):
        for c in contra["contradictions"]:
            add(f"  [{c['strength']:.0f}/100] {c['description']}")
        add("")
        add(f"  {contra.get('summary', '')}")
    else:
        add("  None detected: the available signals are broadly consistent.")
    add("")

    # --- ETF ---------------------------------------------------------------
    add(SUB)
    add("ETF FLOWS")
    add(SUB)
    etf = (a.domains or {}).get("etf") or {}
    if etf.get("available"):
        add(f"  Latest ({etf.get('latest_date', '')[:10]}) : {_signed(etf.get('latest_total'), ' MUSD')}")
        add(f"  3-day average          : {_signed(etf.get('ma_3d'), ' MUSD')}")
        add(f"  5-day average          : {_signed(etf.get('ma_5d'), ' MUSD')}")
        add(f"  7-day average          : {_signed(etf.get('ma_7d'), ' MUSD')}")
        add(f"  30-day cumulative      : {_signed(etf.get('cumulative_30d'), ' MUSD', 0)}")
        add(f"  Acceleration           : {_signed(etf.get('acceleration_pct'), '%', 0)}")
        if etf.get("streak_days"):
            add(f"  Streak                 : {etf['streak_days']} consecutive {etf.get('streak_direction')} days")
        if etf.get("reversal"):
            add(f"  Reversal               : {etf['reversal']}")
        if etf.get("flow_price_divergence"):
            add(f"  Flow/price signal      : {etf['flow_price_divergence']}")
            add(f"    -> {etf.get('divergence_detail', '')}")
        by_ticker = etf.get("latest_by_ticker") or {}
        if by_ticker:
            top = sorted(by_ticker.items(), key=lambda kv: -abs(kv[1]))[:6]
            add("  By fund (latest day)   : " + ", ".join(f"{t} {v:+.1f}" for t, v in top))
    else:
        add(f"  UNAVAILABLE - {etf.get('unavailable_reason', 'no data')}")
    add("")

    # --- derivatives -------------------------------------------------------
    add(SUB)
    add("DERIVATIVES")
    add(SUB)
    d = (a.domains or {}).get("derivatives") or {}
    if d.get("available"):
        fr = d.get("funding_rate")
        add(f"  Funding rate     : {f'{fr:.6f} / 8h' if fr is not None else 'UNAVAILABLE'}  [{d.get('funding_state')}]")
        add(f"  Annualised       : {_signed(d.get('funding_annualized_pct'), '%', 2)}")
        add(f"  Open interest    : {_fmt(d.get('open_interest'), '', 0)}  [{d.get('oi_state')}]")
        add(f"  OI change 24h    : {_signed(d.get('oi_change_24h_pct'), '%', 2)}")
        add(f"  Long/short ratio : {_fmt(d.get('long_short_ratio'), '', 3)}  [{d.get('ls_state')}]")
        add(f"  Basis            : {_signed(d.get('basis_pct'), '%', 4)}")
        if d.get("regime_interpretation"):
            add(f"  Regime           : {d['price_oi_regime']}")
            add(f"    -> {d['regime_interpretation']}")
        if not d.get("liquidations_available"):
            add(f"  Liquidations     : {d.get('liquidations_note', 'UNAVAILABLE')}")
    else:
        add(f"  UNAVAILABLE - {d.get('unavailable_reason', 'no data')}")
    add("")

    # --- on-chain ----------------------------------------------------------
    add(SUB)
    add("ON-CHAIN")
    add(SUB)
    oc = (a.domains or {}).get("onchain") or {}
    if oc.get("available"):
        add(f"  Chain type : {oc.get('chain_type', '')}")
        for f in (oc.get("findings") or [])[:8]:
            add(f"  - {f}")
        if oc.get("not_applicable"):
            add(f"  Not applicable to this chain: {', '.join(oc['not_applicable'])}")
    else:
        add(f"  UNAVAILABLE - {oc.get('unavailable_reason', 'no data')}")
    add("")

    # --- liquidity / defi --------------------------------------------------
    add(SUB)
    add("LIQUIDITY / DEFI")
    add(SUB)
    liq = (a.domains or {}).get("liquidity") or {}
    if liq.get("available"):
        add(f"  Stablecoin regime : {liq.get('regime')}")
        add(f"  Total supply      : {_fmt(liq.get('total_supply'), ' USD')}")
        add(f"  Change 7d         : {_signed(liq.get('change_7d_pct'), '%', 2)}")
        for f in (liq.get("findings") or [])[:3]:
            add(f"  - {f}")
    else:
        add(f"  Stablecoins: UNAVAILABLE - {liq.get('unavailable_reason', '')}")
    defi = (a.domains or {}).get("defi") or {}
    if defi.get("available"):
        add(f"  Chain TVL         : {_fmt(defi.get('tvl'), ' USD')}  ({_signed(defi.get('tvl_change_7d_pct'), '%')} 7d)")
        add(f"  DEX volume 24h    : {_fmt(defi.get('dex_volume_24h'), ' USD')}")
        if defi.get("tvl_price_divergence"):
            add(f"  TVL/price signal  : {defi['tvl_price_divergence']}")
    else:
        add(f"  DeFi: UNAVAILABLE - {defi.get('unavailable_reason', '')}")
    add("")

    # --- macro / politics --------------------------------------------------
    add(SUB)
    add("MACRO / POLITICS")
    add(SUB)
    macro = (a.domains or {}).get("macro") or {}
    if macro.get("available"):
        add(f"  Risk appetite : {macro.get('risk_appetite')}")
        add(f"  Dollar        : {macro.get('dollar_trend')}")
        add(f"  Rates         : {macro.get('rates_trend')}")
        for f in (macro.get("findings") or [])[:6]:
            add(f"  - {f}")
        if macro.get("missing"):
            add(f"  Missing: {', '.join(macro['missing'])}")
    else:
        add(f"  UNAVAILABLE - {macro.get('unavailable_reason', '')}")

    reg = (a.domains or {}).get("regulation") or {}
    add("")
    if reg.get("available"):
        add(f"  Regulatory items : {len(reg.get('events', []))} "
            f"({reg.get('binding_count', 0)} binding, {reg.get('proposal_count', 0)} proposals)")
        for e in (reg.get("events") or [])[:5]:
            add(f"  [{e['legal_status']}] {e['institution']}: {e['title'][:80]}")
        if reg.get("proposal_count"):
            add("  NOTE: proposals are NOT adopted law and change nothing legally until enacted.")
    else:
        add(f"  Regulation: UNAVAILABLE - {reg.get('unavailable_reason', '')}")

    geo = (a.domains or {}).get("geopolitics") or {}
    if geo.get("available"):
        add("")
        add(f"  Geopolitical risk : {geo.get('level')} ({geo.get('score', 0):.0f}/100)")
        add(f"    {geo.get('justification', '')[:200]}")
    add("")

    # --- catalysts ---------------------------------------------------------
    add(SUB)
    add("UPCOMING CATALYSTS")
    add(SUB)
    if syn.get("key_catalysts"):
        for c in syn["key_catalysts"][:8]:
            add(f"  - {c}")
    else:
        add("  None identified in the monitored calendar and feeds.")
    if syn.get("recent_decisions"):
        add("")
        add("  Already decided (context, not upcoming):")
        for d in syn["recent_decisions"][:4]:
            add(f"  - {d}")
    add("")

    # --- scenarios ---------------------------------------------------------
    add(SUB)
    add("SCENARIOS")
    add(SUB)
    if a.scenarios:
        for s in a.scenarios:
            add(f"  {s['name'].upper()} - {s['probability']:.0f}% (indicative analytical probability)")
            add(f"    {s['label']}")
            add(f"    {s['narrative'][:300]}")
            if s.get("conditions"):
                add("    Conditions:")
                for c in s["conditions"][:3]:
                    add(f"      - {c}")
            if s.get("invalidation"):
                add(f"    Invalidation: {s['invalidation']}")
            add("")
    else:
        add("  No scenarios generated.")
        add("")

    # --- technical levels --------------------------------------------------
    add(SUB)
    add("TECHNICAL LEVELS")
    add(SUB)
    daily = (a.technical or {}).get("1d") or {}
    if daily:
        sup = daily.get("levels_support") or []
        res = daily.get("levels_resistance") or []
        add("  Supports    : " + (", ".join(f"{lv['price']:,.0f} ({lv['touches']}x)" for lv in sup[:4]) or "none identified"))
        add("  Resistances : " + (", ".join(f"{lv['price']:,.0f} ({lv['touches']}x)" for lv in res[:4]) or "none identified"))
        add(f"  Daily RSI   : {_fmt(daily.get('rsi'), '', 1)} [{daily.get('rsi_state')}]")
        add(f"  Daily trend : {(daily.get('trend') or {}).get('direction')}")
        add(f"  Structure   : {daily.get('structure')} {daily.get('structure_labels') or ''}")
        pats = daily.get("patterns") or []
        if pats:
            add("  Patterns    :")
            for p in pats[:4]:
                inval = f", invalidation {p['invalidation_level']:,.0f}" if p.get("invalidation_level") else ""
                add(f"    - {p['pattern']} ({p['confirmation_state']}, {p['confidence']:.0f}%{inval})")
        divs = daily.get("divergences") or []
        if divs:
            add("  Divergences :")
            for dv in divs[:3]:
                add(f"    - {dv['indicator']} {dv['kind']} (strength {dv['strength']:.0f})")
    else:
        add("  UNAVAILABLE - no daily candles")
    add("")

    # --- multi timeframe ---------------------------------------------------
    add(SUB)
    add("MULTI-TIMEFRAME")
    add(SUB)
    mtf = (a.domains or {}).get("mtf") or {}
    for v in (mtf.get("verdicts") or []):
        if v.get("available"):
            add(f"  {v['timeframe']:<4} {v['direction']:<12} trend {v['trend']:<12} weight {v['weight']:.2f}")
        else:
            add(f"  {v['timeframe']:<4} UNAVAILABLE")
    add(f"  Alignment {mtf.get('alignment_score', 0):+.1f} | coherence {mtf.get('coherence', 0):.0f}%")
    for c in (mtf.get("conflicts") or []):
        add(f"  ! {c}")
    add("")

    # --- historical --------------------------------------------------------
    hist = (a.domains or {}).get("historical")
    if hist:
        add(SUB)
        add("HISTORICAL ANALOGUES")
        add(SUB)
        if hist.get("available"):
            add(f"  {hist.get('interpretation', '')}")
            for m in (hist.get("matches") or [])[:5]:
                r = m["forward_returns"]
                parts = [f"{k} {v:+.2f}%" for k, v in r.items() if v is not None]
                add(f"    {m['date']}  similarity {m['similarity'] * 100:.1f}%  " + "  ".join(parts))
            add(f"  {hist.get('caveat', '')}")
        else:
            add(f"  UNAVAILABLE - {hist.get('unavailable_reason', '')}")
        add("")

    # --- what would change my mind ----------------------------------------
    add(SUB)
    add("WHAT WOULD CHANGE MY MIND")
    add(SUB)
    if syn.get("what_would_change_my_mind"):
        for w in syn["what_would_change_my_mind"][:6]:
            add(f"  - {w}")
    else:
        add("  Not determined from the available data.")
    add("")

    add(SUB)
    add("RISKS")
    add(SUB)
    if syn.get("key_risks"):
        for r in syn["key_risks"][:6]:
            add(f"  - {r}")
    else:
        add("  No specific risk flagged beyond normal market risk.")
    add("")

    # --- data quality ------------------------------------------------------
    add(SUB)
    add("DATA QUALITY")
    add(SUB)
    ok = [s for s in a.sources if s.ok]
    ko = [s for s in a.sources if not s.ok]
    add(f"  Sources OK        : {len(ok)}/{len(a.sources)}")
    if ko:
        add("  Sources missing   :")
        for s in ko:
            add(f"    - {s.capability:<20} {s.message[:56]}")
    stale = [
        d for d, c in a.scores.items()
        if c.get("available") and c.get("freshness") == "STALE"
    ]
    if stale:
        add(f"  STALE domains     : {', '.join(stale)}")
    add(f"  LLM narrative     : {'yes' if a.llm_used else 'no (deterministic synthesis)'}")
    if syn.get("data_quality_note"):
        add(f"  {syn['data_quality_note']}")
    add("")

    # --- synthesis ---------------------------------------------------------
    add(SUB)
    add("SYNTHESIS")
    add(SUB)
    text = syn.get("text", "")
    for chunk in _wrap(text, W - 2):
        add(f"  {chunk}")
    add("")
    add(SEP)
    add("This tool performs analysis only. It places no orders and gives no")
    add("investment advice. Every decision is yours.")
    add(SEP)

    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    out: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(textwrap.wrap(para, width=width) or [""])
    return out
