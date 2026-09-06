/**
 * Market structure: cross-asset relationships, ratios, breadth, liquidity,
 * derivatives and breakout quality.
 *
 * Everything on this page is CONTEXT. None of it is a directional call, and
 * the labels say so where a reader might otherwise assume one - particularly
 * crowding, whose direction is genuinely not observable.
 */
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorBox, Loading } from "../components/common";

const ASSETS = ["BTC", "ETH", "SOL"];

function pct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function num(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export default function MarketStructure() {
  const [asset, setAsset] = useState("BTC");
  const [cross, setCross] = useState<any>(null);
  const [ratios, setRatios] = useState<any>(null);
  const [breadth, setBreadth] = useState<any>(null);
  const [liquidity, setLiquidity] = useState<any>(null);
  const [breakout, setBreakout] = useState<any>(null);
  const [derivatives, setDerivatives] = useState<any>(null);
  const [liquidations, setLiquidations] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.marketRatios(), api.marketBreadth(), api.marketLiquidity()])
      .then(([r, b, l]) => {
        setRatios(r);
        setBreadth(b);
        setLiquidity(l);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    setCross(null);
    setBreakout(null);
    Promise.all([
      api.crossAsset(asset),
      api.breakout(asset),
      api.derivativesAggregate(asset).catch(() => null),
      api.liquidations(asset).catch(() => null),
    ])
      .then(([c, bo, d, li]) => {
        setCross(c);
        setBreakout(bo);
        setDerivatives(d);
        setLiquidations(li);
      })
      .catch((e) => setError(String(e)));
  }, [asset]);

  if (error) return <ErrorBox error={error} />;

  return (
    <>
      <div className="panel section">
        <div className="panel-title">Market-wide context</div>
        <div className="stat-grid">
          <div className="stat-box">
            <div className="stat-label">Breadth</div>
            <div className="stat-value">{breadth?.state ?? "…"}</div>
            <div className="muted small">
              {breadth
                ? `${breadth.assets_above_ema50}/${breadth.assets_measured} above EMA50`
                : ""}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Liquidity regime</div>
            <div className="stat-value">{liquidity?.regime ?? "…"}</div>
            <div className="muted small">score {num(liquidity?.score, 1)}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">BTC dominance</div>
            <div className="stat-value">
              {ratios?.btc_dominance?.available
                ? `${ratios.btc_dominance.btc_dominance_pct?.toFixed(2)}%`
                : "UNAVAILABLE"}
            </div>
            <div className="muted small">
              {ratios?.btc_dominance?.available ? "live, not stored historically" : ""}
            </div>
          </div>
        </div>
        {breadth?.interpretation && <p className="muted small">{breadth.interpretation}</p>}
        {liquidity?.interpretation && <p className="muted small">{liquidity.interpretation}</p>}
      </div>

      <div className="panel section">
        <div className="panel-title">Ratios</div>
        <table className="table">
          <thead>
            <tr>
              <th>Pair</th><th>Value</th><th>30d</th><th>Percentile</th><th>Trend</th>
            </tr>
          </thead>
          <tbody>
            {(ratios?.ratios ?? []).map((r: any) => (
              <tr key={r.name}>
                <td>{r.name}</td>
                <td>{num(r.value, 6)}</td>
                <td className={r.change_30d_pct > 0 ? "good" : "bad"}>
                  {pct(r.change_30d_pct)}
                </td>
                <td>{r.percentile === null ? "—" : `p${r.percentile}`}</td>
                <td>{r.trend}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel section">
        <div className="panel-title">
          Per-asset
          <span className="tabs">
            {ASSETS.map((a) => (
              <button
                key={a}
                className={a === asset ? "tab tab-active" : "tab"}
                onClick={() => setAsset(a)}
              >
                {a}
              </button>
            ))}
          </span>
        </div>

        {!cross ? (
          <Loading what={`${asset} context`} />
        ) : (
          <>
            <h4>Cross-asset correlation (90 days, on returns)</h4>
            <table className="table">
              <thead>
                <tr><th>Series</th><th>Correlation</th><th>Beta</th><th>vs own history</th></tr>
              </thead>
              <tbody>
                {(cross.correlations ?? []).map((c: any) => (
                  <tr key={c.series}>
                    <td>{c.label}</td>
                    <td className={c.correlation > 0 ? "good" : "bad"}>{num(c.correlation)}</td>
                    <td>{num(c.beta)}</td>
                    <td>
                      {c.percentile_vs_history === null
                        ? c.note || "—"
                        : `p${c.percentile_vs_history}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">{cross.interpretation}</p>
          </>
        )}

        {breakout && (
          <>
            <h4>Breakout quality</h4>
            <div className="stat-grid">
              <div className="stat-box">
                <div className="stat-label">State</div>
                <div className="stat-value">{breakout.state}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Conviction</div>
                <div className="stat-value">
                  {breakout.quality_score === null ? "—" : `${breakout.quality_score}/100`}
                </div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Level</div>
                <div className="stat-value">{num(breakout.level, 2)}</div>
              </div>
            </div>
            <p className="muted small">{breakout.interpretation}</p>
            <p className="muted small"><strong>{breakout.edge_note}</strong></p>
          </>
        )}

        {derivatives && (
          <>
            <h4>Derivatives across venues</h4>
            <table className="table">
              <thead>
                <tr><th>Venue</th><th>Funding</th><th>Open interest</th><th>Basis</th></tr>
              </thead>
              <tbody>
                {(derivatives.exchanges ?? []).map((e: any) => (
                  <tr key={e.exchange}>
                    <td>{e.exchange}</td>
                    <td>{e.available ? num(e.funding_rate, 6) : "—"}</td>
                    <td>
                      {e.open_interest_usd
                        ? `$${(e.open_interest_usd / 1e9).toFixed(2)}B`
                        : "—"}
                    </td>
                    <td>{e.available ? pct(e.basis_pct, 3) : e.reason?.slice(0, 40)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">
              OI-weighted funding {num(derivatives.funding_weighted, 6)}, dispersion{" "}
              {num(derivatives.funding_dispersion, 6)}, concentration{" "}
              {num(derivatives.exchange_concentration, 3)}.
            </p>
            {derivatives.venue_anomaly && (
              <p className="pill pill-warn">{derivatives.venue_anomaly}</p>
            )}
          </>
        )}

        {liquidations && (
          <>
            <h4>Liquidations</h4>
            <p className="muted small">
              Data: <strong>{liquidations.data_state}</strong> — cascade conditions{" "}
              <strong>{liquidations.cascade_risk}</strong>
            </p>
            <p className="muted small">{liquidations.conditions_note}</p>
          </>
        )}
      </div>
    </>
  );
}
