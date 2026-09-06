/**
 * Research page - what the historical studies actually measured.
 *
 * Negative results are shown as prominently as positive ones. A signal that
 * does not work is the most valuable thing this page can tell you.
 */
import { useEffect, useState } from "react";
import { api, type EtfLagStudy, type EventStudyData } from "../lib/api";
import { ErrorBox, Loading, Unavailable } from "../components/common";
import {
  AsymmetrySection,
  AuditSection,
  ChampionChallengerSection,
  DerivativesSection,
  FeatureImportanceSection,
  LivePerformanceSection,
  RegimeSection,
} from "./ResearchSections";

const SECTIONS = [
  "Overview", "ETF", "Asymmetry", "Derivatives", "Regime",
  "Feature Importance", "Walk Forward", "Champion vs Challenger", "Live",
] as const;
type Section = (typeof SECTIONS)[number];

const HORIZONS = ["1d", "2d", "3d", "5d", "7d", "14d", "30d"];

export default function ResearchPage() {
  const [section, setSection] = useState<Section>("Overview");
  const [symbol, setSymbol] = useState("BTC");
  const [lag, setLag] = useState<EtfLagStudy | null>(null);
  const [events, setEvents] = useState<EventStudyData | null>(null);
  const [calibration, setCalibration] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLag(null);
    setEvents(null);
    Promise.all([
      api.researchEtf(symbol).catch(() => null),
      api.researchEvents(symbol).catch(() => null),
    ])
      .then(([l, e]) => {
        setLag(l);
        setEvents(e);
      })
      .catch((e) => setError(String(e)));
  }, [symbol]);

  useEffect(() => {
    api.researchCalibration().then(setCalibration).catch(() => setCalibration(null));
  }, []);

  if (error) return <ErrorBox error={error} />;

  // Sections that are computed per asset need the symbol selector; the audit
  // and champion/challenger views already cover every asset at once.
  const perAsset = !["Overview", "Champion vs Challenger", "Live"].includes(section);

  return (
    <>
      <div className="tabs">
        {SECTIONS.map((s) => (
          <button
            key={s}
            className={`tab ${section === s ? "active" : ""}`}
            onClick={() => setSection(s)}
          >
            {s}
          </button>
        ))}
      </div>

      {perAsset && (
        <div className="row" style={{ gap: 6, marginBottom: 14 }}>
          {["BTC", "ETH", "SOL"].map((s) => (
            <button
              key={s}
              className={`chip ${symbol === s ? "chip-on" : ""}`}
              onClick={() => setSymbol(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {section === "Overview" && <AuditSection />}
      {section === "Asymmetry" && <AsymmetrySection symbol={symbol} />}
      {section === "Derivatives" && <DerivativesSection symbol={symbol} />}
      {section === "Regime" && <RegimeSection symbol={symbol} />}
      {section === "Feature Importance" && <FeatureImportanceSection symbol={symbol} />}
      {section === "Walk Forward" && <FeatureImportanceSection symbol={symbol} />}
      {section === "Champion vs Challenger" && <ChampionChallengerSection />}
      {section === "Live" && <LivePerformanceSection />}

      {section === "ETF" && <EtfSection symbol={symbol} lag={lag} events={events} calibration={calibration} />}
    </>
  );
}

function EtfSection({
  symbol, lag, events, calibration,
}: {
  symbol: string;
  lag: EtfLagStudy | null;
  events: EventStudyData | null;
  calibration: any;
}) {
  return (
    <>

      <div className="panel section">
        <div className="panel-title">ETF flow → future price ({symbol})</div>
        {!lag ? (
          <Loading what="ETF study" />
        ) : !lag.available ? (
          <Unavailable reason={lag.reason} />
        ) : (
          <>
            <div className="small dim" style={{ marginBottom: 8 }}>
              {lag.period!.days} overlapping days ({lag.period!.start.slice(0, 10)} →{" "}
              {lag.period!.end.slice(0, 10)})
            </div>

            {lag.contemporaneous_control?.flow?.spearman_r != null && (
              <div className="warning-box">
                <strong>Same-day control: {lag.contemporaneous_control.flow.spearman_r.toFixed(3)}</strong>
                {" — "}
                flows correlate strongly with the <em>same day's</em> return. If the forward
                columns below are near zero, flows are following price rather than leading it.
              </div>
            )}

            {lag.multiple_testing && (
              <div className="small dim" style={{ marginBottom: 10 }}>
                {lag.multiple_testing.hypotheses} hypotheses tested ·{" "}
                {lag.multiple_testing.significant_raw} pass raw p&lt;0.05 ·{" "}
                {lag.multiple_testing.expected_false_positives_uncorrected} expected by chance ·{" "}
                <strong className={lag.multiple_testing.significant_after_fdr > 0 ? "pos" : "neg"}>
                  {lag.multiple_testing.significant_after_fdr} survive FDR correction
                </strong>
              </div>
            )}

            <table className="research-table">
              <thead>
                <tr>
                  <th>Signal</th>
                  {HORIZONS.map((h) => <th key={h} className="num">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {Object.entries(lag.correlations ?? {}).map(([signal, horizons]) => (
                  <tr key={signal}>
                    <td className="mono tiny">{signal}</td>
                    {HORIZONS.map((h) => {
                      const cell = horizons[h];
                      if (!cell || cell.spearman_r === null) {
                        return <td key={h} className="num insig">n/a</td>;
                      }
                      return (
                        <td key={h} className={`num ${cell.significant ? "sig" : "insig"}`}>
                          {cell.spearman_r >= 0 ? "+" : ""}
                          {cell.spearman_r.toFixed(3)}
                          {cell.significant ? "*" : ""}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="tiny faint" style={{ marginTop: 8 }}>
              * survives Benjamini-Hochberg correction. {lag.note}
            </div>
          </>
        )}
      </div>

      <div className="panel section">
        <div className="panel-title">Event studies ({symbol}) — 7-day forward return</div>
        {!events ? (
          <Loading what="event studies" />
        ) : !events.available ? (
          <Unavailable reason={(events as any).reason} />
        ) : (
          <table className="research-table">
            <thead>
              <tr>
                <th>Event</th>
                <th className="num">n</th>
                <th className="num">Mean</th>
                <th className="num">Baseline</th>
                <th className="num">Edge</th>
                <th className="num">Win</th>
                <th className="num">MFE</th>
                <th className="num">MAE</th>
              </tr>
            </thead>
            <tbody>
              {events.events
                .filter((e) => e.available && e.horizons?.["7d"])
                .sort(
                  (a, b) =>
                    (b.horizons!["7d"].edge_vs_baseline ?? 0) -
                    (a.horizons!["7d"].edge_vs_baseline ?? 0),
                )
                .map((e) => {
                  const h = e.horizons!["7d"];
                  const edge = h.edge_vs_baseline ?? 0;
                  return (
                    <tr key={e.event}>
                      <td>
                        <span className="tiny">{e.label ?? e.event}</span>
                        {!h.reliable_sample && (
                          <span className="pill pill-info" style={{ marginLeft: 6 }}>small n</span>
                        )}
                      </td>
                      <td className="num dim">{h.n}</td>
                      <td className="num">{h.mean?.toFixed(2)}%</td>
                      <td className="num dim">{h.baseline_mean?.toFixed(2)}%</td>
                      <td className={`num ${edge > 0 ? "pos" : edge < 0 ? "neg" : "dim"}`}>
                        {edge >= 0 ? "+" : ""}{edge.toFixed(2)}%
                      </td>
                      <td className="num dim">{h.win_rate?.toFixed(0)}%</td>
                      <td className="num pos tiny">+{h.max_favorable_excursion_mean?.toFixed(1)}%</td>
                      <td className="num neg tiny">{h.max_adverse_excursion_mean?.toFixed(1)}%</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        )}
        <div className="tiny faint" style={{ marginTop: 8 }}>
          Edge = event mean minus the unconditional mean over the same observable window.
          Thresholds use a trailing 252-day percentile, so "extreme" at each date only uses
          data available at that date.
        </div>
      </div>

      {calibration?.reconstructed && (
        <div className="panel section">
          <div className="panel-title">Score calibration — reconstructed logic</div>
          <table className="research-table">
            <thead>
              <tr>
                <th>Asset</th><th>Domain</th><th className="num">n</th>
                <th className="num">Spearman 7d</th><th className="num">p</th>
                <th>Monotonic</th><th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(calibration.reconstructed).flatMap(([asset, domains]: any) =>
                Object.entries(domains).map(([domain, r]: any) => {
                  if (!r.available) {
                    return (
                      <tr key={`${asset}-${domain}`}>
                        <td className="mono">{asset}</td>
                        <td>{domain}</td>
                        <td colSpan={5} className="unavailable tiny">{r.reason}</td>
                      </tr>
                    );
                  }
                  const c = r.correlations["7d"];
                  const mono = r.monotonicity_7d;
                  const useful = c.significant && mono?.monotonic;
                  return (
                    <tr key={`${asset}-${domain}`}>
                      <td className="mono">{asset}</td>
                      <td>{domain}</td>
                      <td className="num dim">{c.n}</td>
                      <td className={`num ${c.significant ? "sig" : "insig"}`}>
                        {c.spearman_r >= 0 ? "+" : ""}{c.spearman_r?.toFixed(3)}
                      </td>
                      <td className="num tiny dim">{c.p_value}</td>
                      <td className={mono?.monotonic ? "pos" : "neg"}>
                        {mono?.monotonic ? "yes" : "no"}
                      </td>
                      <td className={useful ? "pos small" : "neg small"}>
                        {useful ? "orders outcomes" : "no measurable value"}
                      </td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
          <div className="tiny faint" style={{ marginTop: 8 }}>
            Scores are reconstructed by replaying current logic over historical candles.
            This measures whether the logic has predictive value, not what the system would
            have said at the time. No weight is ever changed automatically.
          </div>
        </div>
      )}
    </>
  );
}
