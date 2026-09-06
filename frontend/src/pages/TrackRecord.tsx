/**
 * Live track record: what the system actually said, before outcomes existed.
 *
 * Kept deliberately separate from backtest figures. A backtest replays today's
 * logic over old data and will always look better; conflating the two is how a
 * replay gets mistaken for a record. When there is no live data yet, the page
 * says so rather than showing backtest numbers in its place.
 */
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorBox, Loading } from "../components/common";

export default function TrackRecord() {
  const [drift, setDrift] = useState<any>(null);
  const [live, setLive] = useState<any>(null);
  const [patterns, setPatterns] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.researchDrift(),
      api.researchLivePerformance().catch(() => null),
      api.researchPatterns().catch(() => null),
    ])
      .then(([d, l, p]) => {
        setDrift(d);
        setLive(l);
        setPatterns(p);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!drift) return <Loading what="the live track record" />;

  return (
    <>
      <div className="panel section">
        <div className="panel-title">Live track record</div>
        {live && !live.available ? (
          <p className="muted">{live.reason}</p>
        ) : (
          <p className="muted">Live outcomes recorded: {live?.outcomes ?? 0}</p>
        )}
        <p className="muted small">
          These are predictions the system made before the outcome existed. Backtest
          figures elsewhere in this app are a replay of current logic over old data and
          are not a track record.
        </p>
      </div>

      <div className="panel section">
        <div className="panel-title">Shadow model and drift</div>
        <table className="table">
          <thead>
            <tr>
              <th>Asset</th><th>Recorded</th><th>Resolved</th><th>Scored</th><th>Drift</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(drift.assets ?? {}).map(([asset, value]: [string, any]) => (
              <tr key={asset}>
                <td>{asset}</td>
                <td>{value.drift?.predictions_total ?? 0}</td>
                <td>{value.drift?.predictions_resolved ?? 0}</td>
                <td>{value.drift?.predictions_scored ?? 0}</td>
                <td>{value.drift?.state}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {Object.entries(drift.assets ?? {}).map(([asset, value]: [string, any]) => (
          <p key={asset} className="muted small">
            <strong>{asset}:</strong> {value.drift?.note}
          </p>
        ))}
      </div>

      {patterns?.results && (
        <div className="panel section">
          <div className="panel-title">Pattern edge verdicts</div>
          <p className="muted small">{patterns.note}</p>
          {Object.entries(patterns.results).map(([key, res]: [string, any]) =>
            res.status !== "OK" ? null : (
              <div key={key}>
                <h4>{key}</h4>
                <p className="muted small">
                  {res.multiple_testing.hypotheses_tested} hypotheses,{" "}
                  {res.multiple_testing.raw_significant} raw,{" "}
                  {res.multiple_testing.survives_fdr} after FDR (
                  {res.multiple_testing.expected_false_positives} false positives expected)
                </p>
                <table className="table small">
                  <thead>
                    <tr>
                      <th>Pattern</th><th>Occurrences</th><th>Recognition</th>
                      <th>7d excess</th><th>Effective n</th><th>Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(res.patterns).map(([name, entry]: [string, any]) => {
                      const cell = entry.horizons?.["7d"] ?? {};
                      return (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>{entry.raw_occurrences}</td>
                          <td>{entry.mean_confidence ?? "—"}</td>
                          <td>
                            {cell.excess_vs_regime_baseline_pct === undefined
                              ? "—"
                              : `${cell.excess_vs_regime_baseline_pct > 0 ? "+" : ""}${cell.excess_vs_regime_baseline_pct}%`}
                          </td>
                          <td>{cell.effective_n ?? "—"}</td>
                          <td
                            className={
                              entry.verdict === "MEASURABLE_EDGE" ? "good" : "muted"
                            }
                          >
                            {entry.verdict}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          )}
        </div>
      )}
    </>
  );
}
