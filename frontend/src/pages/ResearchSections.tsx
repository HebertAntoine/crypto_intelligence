/**
 * Research sections added in LOT 3.
 *
 * The organising principle: a result is never shown without its sample size,
 * and negative findings get the same visual weight as positive ones. A page
 * that only surfaces what works would be worse than no page.
 */
import { useEffect, useState } from "react";
import { api, type AuditData } from "../lib/api";
import { ErrorBox, Loading, Unavailable } from "../components/common";

const VERDICT_CLASS: Record<string, string> = {
  USEFUL: "pos",
  WEAK: "dim",
  UNSTABLE: "neg",
  NO_MEASURABLE_VALUE: "neg",
  INSUFFICIENT_DATA: "unavailable",
};

export function AuditSection() {
  const [data, setData] = useState<AuditData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.researchAudit().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="score audit" />;

  return (
    <>
      <div className="warning-box">
        This audit asks one question of every score: does it carry information about
        future returns? A weight is not justified by the domain sounding important.
      </div>

      {Object.entries(data.assets).map(([asset, result]) => (
        <div key={asset} className="panel section">
          <div className="panel-title">{asset}</div>
          <table className="research-table">
            <thead>
              <tr>
                <th>Domain</th><th className="num">Weight</th><th className="num">n</th>
                <th className="num">IC 7d</th><th className="num">Within-period</th>
                <th className="num">p</th><th>Monotonic</th>
                <th className="num">Stability</th><th className="num">Concentration</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.domains).map(([domain, r]) => {
                const decomposition = r.ic_decomposition;
                const inflated = decomposition?.globally_inflated;
                return (
                  <tr key={domain}>
                    <td>{domain}</td>
                    <td className="num">{r.current_weight.toFixed(2)}</td>
                    <td className="num dim">{r.n || "—"}</td>
                    <td className={`num ${r.significant ? "sig" : "insig"}`}>
                      {r.ic !== null && r.ic !== undefined
                        ? `${r.ic >= 0 ? "+" : ""}${r.ic.toFixed(3)}`
                        : "—"}
                    </td>
                    <td className={`num ${inflated ? "neg" : "dim"}`}>
                      {decomposition?.assessable && decomposition.mean_within_ic !== null
                        ? `${decomposition.mean_within_ic! >= 0 ? "+" : ""}${decomposition.mean_within_ic!.toFixed(3)}`
                        : "—"}
                    </td>
                    <td className="num tiny dim">{r.p_value ?? "—"}</td>
                    <td className={r.monotonic ? "pos" : "dim"}>
                      {r.n ? (r.monotonic ? "yes" : "no") : "—"}
                    </td>
                    <td className="num dim">{r.n ? r.stability_score.toFixed(0) : "—"}</td>
                    <td className="num dim">
                      {r.concentration ? `${r.concentration.dominant_share.toFixed(0)}%` : "—"}
                    </td>
                    <td className={VERDICT_CLASS[r.verdict] ?? "dim"}>
                      <span className="tiny">{r.verdict}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="stat-grid" style={{ marginTop: 12 }}>
            <div className="stat-box">
              <div className="stat-label">Weight on USEFUL</div>
              <div className={`stat-value ${result.summary.weight_on_useful > 0 ? "pos" : "neg"}`}>
                {result.summary.weight_on_useful.toFixed(2)}
              </div>
            </div>
            <div className="stat-box">
              <div className="stat-label">On worthless / unstable</div>
              <div className="stat-value neg">
                {result.summary.weight_on_worthless_or_unstable.toFixed(2)}
              </div>
            </div>
            <div className="stat-box">
              <div className="stat-label">Not measurable</div>
              <div className="stat-value dim">
                {result.summary.weight_on_unmeasured.toFixed(2)}
              </div>
            </div>
          </div>

          {Object.entries(result.domains)
            .filter(([, r]) => r.ic_decomposition?.globally_inflated)
            .map(([domain, r]) => (
              <div key={domain} className="warning-box" style={{ marginTop: 10 }}>
                <strong>{domain}</strong> — {r.ic_decomposition!.interpretation}
              </div>
            ))}
        </div>
      ))}

      <div className="panel">
        <div className="tiny faint">{data.note}</div>
      </div>
    </>
  );
}

export function AsymmetrySection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    setData(null);
    api.researchAsymmetry(symbol).then(setData).catch(() => setData({ available: false }));
  }, [symbol]);

  if (!data) return <Loading what="ETF asymmetry" />;
  if (!data.available) return <div className="panel"><Unavailable reason={data.reason} /></div>;

  const order = ["extreme_outflow", "moderate_outflow", "neutral", "moderate_inflow", "extreme_inflow"];

  return (
    <div className="panel section">
      <div className="panel-title">
        ETF flow asymmetry — {symbol} ({data.period.days} days)
      </div>
      <div className="small dim" style={{ marginBottom: 10 }}>
        Inflows and outflows are measured separately. A single correlation assumes they
        are mirror images; this does not.
      </div>
      <table className="research-table">
        <thead>
          <tr>
            <th>Category</th><th className="num">n</th><th className="num">Mean 7d</th>
            <th className="num">Edge</th><th className="num">Win</th>
            <th className="num">CI 95%</th><th className="num">MFE</th>
            <th className="num">MAE</th><th>Sig</th>
          </tr>
        </thead>
        <tbody>
          {order.map((name) => {
            const c = data.categories[name];
            if (!c) return null;
            if (!c.available) {
              return (
                <tr key={name}>
                  <td>{name.replace(/_/g, " ")}</td>
                  <td className="num dim">{c.n}</td>
                  <td colSpan={7} className="unavailable tiny">{c.reason}</td>
                </tr>
              );
            }
            const h = c.horizons["7d"];
            return (
              <tr key={name}>
                <td>{name.replace(/_/g, " ")}</td>
                <td className="num dim">{h.n}</td>
                <td className="num">{h.mean?.toFixed(2)}%</td>
                <td className={`num ${(h.edge_vs_baseline ?? 0) > 0 ? "pos" : "neg"}`}>
                  {h.edge_vs_baseline >= 0 ? "+" : ""}{h.edge_vs_baseline?.toFixed(2)}%
                </td>
                <td className="num dim">{h.win_rate?.toFixed(0)}%</td>
                <td className="num tiny dim">
                  {h.ci95_low !== null ? `[${h.ci95_low.toFixed(1)},${h.ci95_high.toFixed(1)}]` : "—"}
                </td>
                <td className="num pos tiny">+{h.mfe_median?.toFixed(1)}%</td>
                <td className="num neg tiny">{h.mae_median?.toFixed(1)}%</td>
                <td className={h.significant_fdr ? "pos" : "dim"}>
                  <span className="tiny">{h.significant_fdr ? "FDR" : h.ci_excludes_zero ? "CI" : "—"}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {data.asymmetry?.assessable && (
        <div className={data.asymmetry.verdict === "NO_ASYMMETRY_DEMONSTRATED" ? "warning-box" : "nuance"}>
          <strong>{data.asymmetry.verdict.replace(/_/g, " ")}</strong> — {data.asymmetry.conclusion}
        </div>
      )}
    </div>
  );
}

export function DerivativesSection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    setData(null);
    api.researchDerivatives(symbol).then(setData).catch(() => setData({ error: true }));
  }, [symbol]);

  if (!data) return <Loading what="derivatives study" />;
  const bands = data.percentile_bands;
  if (!bands?.available) return <div className="panel"><Unavailable reason={bands?.reason} /></div>;

  const order = ["p0_5", "p5_20", "p20_80", "p80_95", "p95_100"];

  return (
    <>
      <div className="panel section">
        <div className="panel-title">Funding percentile bands — {symbol}</div>
        {bands.current_threshold_mapping?.diagnosis && (
          <div className="warning-box">{bands.current_threshold_mapping.diagnosis}</div>
        )}
        <table className="research-table">
          <thead>
            <tr>
              <th>Band</th><th className="num">n</th><th className="num">Funding range</th>
              <th className="num">Mean 7d</th><th className="num">Edge</th>
              <th className="num">Win</th><th>Sig</th>
            </tr>
          </thead>
          <tbody>
            {order.map((name) => {
              const b = bands.bands[name];
              if (!b?.available) {
                return (
                  <tr key={name}>
                    <td>{name}</td><td className="num dim">{b?.n ?? 0}</td>
                    <td colSpan={5} className="unavailable tiny">{b?.reason}</td>
                  </tr>
                );
              }
              const h = b.horizons["7d"];
              return (
                <tr key={name}>
                  <td className="mono tiny">{name}</td>
                  <td className="num dim">{h.n}</td>
                  <td className="num tiny dim">
                    {b.funding_range ? `${b.funding_range[0].toFixed(5)} … ${b.funding_range[1].toFixed(5)}` : "—"}
                  </td>
                  <td className="num">{h.mean?.toFixed(2)}%</td>
                  <td className={`num ${(h.edge_vs_baseline ?? 0) > 0 ? "pos" : "neg"}`}>
                    {h.edge_vs_baseline >= 0 ? "+" : ""}{h.edge_vs_baseline?.toFixed(2)}%
                  </td>
                  <td className="num dim">{h.win_rate?.toFixed(0)}%</td>
                  <td className={h.significant_fdr ? "pos" : "dim"}>
                    <span className="tiny">{h.significant_fdr ? "FDR" : "—"}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {data.suggested_thresholds?.available && (
          <div style={{ marginTop: 12 }}>
            <div className="panel-title">Percentile-derived thresholds (proposal only)</div>
            <div className="mono tiny dim">
              extreme_negative {data.suggested_thresholds.suggested.extreme_negative} ·
              neutral [{data.suggested_thresholds.suggested.neutral_low},{" "}
              {data.suggested_thresholds.suggested.neutral_high}] ·
              extreme {data.suggested_thresholds.suggested.extreme}
            </div>
            <div className="tiny faint" style={{ marginTop: 6 }}>
              {data.suggested_thresholds.rationale}
            </div>
          </div>
        )}
      </div>

      <div className="panel section">
        <div className="panel-title">Price × open interest × funding</div>
        {data.price_oi_funding?.available ? (
          <table className="research-table">
            <thead>
              <tr><th>State</th><th className="num">n</th><th className="num">Mean 7d</th><th className="num">Win</th></tr>
            </thead>
            <tbody>
              {Object.entries(data.price_oi_funding.states).map(([name, s]: any) => (
                <tr key={name}>
                  <td className="tiny">{name.replace(/_/g, " ")}</td>
                  <td className="num dim">{s.n}</td>
                  {s.available ? (
                    <>
                      <td className="num">{s.horizons["7d"].mean?.toFixed(2)}%</td>
                      <td className="num dim">{s.horizons["7d"].win_rate?.toFixed(0)}%</td>
                    </>
                  ) : (
                    <td colSpan={2} className="unavailable tiny">{s.reason}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Unavailable reason={data.price_oi_funding?.reason} />
        )}
      </div>
    </>
  );
}

export function RegimeSection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    setData(null);
    api.researchRegimes(symbol).then(setData).catch(() => setData({ available: false }));
  }, [symbol]);

  if (!data) return <Loading what="regime-conditioned signals" />;
  if (!data.available) return <div className="panel"><Unavailable reason={data.reason} /></div>;

  return (
    <div className="panel section">
      <div className="panel-title">Signals conditioned by regime — {symbol}</div>
      <div className="small dim" style={{ marginBottom: 8 }}>
        Each signal is compared against days in the SAME regime where it is absent, which
        isolates the signal from the regime it occurs in.
      </div>
      <div className="mono tiny faint" style={{ marginBottom: 12 }}>
        Regime distribution: {Object.entries(data.regime_distribution)
          .map(([r, n]) => `${r} ${n}`).join(" · ")}
      </div>

      {Object.entries(data.signals).map(([name, result]: any) => {
        if (!result.available) return null;
        const cells = Object.entries(result.by_regime).filter(([, c]: any) => c.available);
        if (!cells.length) return null;
        return (
          <div key={name} style={{ marginBottom: 16 }}>
            <strong className="small">{name.replace(/_/g, " ")}</strong>
            <table className="research-table" style={{ marginTop: 6 }}>
              <thead>
                <tr>
                  <th>Regime</th><th className="num">n</th><th className="num">Signal</th>
                  <th className="num">Same-regime baseline</th><th className="num">Edge</th>
                  <th className="num">Win</th><th>Sig</th>
                </tr>
              </thead>
              <tbody>
                {cells.map(([regime, c]: any) => (
                  <tr key={regime}>
                    <td className="tiny">{regime}</td>
                    <td className="num dim">{c.signal.n}</td>
                    <td className="num">{c.signal.mean?.toFixed(2)}%</td>
                    <td className="num dim">{c.regime_baseline.mean?.toFixed(2)}%</td>
                    <td className={`num ${c.edge_vs_regime > 0 ? "pos" : "neg"}`}>
                      {c.edge_vs_regime >= 0 ? "+" : ""}{c.edge_vs_regime?.toFixed(2)}%
                    </td>
                    <td className="num dim">{c.signal.win_rate?.toFixed(0)}%</td>
                    <td className={c.significant_fdr ? "pos" : "dim"}>
                      <span className="tiny">{c.significant_fdr ? "FDR" : "—"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="tiny faint" style={{ marginTop: 4 }}>
              {result.interpretation.conclusion}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function FeatureImportanceSection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    setData(null);
    api.researchFeatures(symbol, true).then(setData).catch(() => setData({ available: false }));
  }, [symbol]);

  if (!data) return <Loading what="feature importance (slow — walk-forward per feature)" />;
  if (!data.available) return <div className="panel"><Unavailable reason={data.reason} /></div>;

  const permutation = data.permutation_importance;

  return (
    <div className="panel section">
      <div className="panel-title">
        Feature importance — {symbol} ({data.feature_count} features, {data.period.rows} days)
      </div>

      {permutation?.available && (
        <div className={permutation.baseline_r2_oos <= 0 ? "warning-box" : "nuance"}>
          Ridge regression over {permutation.features_used} features:
          out-of-sample R² = <strong>{permutation.baseline_r2_oos.toFixed(4)}</strong>
          {permutation.baseline_r2_oos <= 0 && (
            <> — negative, meaning the features jointly explain less than a constant would.
            That is the finding, not a bug.</>
          )}
        </div>
      )}

      <table className="research-table">
        <thead>
          <tr>
            <th>Feature</th><th className="num">IC 7d</th><th className="num">p</th>
            <th className="num">n</th><th>Monotonic</th>
            <th className="num">Stability</th><th className="num">Usefulness</th><th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {data.ranking.slice(0, 25).map((r: any) => (
            <tr key={r.feature}>
              <td className="mono tiny">{r.feature}</td>
              <td className={`num ${r.significant_fdr ? "sig" : "insig"}`}>
                {r.ic_7d >= 0 ? "+" : ""}{r.ic_7d?.toFixed(3)}
              </td>
              <td className="num tiny dim">{r.p_value_7d ?? "—"}</td>
              <td className="num dim">{r.n}</td>
              <td className={r.monotonic_7d ? "pos" : "dim"}>
                {r.monotonic_7d ? "yes" : "no"}
              </td>
              <td className="num dim">{r.stability_score?.toFixed(0)}</td>
              <td className="num">{r.usefulness?.toFixed(2)}</td>
              <td className={VERDICT_CLASS[r.verdict] ?? "dim"}>
                <span className="tiny">{r.verdict}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChampionChallengerSection() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api.researchCandidateWeights().then(setData).catch(() => setData({ error: true }));
  }, []);

  if (!data) return <Loading what="champion vs challenger" />;
  if (data.error) return <div className="panel"><Unavailable /></div>;

  return (
    <>
      <div className="warning-box">
        The Champion is the weighting currently in use. A Challenger is only recommended
        if it beats it out of sample. <strong>Promotion is always manual</strong> — no code
        applies <span className="mono">config/scoring_candidate.yaml</span>.
      </div>

      {Object.entries(data.proposals ?? {}).map(([asset, proposal]: any) => {
        const comparison = data.comparisons?.[asset];
        return (
          <div key={asset} className="panel section">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div className="panel-title" style={{ margin: 0 }}>{asset}</div>
              {comparison?.available && (
                <span className={`pill ${
                  comparison.verdict === "PROMOTE_CHALLENGER" ? "pill-important"
                    : comparison.verdict === "KEEP_CHAMPION" ? "pill-info" : "pill-watch"
                }`}>
                  {comparison.verdict.replace(/_/g, " ")}
                </span>
              )}
            </div>

            <table className="research-table" style={{ marginTop: 10 }}>
              <thead>
                <tr>
                  <th>Domain</th><th className="num">Champion</th>
                  <th className="num">Challenger</th><th className="num">Δ</th><th>Action</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(proposal.current).map(([domain, current]: any) => {
                  const candidate = proposal.candidate[domain];
                  const delta = candidate - current;
                  const action = proposal.rationale[domain]?.action;
                  return (
                    <tr key={domain}>
                      <td>{domain}</td>
                      <td className="num">{current.toFixed(3)}</td>
                      <td className="num">{candidate.toFixed(3)}</td>
                      <td className={`num ${Math.abs(delta) < 0.005 ? "dim" : delta > 0 ? "pos" : "neg"}`}>
                        {delta >= 0 ? "+" : ""}{delta.toFixed(3)}
                      </td>
                      <td className="tiny dim">{action}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {comparison?.available ? (
              <>
                <div className="stat-grid" style={{ marginTop: 12 }}>
                  <div className="stat-box">
                    <div className="stat-label">OOS windows</div>
                    <div className="stat-value">{comparison.summary.windows}</div>
                  </div>
                  <div className="stat-box">
                    <div className="stat-label">Champion wins</div>
                    <div className="stat-value">{comparison.summary.champion_wins}</div>
                  </div>
                  <div className="stat-box">
                    <div className="stat-label">Challenger wins</div>
                    <div className="stat-value">{comparison.summary.challenger_wins}</div>
                  </div>
                  <div className="stat-box">
                    <div className="stat-label">Hit rate</div>
                    <div className="stat-value" style={{ fontSize: 13 }}>
                      {comparison.summary.champion_hit_rate}% vs {comparison.summary.challenger_hit_rate}%
                    </div>
                  </div>
                </div>
                <div className="small dim" style={{ marginTop: 8 }}>{comparison.reason}</div>
              </>
            ) : (
              <div className="unavailable tiny" style={{ marginTop: 10 }}>{comparison?.reason}</div>
            )}
          </div>
        );
      })}
    </>
  );
}

export function LivePerformanceSection() {
  const [data, setData] = useState<any>(null);
  const [integrity, setIntegrity] = useState<any>(null);

  useEffect(() => {
    api.researchLivePerformance().then(setData).catch(() => setData({ available: false }));
    api.snapshotsIntegrity().then(setIntegrity).catch(() => setIntegrity(null));
  }, []);

  if (!data) return <Loading what="live performance" />;

  return (
    <>
      <div className="warning-box">
        <strong>Live is not backtest.</strong> These are predictions the system actually
        made, evaluated after the fact. Backtest figures replay today's logic over old
        data and are not a track record.
      </div>

      <div className="panel section">
        <div className="panel-title">Live performance</div>
        {!data.available ? (
          <>
            <Unavailable reason={data.reason} />
            <div className="stat-grid" style={{ marginTop: 10 }}>
              <div className="stat-box">
                <div className="stat-label">Snapshots recorded</div>
                <div className="stat-value">{data.snapshots ?? 0}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Outcomes scored</div>
                <div className="stat-value">{data.outcomes ?? 0}</div>
              </div>
            </div>
          </>
        ) : (
          <table className="research-table">
            <thead>
              <tr>
                <th>Horizon</th><th className="num">n</th><th className="num">Directional</th>
                <th className="num">Accuracy</th><th className="num">Mean return</th><th>Reliable</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.by_horizon).map(([horizon, s]: any) => (
                <tr key={horizon}>
                  <td className="mono">{horizon}</td>
                  <td className="num dim">{s.n}</td>
                  <td className="num dim">{s.n_directional}</td>
                  <td className="num">{s.accuracy !== null ? `${s.accuracy}%` : "—"}</td>
                  <td className="num">{s.mean_return !== null ? `${s.mean_return}%` : "—"}</td>
                  <td className={s.reliable ? "pos" : "neg"}>
                    <span className="tiny">{s.reliable ? "yes" : "sample < 30"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {integrity && (
        <div className="panel">
          <div className="panel-title">Snapshot integrity</div>
          <div className={integrity.all_intact ? "pos small" : "neg small"}>
            {integrity.intact}/{integrity.total} recorded predictions verified unaltered
            {!integrity.all_intact && ` — ${integrity.tampered.length} MODIFIED`}
          </div>
          <div className="tiny faint" style={{ marginTop: 6 }}>
            Each prediction is hashed when written. If a payload were edited later, the hash
            would no longer match and the accuracy statistics would be worthless.
          </div>
        </div>
      )}
    </>
  );
}
