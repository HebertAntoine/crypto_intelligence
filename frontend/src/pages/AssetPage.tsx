import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type AssetDetail } from "../lib/api";
import {
  ErrorBox, FreshnessBadge, LegalStatusPill, Loading, ScoreBar, Unavailable,
  Value, WhyButton, fmtNumber, fmtSigned, signClass,
} from "../components/common";
import PriceChart from "../components/PriceChart";
import EtfVsPricePanel from "./EtfVsPrice";
import { WhyVerdict } from "../components/WhyPanel";

const TABS = [
  "Overview", "Chart", "Timing", "Technical", "ETF", "ETF vs Price",
  "Derivatives", "On-chain", "Liquidity", "Macro", "News", "Whales",
  "Historical", "Report", "Sources",
] as const;
type Tab = (typeof TABS)[number];

export default function AssetPage() {
  const { symbol = "BTC" } = useParams();
  const [data, setData] = useState<AssetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [refreshing, setRefreshing] = useState(false);

  const load = (refresh = false) => {
    setError(null);
    if (refresh) setRefreshing(true);
    api
      .asset(symbol, refresh)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setRefreshing(false));
  };

  useEffect(() => {
    setData(null);
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what={`${symbol} analysis`} />;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <div className="row">
          <span className="asset-symbol">{data.asset}</span>
          <span className="asset-price">
            <Value v={data.price} decimals={data.asset === "SOL" ? 2 : 0} />
          </span>
          <span className={`mono ${signClass(data.change_24h_pct)}`}>
            {fmtSigned(data.change_24h_pct, 2, "%")} 24h
          </span>
          <span className={`regime-badge regime-${data.regime?.regime ?? "UNDETERMINED"}`}>
            {data.regime?.regime ?? "UNDETERMINED"}
          </span>
          <span className={`timing-badge timing-${data.entry_timing?.timing ?? "UNDETERMINED"}`}>
            {data.entry_timing?.timing ?? "UNDETERMINED"}
          </span>
        </div>
        <button className="refresh-btn" onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && <Overview data={data} />}
      {tab === "Chart" && <PriceChart symbol={data.asset} />}
      {tab === "Timing" && <RegimeAndTiming data={data} />}
      {tab === "ETF vs Price" && <EtfVsPricePanel symbol={data.asset} />}
      {tab === "Technical" && <Technical data={data} />}
      {tab === "ETF" && <ETF data={data} />}
      {tab === "Derivatives" && <Derivatives data={data} />}
      {tab === "On-chain" && <OnChain data={data} />}
      {tab === "Liquidity" && <Liquidity data={data} />}
      {tab === "Macro" && <Macro data={data} />}
      {tab === "News" && <News data={data} />}
      {tab === "Whales" && <Whales data={data} />}
      {tab === "Historical" && <Historical data={data} />}
      {tab === "Report" && <Report symbol={data.asset} />}
      {tab === "Sources" && <Sources data={data} />}
    </>
  );
}

/* ---------------------------------------------------------------- Overview */

function Overview({ data }: { data: AssetDetail }) {
  const c = data.conviction;
  const syn = data.synthesis;

  return (
    <>
      <div className="grid-2">
        <div className="panel">
          <div className="panel-title">Conviction by horizon</div>
          {(["short", "medium", "long"] as const).map((h) => {
            const conv = c[h];
            return (
              <div key={h} className="conviction-row">
                <span className="conviction-label">
                  {h === "short" ? "Short (1h–24h)" : h === "medium" ? "Medium (days–weeks)" : "Long (weeks–months)"}
                </span>
                <span className="row" style={{ gap: 10 }}>
                  <span className="tiny faint">{conv.label}</span>
                  <span className="tiny faint">{conv.confidence.toFixed(0)}%</span>
                  <span className={`conviction-value ${signClass(conv.score)}`}>
                    {fmtSigned(conv.score, 1)}
                  </span>
                </span>
              </div>
            );
          })}
          <div className="kv" style={{ marginTop: 10 }}>
            <span>Overall confidence</span>
            <span>{c.overall_confidence.toFixed(1)}%</span>
          </div>
          <div className="kv">
            <span>Domains available</span>
            <span>{c.domains_available}/10</span>
          </div>
          {c.domains_missing.length > 0 && (
            <div className="tiny unavailable" style={{ marginTop: 6 }}>
              Missing: {c.domains_missing.join(", ")}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">Domain scores</div>
          {Object.entries(data.scores).map(([domain, card]) => (
            <div key={domain} className="score-row">
              <span className="score-name">{domain}</span>
              <ScoreBar score={card.score} available={card.available} />
              <span className={`score-value ${card.available ? signClass(card.score) : "unavailable"}`}>
                {card.available ? fmtSigned(card.score, 0) : "N/A"}
              </span>
              <span className="score-conf">
                {card.available ? `conf ${card.confidence.toFixed(0)}%` : ""}
              </span>
              <span style={{ textAlign: "right" }}>
                <FreshnessBadge freshness={card.freshness} />
              </span>
            </div>
          ))}
          <div className="tiny faint" style={{ marginTop: 8 }}>
            Unavailable domains carry zero weight — they are never treated as neutral.
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-title">What is positive</div>
          {syn.positives.length ? (
            <ul className="finding-list positive">
              {syn.positives.map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          ) : <div className="unavailable">No clearly positive signal.</div>}
        </div>
        <div className="panel">
          <div className="panel-title">What is negative</div>
          {syn.negatives.length ? (
            <ul className="finding-list negative">
              {syn.negatives.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          ) : <div className="unavailable">No clearly negative signal.</div>}
        </div>
      </div>

      <div className="panel section" style={{ marginTop: 14 }}>
        <div className="panel-title">
          Contradictory signals
          {data.contradictions.is_high && (
            <span className="pill pill-important" style={{ marginLeft: 8 }}>HIGH</span>
          )}
        </div>
        {data.contradictions.contradictions.length ? (
          <>
            <ul className="finding-list warn">
              {data.contradictions.contradictions.map((c2, i) => (
                <li key={i}>
                  <span className="mono tiny faint">[{c2.strength.toFixed(0)}]</span> {c2.description}
                </li>
              ))}
            </ul>
            <div className="small dim" style={{ marginTop: 10 }}>{data.contradictions.summary}</div>
          </>
        ) : (
          <div className="dim small">None detected — the available signals are broadly consistent.</div>
        )}
      </div>

      <div className="panel section">
        <div className="panel-title">Scenarios</div>
        {data.scenarios.map((s) => (
          <div key={s.name} style={{ marginBottom: 14 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong style={{ textTransform: "uppercase", fontSize: 12 }}>{s.name}</strong>
              <span className="mono">
                {s.probability.toFixed(0)}%
                <span className="tiny faint"> (indicative analytical probability)</span>
              </span>
            </div>
            <div className="small dim" style={{ margin: "4px 0" }}>{s.label}</div>
            <div className="small">{s.narrative}</div>
            {s.conditions.length > 0 && (
              <ul className="finding-list neutral" style={{ marginTop: 6 }}>
                {s.conditions.slice(0, 3).map((cond, i) => <li key={i} className="small">{cond}</li>)}
              </ul>
            )}
            {s.invalidation && (
              <div className="tiny faint" style={{ marginTop: 4 }}>Invalidation: {s.invalidation}</div>
            )}
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-title">Upcoming catalysts</div>
          {syn.key_catalysts.length ? (
            <ul className="finding-list neutral">
              {syn.key_catalysts.map((k, i) => <li key={i}>{k}</li>)}
            </ul>
          ) : <div className="unavailable">None identified.</div>}
        </div>
        <div className="panel">
          <div className="panel-title">Risks</div>
          {syn.key_risks.length ? (
            <ul className="finding-list warn">
              {syn.key_risks.map((k, i) => <li key={i}>{k}</li>)}
            </ul>
          ) : <div className="dim small">No specific risk beyond normal market risk.</div>}
        </div>
      </div>

      <div className="panel section" style={{ marginTop: 14 }}>
        <div className="panel-title">What would change my mind</div>
        {syn.what_would_change_my_mind.length ? (
          <ul className="finding-list neutral">
            {syn.what_would_change_my_mind.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        ) : <div className="unavailable">Not determined from the available data.</div>}
      </div>

      <div className="panel section">
        <div className="panel-title">
          Synthesis {!syn.llm_used && <span className="tiny faint">(deterministic — no LLM configured)</span>}
        </div>
        <div className="small" style={{ whiteSpace: "pre-wrap" }}>{syn.text}</div>
        {syn.data_quality_note && (
          <div className="tiny faint" style={{ marginTop: 10 }}>{syn.data_quality_note}</div>
        )}
      </div>
    </>
  );
}

/* --------------------------------------------------------------- Technical */

function Technical({ data }: { data: AssetDetail }) {
  const mtf = data.domains.mtf;
  const tfs = Object.keys(data.technical);
  const [selected, setSelected] = useState(tfs.includes("1d") ? "1d" : tfs[0]);
  const snap = data.technical[selected];

  return (
    <>
      <div className="panel section">
        <div className="panel-title">Multi-timeframe</div>
        <table>
          <thead>
            <tr><th>TF</th><th>Direction</th><th>Trend</th><th className="num">Weight</th><th className="num">RSI</th></tr>
          </thead>
          <tbody>
            {mtf?.verdicts?.map((v: any) => (
              <tr key={v.timeframe}>
                <td className="mono">{v.timeframe}</td>
                <td className={v.available ? signClass(v.direction === "BULLISH" ? 1 : v.direction === "BEARISH" ? -1 : 0) : "unavailable"}>
                  {v.available ? v.direction : "UNAVAILABLE"}
                </td>
                <td className="dim">{v.available ? v.trend : "—"}</td>
                <td className="num dim">{v.weight.toFixed(2)}</td>
                <td className="num">{v.rsi ? v.rsi.toFixed(1) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row small" style={{ marginTop: 10, gap: 20 }}>
          <span>Alignment <span className={`mono ${signClass(mtf?.alignment_score)}`}>{fmtSigned(mtf?.alignment_score, 1)}</span></span>
          <span>Coherence <span className="mono">{mtf?.coherence?.toFixed(0)}%</span></span>
        </div>
        {mtf?.conflicts?.map((c: string, i: number) => (
          <div key={i} className="small" style={{ color: "var(--warn)", marginTop: 6 }}>! {c}</div>
        ))}
      </div>

      <div className="tabs">
        {tfs.map((tf) => (
          <button key={tf} className={`tab ${selected === tf ? "active" : ""}`} onClick={() => setSelected(tf)}>
            {tf}
          </button>
        ))}
      </div>

      {!snap ? <Unavailable /> : (
        <div className="grid-2">
          <div className="panel">
            <div className="panel-title">Indicators — {snap.timeframe}</div>
            <div className="kv"><span>Trend</span><span>{snap.trend.direction} ({snap.trend.strength.toFixed(0)})</span></div>
            <div className="kv"><span>EMA 20</span><span><Value v={snap.ema20} /></span></div>
            <div className="kv"><span>EMA 50</span><span><Value v={snap.ema50} /></span></div>
            <div className="kv"><span>EMA 200</span><span><Value v={snap.ema200} /></span></div>
            <div className="kv"><span>RSI 14</span><span>{snap.rsi?.toFixed(1) ?? "UNAVAILABLE"} <span className="tiny faint">{snap.rsi_state}</span></span></div>
            <div className="kv"><span>MACD</span><span>{snap.macd_state}</span></div>
            <div className="kv"><span>ADX</span><span>{snap.adx?.toFixed(1) ?? "—"}</span></div>
            <div className="kv"><span>ATR %</span><span>{snap.atr_pct?.toFixed(2) ?? "—"} <span className="tiny faint">{snap.volatility_state}</span></span></div>
            <div className="kv"><span>Rel. volume</span><span>{snap.relative_volume?.toFixed(2) ?? "—"}x <span className="tiny faint">{snap.volume_state}</span></span></div>
            <div className="kv"><span>Structure</span><span>{snap.structure} {snap.structure_labels?.join(" ")}</span></div>
            <div className="tiny faint" style={{ marginTop: 8 }}>{snap.bars} bars · {snap.trend.reason}</div>
            {snap.notes?.map((n, i) => <div key={i} className="tiny" style={{ color: "var(--warn)" }}>{n}</div>)}
          </div>

          <div className="panel">
            <div className="panel-title">Levels</div>
            <table>
              <thead><tr><th>Type</th><th className="num">Price</th><th className="num">Touches</th><th className="num">Distance</th></tr></thead>
              <tbody>
                {snap.levels_resistance.map((l, i) => (
                  <tr key={`r${i}`}>
                    <td className="neg">Resistance</td>
                    <td className="num">{fmtNumber(l.price, 0)}</td>
                    <td className="num dim">{l.touches}</td>
                    <td className="num dim">{fmtSigned(l.distance_pct, 1, "%")}</td>
                  </tr>
                ))}
                {snap.levels_support.map((l, i) => (
                  <tr key={`s${i}`}>
                    <td className="pos">Support</td>
                    <td className="num">{fmtNumber(l.price, 0)}</td>
                    <td className="num dim">{l.touches}</td>
                    <td className="num dim">{fmtSigned(l.distance_pct, 1, "%")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <div className="panel-title">Chart patterns</div>
            {snap.patterns.length ? snap.patterns.map((p, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong className="small">{p.pattern.replace(/_/g, " ")}</strong>
                  <span className="row" style={{ gap: 6 }}>
                    <span className="pill">{p.confirmation_state}</span>
                    <span className="mono tiny">{p.confidence.toFixed(0)}%</span>
                  </span>
                </div>
                <div className="tiny dim">{p.notes}</div>
                {p.invalidation_level && (
                  <div className="tiny faint">Invalidation: {fmtNumber(p.invalidation_level, 0)}</div>
                )}
              </div>
            )) : <div className="dim small">No pattern above the confidence threshold — nothing is announced on a vague resemblance.</div>}
          </div>

          <div className="panel">
            <div className="panel-title">Divergences</div>
            {snap.divergences.length ? (
              <ul className="finding-list neutral">
                {snap.divergences.map((d, i) => (
                  <li key={i} className="small">
                    {d.indicator} {d.kind.replace(/_/g, " ")} · strength {d.strength.toFixed(0)}
                  </li>
                ))}
              </ul>
            ) : <div className="dim small">None detected.</div>}
          </div>
        </div>
      )}
    </>
  );
}

/* --------------------------------------------------------------------- ETF */

function ETF({ data }: { data: AssetDetail }) {
  const etf = data.domains.etf;
  const card = data.scores.etf;
  if (!etf?.available) return <div className="panel"><Unavailable reason={etf?.unavailable_reason} /></div>;

  return (
    <>
      <div className="grid-2">
        <div className="panel">
          <div className="panel-title">
            Flows
            {card?.evidence_ids && <WhyButton evidenceIds={card.evidence_ids} label="ETF flows" />}
          </div>
          <div className="kv"><span>Latest ({etf.latest_date?.slice(0, 10)})</span><span className={signClass(etf.latest_total)}>{fmtSigned(etf.latest_total, 1, " M$")}</span></div>
          <div className="kv"><span>3-day average</span><span className={signClass(etf.ma_3d)}>{fmtSigned(etf.ma_3d, 1, " M$")}</span></div>
          <div className="kv"><span>5-day average</span><span className={signClass(etf.ma_5d)}>{fmtSigned(etf.ma_5d, 1, " M$")}</span></div>
          <div className="kv"><span>7-day average</span><span className={signClass(etf.ma_7d)}>{fmtSigned(etf.ma_7d, 1, " M$")}</span></div>
          <div className="kv"><span>30-day cumulative</span><span className={signClass(etf.cumulative_30d)}>{fmtSigned(etf.cumulative_30d, 0, " M$")}</span></div>
          <div className="kv"><span>Acceleration</span><span className={signClass(etf.acceleration_pct)}>{fmtSigned(etf.acceleration_pct, 0, "%")}</span></div>
          <div className="kv"><span>Streak</span><span>{etf.streak_days} {etf.streak_direction ?? ""}</span></div>
          {etf.reversal && <div className="kv"><span>Reversal</span><span className="pill pill-watch">{etf.reversal}</span></div>}
        </div>

        <div className="panel">
          <div className="panel-title">Flow vs price</div>
          {etf.flow_price_divergence ? (
            <>
              <div className="pill pill-important">{etf.flow_price_divergence}</div>
              <div className="small" style={{ marginTop: 8 }}>{etf.divergence_detail}</div>
            </>
          ) : <div className="dim small">No significant divergence between flows and price.</div>}

          <div className="panel-title" style={{ marginTop: 16 }}>By fund (latest day)</div>
          <table>
            <tbody>
              {Object.entries(etf.latest_by_ticker ?? {})
                .sort((a: any, b: any) => Math.abs(b[1]) - Math.abs(a[1]))
                .map(([ticker, v]: any) => (
                  <tr key={ticker}>
                    <td className="mono">{ticker}</td>
                    <td className={`num ${signClass(v)}`}>{fmtSigned(v, 1)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel section" style={{ marginTop: 14 }}>
        <div className="panel-title">Daily history (last 30 days, M$)</div>
        <FlowBars history={etf.history ?? []} />
      </div>
    </>
  );
}

function FlowBars({ history }: { history: { date: string; total_musd: number }[] }) {
  const recent = history.slice(-30);
  if (!recent.length) return <Unavailable />;
  const max = Math.max(...recent.map((h) => Math.abs(h.total_musd)), 1);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 2, height: 120 }}>
      {recent.map((h, i) => {
        const pct = (Math.abs(h.total_musd) / max) * 50;
        const positive = h.total_musd >= 0;
        return (
          <div key={i} title={`${h.date.slice(0, 10)}: ${h.total_musd.toFixed(1)} M$`}
               style={{ flex: 1, height: "100%", position: "relative" }}>
            <div style={{
              position: "absolute", left: 0, right: 0,
              [positive ? "bottom" : "top"]: "50%",
              height: `${pct}%`,
              background: positive ? "var(--bull)" : "var(--bear)",
              opacity: 0.85, borderRadius: 1,
            } as React.CSSProperties} />
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------- Derivatives */

function Derivatives({ data }: { data: AssetDetail }) {
  const d = data.domains.derivatives;
  if (!d?.available) return <div className="panel"><Unavailable reason={d?.unavailable_reason} /></div>;

  return (
    <div className="grid-2">
      <div className="panel">
        <div className="panel-title">Positioning</div>
        <div className="kv"><span>Funding rate (8h)</span><span>{d.funding_rate?.toFixed(6) ?? "UNAVAILABLE"}</span></div>
        <div className="kv"><span>State</span><span className="pill">{d.funding_state}</span></div>
        <div className="kv"><span>Annualised</span><span className={signClass(d.funding_annualized_pct)}>{fmtSigned(d.funding_annualized_pct, 2, "%")}</span></div>
        <div className="kv"><span>Open interest</span><span>{fmtNumber(d.open_interest, 0)}</span></div>
        <div className="kv"><span>OI 24h change</span><span className={signClass(d.oi_change_24h_pct)}>{fmtSigned(d.oi_change_24h_pct, 2, "%")}</span></div>
        <div className="kv"><span>Long/short ratio</span><span>{d.long_short_ratio?.toFixed(3) ?? "—"} <span className="tiny faint">{d.ls_state}</span></span></div>
        <div className="kv"><span>Basis</span><span className={signClass(d.basis_pct)}>{fmtSigned(d.basis_pct, 4, "%")}</span></div>
        {!d.liquidations_available && (
          <div className="unavailable tiny" style={{ marginTop: 10 }}>{d.liquidations_note}</div>
        )}
      </div>
      <div className="panel">
        <div className="panel-title">Interpretation</div>
        {d.price_oi_regime && <div className="pill pill-watch">{d.price_oi_regime}</div>}
        {d.regime_interpretation && <div className="small" style={{ marginTop: 8 }}>{d.regime_interpretation}</div>}
        {d.findings?.length > 0 && (
          <ul className="finding-list neutral" style={{ marginTop: 12 }}>
            {d.findings.map((f: string, i: number) => <li key={i} className="small">{f}</li>)}
          </ul>
        )}
        {d.warnings?.length > 0 && (
          <ul className="finding-list warn" style={{ marginTop: 10 }}>
            {d.warnings.map((w: string, i: number) => <li key={i} className="small">{w}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- On-chain */

function OnChain({ data }: { data: AssetDetail }) {
  const oc = data.domains.onchain;
  if (!oc?.available) return <div className="panel"><Unavailable reason={oc?.unavailable_reason} /></div>;

  return (
    <div className="grid-2">
      <div className="panel">
        <div className="panel-title">Metrics — {oc.chain_type}</div>
        <table>
          <tbody>
            {Object.entries(oc.metrics ?? {}).map(([k, v]: any) => (
              <tr key={k}>
                <td className="dim">{k.replace("onchain.", "")}</td>
                <td className="num">{fmtNumber(v, 2)} <span className="tiny faint">{oc.units?.[k] ?? ""}</span></td>
                <td className={`num tiny ${signClass(oc.trends?.[k])}`}>
                  {oc.trends?.[k] !== undefined ? fmtSigned(oc.trends[k], 1, "%") : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <div className="panel-title">Reading</div>
        <ul className="finding-list neutral">
          {oc.findings?.map((f: string, i: number) => <li key={i} className="small">{f}</li>)}
        </ul>
        {oc.not_applicable?.length > 0 && (
          <div className="tiny faint" style={{ marginTop: 12 }}>
            Not applicable to this chain: {oc.not_applicable.join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Liquidity */

function Liquidity({ data }: { data: AssetDetail }) {
  const liq = data.domains.liquidity;
  const defi = data.domains.defi;
  return (
    <div className="grid-2">
      <div className="panel">
        <div className="panel-title">Stablecoin liquidity</div>
        {liq?.available ? (
          <>
            <div className="kv"><span>Regime</span><span className="pill">{liq.regime}</span></div>
            <div className="kv"><span>Total supply</span><span>{fmtNumber(liq.total_supply, 2, " $")}</span></div>
            <div className="kv"><span>Change 1d</span><span className={signClass(liq.change_1d_pct)}>{fmtSigned(liq.change_1d_pct, 2, "%")}</span></div>
            <div className="kv"><span>Change 7d</span><span className={signClass(liq.change_7d_pct)}>{fmtSigned(liq.change_7d_pct, 2, "%")}</span></div>
            <div className="panel-title" style={{ marginTop: 14 }}>By chain</div>
            <table><tbody>
              {Object.entries(liq.by_chain ?? {}).sort((a: any, b: any) => b[1] - a[1]).map(([c, v]: any) => (
                <tr key={c}><td className="dim">{c}</td><td className="num">{fmtNumber(v, 2, " $")}</td></tr>
              ))}
            </tbody></table>
          </>
        ) : <Unavailable reason={liq?.unavailable_reason} />}
      </div>
      <div className="panel">
        <div className="panel-title">DeFi / TVL</div>
        {defi?.available ? (
          <>
            <div className="kv"><span>Chain TVL</span><span>{fmtNumber(defi.tvl, 2, " $")}</span></div>
            <div className="kv"><span>TVL 7d</span><span className={signClass(defi.tvl_change_7d_pct)}>{fmtSigned(defi.tvl_change_7d_pct, 1, "%")}</span></div>
            <div className="kv"><span>TVL 30d</span><span className={signClass(defi.tvl_change_30d_pct)}>{fmtSigned(defi.tvl_change_30d_pct, 1, "%")}</span></div>
            <div className="kv"><span>DEX volume 24h</span><span>{fmtNumber(defi.dex_volume_24h, 2, " $")}</span></div>
            <div className="kv"><span>Fees 24h</span><span>{fmtNumber(defi.fees_24h, 2, " $")}</span></div>
            {defi.tvl_price_divergence && (
              <div className="pill pill-watch" style={{ marginTop: 10 }}>{defi.tvl_price_divergence}</div>
            )}
            <ul className="finding-list neutral" style={{ marginTop: 10 }}>
              {defi.findings?.map((f: string, i: number) => <li key={i} className="small">{f}</li>)}
            </ul>
          </>
        ) : <Unavailable reason={defi?.unavailable_reason} />}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- Macro */

function Macro({ data }: { data: AssetDetail }) {
  const m = data.domains.macro;
  const reg = data.domains.regulation;
  const geo = data.domains.geopolitics;

  return (
    <>
      <div className="grid-2">
        <div className="panel">
          <div className="panel-title">Macro</div>
          {m?.available ? (
            <>
              <div className="kv"><span>Risk appetite</span><span>{m.risk_appetite}</span></div>
              <div className="kv"><span>Dollar</span><span>{m.dollar_trend}</span></div>
              <div className="kv"><span>Rates</span><span>{m.rates_trend}</span></div>
              <table style={{ marginTop: 10 }}><tbody>
                {Object.entries(m.metrics ?? {}).map(([k, v]: any) => (
                  <tr key={k}><td className="dim">{k.replace("macro.", "")}</td><td className="num">{fmtNumber(v, 2)}</td></tr>
                ))}
              </tbody></table>
              {m.missing?.length > 0 && (
                <div className="unavailable tiny" style={{ marginTop: 10 }}>Missing: {m.missing.join(", ")}</div>
              )}
            </>
          ) : <Unavailable reason={m?.unavailable_reason} />}
        </div>

        <div className="panel">
          <div className="panel-title">Upcoming events</div>
          {m?.upcoming_events?.length ? (
            <table>
              <tbody>
                {m.upcoming_events.map((e: any, i: number) => (
                  <tr key={i}>
                    <td className="mono tiny">{new Date(e.scheduled_at).toLocaleString()}</td>
                    <td>{e.name}</td>
                    <td className="num tiny">{e.hours_until?.toFixed(0)}h</td>
                    <td><span className={`pill pill-${e.importance?.toLowerCase()}`}>{e.importance}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="dim small">No scheduled event in the calendar window.</div>}
          {m?.imminent_event && (
            <div className="pill pill-critical" style={{ marginTop: 10 }}>
              {m.imminent_event.name} in {m.imminent_event.hours_until?.toFixed(1)}h
            </div>
          )}
        </div>
      </div>

      <div className="panel section" style={{ marginTop: 14 }}>
        <div className="panel-title">Regulation & politics</div>
        {reg?.available ? (
          <>
            <div className="row small" style={{ gap: 18, marginBottom: 10 }}>
              <span>{reg.events.length} items</span>
              <span className="pos">{reg.binding_count} binding</span>
              <span className="dim">{reg.proposal_count} proposals (not law)</span>
            </div>
            <table>
              <tbody>
                {reg.events.map((e: any, i: number) => (
                  <tr key={i}>
                    <td style={{ width: 150 }}><LegalStatusPill status={e.legal_status} /></td>
                    <td className="tiny dim" style={{ width: 90 }}>{e.institution}</td>
                    <td>
                      {e.source_url ? <a href={e.source_url} target="_blank" rel="noreferrer">{e.title}</a> : e.title}
                      <div className="tiny faint">
                        {new Date(e.published_at).toLocaleDateString()} · uncertainty {e.uncertainty?.toFixed(0)}%
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {reg.proposal_count > 0 && (
              <div className="tiny" style={{ color: "var(--warn)", marginTop: 10 }}>
                Proposals are NOT adopted law — they change nothing legally until enacted.
              </div>
            )}
          </>
        ) : <Unavailable reason={reg?.unavailable_reason} />}
      </div>

      {geo?.available && (
        <div className="panel section">
          <div className="panel-title">Geopolitical risk</div>
          <div className="row" style={{ gap: 12 }}>
            <span className={`pill ${geo.level === "HIGH" || geo.level === "EXTREME" ? "pill-critical" : "pill-info"}`}>
              {geo.level}
            </span>
            <span className="mono small">{geo.score?.toFixed(0)}/100</span>
          </div>
          <div className="small" style={{ marginTop: 8 }}>{geo.justification}</div>
          <div className="small dim" style={{ marginTop: 6 }}>{geo.crypto_implication}</div>
          <div className="tiny faint" style={{ marginTop: 8 }}>{geo.disclaimer}</div>
        </div>
      )}
    </>
  );
}

/* --------------------------------------------------------------------- News */

function News({ data }: { data: AssetDetail }) {
  const n = data.domains.news;
  if (!n?.available) return <div className="panel"><Unavailable reason={n?.unavailable_reason} /></div>;
  return (
    <div className="panel">
      <div className="panel-title">
        Events — {n.unique_events} distinct from {n.total_items} items ({n.duplicates_removed} republications collapsed)
      </div>
      <table>
        <tbody>
          {n.clusters?.map((c: any, i: number) => (
            <tr key={i}>
              <td style={{ width: 40 }}><span className="pill">T{c.best_tier}</span></td>
              <td className="tiny dim" style={{ width: 110 }}>{c.primary_source}</td>
              <td>
                {c.items?.[0]?.url ? <a href={c.items[0].url} target="_blank" rel="noreferrer">{c.event_title}</a> : c.event_title}
                <div className="tiny faint">
                  {new Date(c.published_at).toLocaleString()}
                  {c.duplicate_count > 0 && ` · +${c.duplicate_count} republications`}
                  {c.assets?.length > 0 && ` · ${c.assets.join(", ")}`}
                </div>
              </td>
              <td className="num tiny dim" style={{ width: 50 }}>{c.importance?.toFixed(0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------- Whales */

function Whales({ data }: { data: AssetDetail }) {
  const w = data.domains.whale;
  return (
    <div className="panel">
      <div className="panel-title">Whale activity</div>
      {w?.available ? (
        <>
          <div className="kv"><span>Behaviour</span><span>{w.behaviour}</span></div>
          <div className="kv"><span>Reliability</span><span className="pill">{w.reliability}</span></div>
          <div className="kv"><span>Net exchange flow</span><span className={signClass(w.exchange_netflow)}>{fmtSigned(w.exchange_netflow, 0)}</span></div>
          <div className="kv"><span>Whale threshold</span><span>{w.threshold} {w.threshold_unit}</span></div>
          <ul className="finding-list neutral" style={{ marginTop: 10 }}>
            {w.findings?.map((f: string, i: number) => <li key={i} className="small">{f}</li>)}
          </ul>
        </>
      ) : (
        <>
          <Unavailable reason={w?.unavailable_reason} />
          <div className="small dim" style={{ marginTop: 10 }}>
            Whale threshold for {data.asset}: <span className="mono">{w?.threshold} {w?.threshold_unit}</span> —
            defined per asset, because 100 BTC and 50 000 SOL are different amounts of conviction.
          </div>
          <div className="tiny faint" style={{ marginTop: 8 }}>
            No whale signal is inferred without a reliable source. Configure GLASSNODE_API_KEY,
            CRYPTOQUANT_API_KEY, NANSEN_API_KEY or ARKHAM_API_KEY to enable this domain.
          </div>
        </>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- Historical */

function Historical({ data }: { data: AssetDetail }) {
  const h = data.domains.historical;
  if (!h?.available) return <div className="panel"><Unavailable reason={h?.unavailable_reason} /></div>;
  return (
    <div className="panel">
      <div className="panel-title">Historical analogues</div>
      <div className="small" style={{ marginBottom: 12 }}>{h.interpretation}</div>
      <table>
        <thead>
          <tr><th>Date</th><th className="num">Similarity</th><th className="num">+1d</th><th className="num">+3d</th><th className="num">+7d</th><th className="num">+30d</th></tr>
        </thead>
        <tbody>
          {h.matches?.map((m: any, i: number) => (
            <tr key={i}>
              <td className="mono">{m.date}</td>
              <td className="num">{(m.similarity * 100).toFixed(1)}%</td>
              {["1d", "3d", "7d", "30d"].map((k) => (
                <td key={k} className={`num ${signClass(m.forward_returns?.[k])}`}>
                  {m.forward_returns?.[k] !== null && m.forward_returns?.[k] !== undefined
                    ? fmtSigned(m.forward_returns[k], 2, "%") : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="tiny faint" style={{ marginTop: 12 }}>{h.caveat}</div>
    </div>
  );
}

/* ------------------------------------------------------------------- Report */

function Report({ symbol }: { symbol: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.report(symbol).then((r) => setText(r.text)).catch((e) => setError(String(e)));
  }, [symbol]);
  if (error) return <ErrorBox error={error} />;
  if (!text) return <Loading what="report" />;
  return <pre className="report-text">{text}</pre>;
}

/* ------------------------------------------------------------------ Sources */

function Sources({ data }: { data: AssetDetail }) {
  const ok = data.sources.filter((s) => s.ok).length;
  return (
    <div className="panel">
      <div className="panel-title">Data sources — {ok}/{data.sources.length} available</div>
      <table>
        <thead><tr><th>Capability</th><th>Status</th><th>Provider</th><th className="num">Obs.</th><th>Detail</th></tr></thead>
        <tbody>
          {data.sources.map((s, i) => (
            <tr key={i}>
              <td className="mono tiny">{s.capability}</td>
              <td className={s.ok ? "pos" : "unavailable"}>{s.ok ? "OK" : s.status}</td>
              <td className="tiny dim">{s.provider}</td>
              <td className="num tiny">{s.observations}</td>
              <td className="tiny faint">{s.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


/* ------------------------------------------------- Regime and entry timing */

function RegimeAndTiming({ data }: { data: AssetDetail }) {
  const regime = data.regime;
  const timing = data.entry_timing;

  if (!regime || !timing) return <div className="panel"><Unavailable /></div>;

  return (
    <>
      <div className="panel section">
        <div className="nuance" style={{ fontSize: 14, marginTop: 0 }}>
          <strong>Market regime</strong> answers "which way is this market leaning?".{" "}
          <strong>Entry timing</strong> answers "is right now a good moment?". They are
          computed independently and can disagree — that disagreement is the useful part.
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
            <div className="panel-title" style={{ margin: 0 }}>Market regime</div>
            <WhyVerdict
              title="Market regime"
              verdict={regime.regime}
              score={regime.regime_score}
              confidence={regime.confidence}
              factors={regime.factors}
              evidenceIds={regime.evidence_ids}
              missing={regime.missing}
            />
          </div>
          <div className="row" style={{ gap: 10, marginBottom: 10 }}>
            <span className={`regime-badge regime-${regime.regime}`}>{regime.regime}</span>
            <span className={`mono ${signClass(regime.regime_score)}`}>
              {fmtSigned(regime.regime_score, 1)}
            </span>
            <span className="tiny faint">confidence {regime.confidence.toFixed(0)}%</span>
          </div>
          {regime.conditions.length > 0 && (
            <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
              {regime.conditions.map((c) => (
                <span key={c} className="pill pill-watch">{c.replace(/_/g, " ")}</span>
              ))}
            </div>
          )}
          <div className="small dim">{regime.summary}</div>

          <div className="panel-title" style={{ marginTop: 16 }}>Contributing factors</div>
          {regime.factors
            .filter((f) => f.weight > 0)
            .sort((a, b) => Math.abs(b.contribution * b.weight) - Math.abs(a.contribution * a.weight))
            .map((f, i) => (
              <div key={i} className="factor-row">
                <span className="tiny">
                  {f.name}: <span className="mono">{f.value}</span>
                </span>
                <span className="factor-bar">
                  <span
                    className="factor-fill"
                    style={{
                      background: f.contribution >= 0 ? "var(--bull)" : "var(--bear)",
                      left: f.contribution >= 0 ? "50%" : `${50 - Math.min(Math.abs(f.contribution), 100) / 2}%`,
                      width: `${Math.min(Math.abs(f.contribution), 100) / 2}%`,
                    }}
                  />
                </span>
                <span className={`mono tiny ${signClass(f.contribution)}`} style={{ textAlign: "right" }}>
                  {fmtSigned(f.contribution, 0)}
                </span>
              </div>
            ))}
          {regime.missing.length > 0 && (
            <div className="tiny unavailable" style={{ marginTop: 10 }}>
              Not available: {regime.missing.join(", ")}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
            <div className="panel-title" style={{ margin: 0 }}>Entry timing</div>
            <WhyVerdict
              title="Entry timing"
              verdict={timing.timing}
              score={timing.timing_score}
              confidence={timing.confidence}
              factors={timing.factors}
              explanation={timing.explanation}
              evidenceIds={timing.evidence_ids}
              missing={timing.missing}
            />
          </div>
          <div className="row" style={{ gap: 10, marginBottom: 10 }}>
            <span className={`timing-badge timing-${timing.timing}`}>{timing.timing}</span>
            <span className={`mono ${signClass(timing.timing_score)}`}>
              {fmtSigned(timing.timing_score, 1)}
            </span>
            <span className="tiny faint">confidence {timing.confidence.toFixed(0)}%</span>
          </div>
          <div className="small dim">{timing.summary}</div>

          {timing.positives.length > 0 && (
            <>
              <div className="panel-title" style={{ marginTop: 14 }}>Supportive</div>
              <ul className="finding-list positive">
                {timing.positives.map((p, i) => <li key={i} className="small">{p}</li>)}
              </ul>
            </>
          )}
          {timing.negatives.length > 0 && (
            <>
              <div className="panel-title" style={{ marginTop: 14 }}>Adverse</div>
              <ul className="finding-list negative">
                {timing.negatives.map((n, i) => <li key={i} className="small">{n}</li>)}
              </ul>
            </>
          )}
          {timing.risks.length > 0 && (
            <>
              <div className="panel-title" style={{ marginTop: 14 }}>Risks</div>
              <ul className="finding-list warn">
                {timing.risks.map((r, i) => <li key={i} className="small">{r}</li>)}
              </ul>
            </>
          )}
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-title">Zones to watch</div>
          {timing.zones_to_watch.length === 0 ? (
            <div className="dim small">No zone identified from computed levels.</div>
          ) : (
            <table>
              <thead>
                <tr><th>Zone</th><th className="num">Range</th><th>Basis</th></tr>
              </thead>
              <tbody>
                {timing.zones_to_watch.map((z, i) => (
                  <tr key={i}>
                    <td className="small">{z.label}</td>
                    <td className="num mono tiny">
                      {z.low !== null ? fmtNumber(z.low, 2) : "—"} –{" "}
                      {z.high !== null ? fmtNumber(z.high, 2) : "—"}
                    </td>
                    <td className="tiny faint">{z.basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="tiny faint" style={{ marginTop: 10 }}>
            Every zone derives from computed levels (swing clustering, moving averages).
            No arbitrary price target is ever produced.
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Invalidation</div>
          {timing.invalidation_level !== null ? (
            <>
              <div className="stat-value">{fmtNumber(timing.invalidation_level, 2)}</div>
              <div className="small dim" style={{ marginTop: 6 }}>{timing.invalidation_reason}</div>
            </>
          ) : (
            <Unavailable reason={timing.invalidation_reason} />
          )}
        </div>
      </div>
    </>
  );
}
