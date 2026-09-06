/**
 * Trader Knowledge: what sources claim, versus what the data shows.
 *
 * The confrontation is the point of this page. A source says a falling wedge
 * is bullish; the measured verdict sits directly beside it. Where they
 * disagree, both are shown - hiding the disagreement would defeat the purpose
 * of collecting the claim in the first place.
 */
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorBox, Loading } from "../components/common";

const VERDICT_CLASS: Record<string, string> = {
  SUPPORTED: "pill-good",
  PARTIALLY_SUPPORTED: "pill-info",
  NOT_SUPPORTED: "pill-warn",
  CONTRADICTED: "pill-bad",
  INSUFFICIENT_DATA: "pill-info",
  UNTESTABLE: "pill-info",
};

export default function TraderKnowledge() {
  const [claims, setClaims] = useState<any>(null);
  const [quality, setQuality] = useState<any>(null);
  const [queue, setQueue] = useState<any>(null);
  const [examples, setExamples] = useState<any>(null);
  const [agreement, setAgreement] = useState<any>(null);
  const [validation, setValidation] = useState<any>(null);
  const [hierarchy, setHierarchy] = useState<any>(null);
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.educationalClaims(),
      api.datasetQuality(),
      api.annotationQueue(10),
      api.humanExamples(),
      api.humanVsAlgorithm(),
      api.researchClaimValidation().catch(() => null),
      api.sourceHierarchy(),
    ])
      .then(([c, q, aq, ex, ag, v, h]) => {
        setClaims(c);
        setQuality(q);
        setQueue(aq);
        setExamples(ex);
        setAgreement(ag);
        setValidation(v);
        setHierarchy(h);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!claims) return <Loading what="trader knowledge" />;

  const sources: string[] = Array.from(
    new Set((claims.claims ?? []).map((c: any) => c.source))
  );
  const visible = (claims.claims ?? []).filter(
    (c: any) =>
      (sourceFilter === "all" || c.source === sourceFilter) &&
      c.claim_type === "EDUCATIONAL_CLAIM"
  );

  // Map concept -> measured verdict, so theory and data sit on one row.
  const verdicts: Record<string, any> = {};
  if (validation?.results) {
    for (const [assetName, assetResult] of Object.entries<any>(validation.results)) {
      for (const claim of assetResult.claims ?? []) {
        const key = `${claim.concept}|${assetName}`;
        verdicts[key] = claim;
      }
    }
  }

  return (
    <>
      <div className="panel section">
        <div className="panel-title">Source hierarchy</div>
        <p className="muted small">{hierarchy?.rule}</p>
        <table className="table small">
          <thead>
            <tr><th>Tier</th><th>Kind</th><th>Primary data?</th><th>Providers</th></tr>
          </thead>
          <tbody>
            {Object.entries<any>(hierarchy?.tiers ?? {}).map(([tier, info]) => (
              <tr key={tier}>
                <td>{tier}</td>
                <td>{info.label}</td>
                <td className={info.is_primary_data ? "good" : "muted"}>
                  {info.is_primary_data ? "yes" : "no — claims only"}
                </td>
                <td className="muted small">{info.providers.join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel section">
        <div className="panel-title">
          Theory versus data
          <span className="tabs">
            <button
              className={sourceFilter === "all" ? "tab tab-active" : "tab"}
              onClick={() => setSourceFilter("all")}
            >
              all
            </button>
            {sources.map((s) => (
              <button
                key={s}
                className={sourceFilter === s ? "tab tab-active" : "tab"}
                onClick={() => setSourceFilter(s)}
              >
                {s}
              </button>
            ))}
          </span>
        </div>
        <p className="muted small">{claims.note}</p>
        {!validation && (
          <p className="muted">
            Claim validation has not been run yet — run{" "}
            <code>crypto-intel research-claims</code> to fill the data column.
          </p>
        )}
        <table className="table">
          <thead>
            <tr>
              <th>Concept</th><th>What the source claims</th>
              <th>Implied direction</th><th>What the data shows</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((claim: any) => {
              const measured = ["BTC", "ETH", "SOL"]
                .map((a) => verdicts[`${claim.concept}|${a}`])
                .filter(Boolean);
              return (
                <tr key={claim.id}>
                  <td>{claim.concept.replace(/_/g, " ")}</td>
                  <td className="muted small">{claim.statement}</td>
                  <td>{claim.implied_direction ?? "—"}</td>
                  <td>
                    {measured.length === 0 ? (
                      <span className="muted small">not tested</span>
                    ) : (
                      measured.map((m: any, i: number) => (
                        <span
                          key={i}
                          className={`pill ${VERDICT_CLASS[m.verdict] ?? "pill-info"}`}
                          title={m.note}
                        >
                          {m.asset} {m.verdict.replace(/_/g, " ")}
                        </span>
                      ))
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="panel section">
        <div className="panel-title">Human example dataset</div>
        {quality?.status === "EMPTY" ? (
          <>
            <p className="muted">{quality.note}</p>
            <p className="muted small">Target: {quality.target}</p>
          </>
        ) : (
          <>
            <div className="stat-grid">
              <div className="stat-box">
                <div className="stat-label">Examples</div>
                <div className="stat-value">{quality?.number_examples}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Market episodes</div>
                <div className="stat-value">{quality?.market_episodes}</div>
                <div className="muted small">the real unit of evidence</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Effective sample</div>
                <div className="stat-value">{quality?.effective_sample_size}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Human verified</div>
                <div className="stat-value">{quality?.human_verified}</div>
              </div>
            </div>
            <p className="muted small">{quality?.note}</p>
            {(quality?.gaps ?? []).map((gap: string, i: number) => (
              <p key={i} className="pill pill-warn">{gap}</p>
            ))}
          </>
        )}
        <p className="muted small">
          Examples stored: {examples?.count ?? 0}. Human vs algorithm:{" "}
          {agreement?.status === "OK"
            ? `${agreement.agreement_rate_pct}% agreement on ${agreement.compared} examples`
            : agreement?.note}
        </p>
      </div>

      <div className="panel section">
        <div className="panel-title">Annotation queue (active learning)</div>
        <p className="muted small">{queue?.selection_rule}</p>
        <p className="muted small">{queue?.note}</p>
        <table className="table small">
          <thead>
            <tr>
              <th>Asset</th><th>TF</th><th>Date</th>
              <th>Detected</th><th>Confidence</th><th>Question</th>
            </tr>
          </thead>
          <tbody>
            {(queue?.queue ?? []).map((item: any, i: number) => (
              <tr key={i}>
                <td>{item.asset}</td>
                <td>{item.timeframe}</td>
                <td>{item.timestamp?.slice(0, 10)}</td>
                <td>{item.range_type?.replace(/_/g, " ")}</td>
                <td>{item.recognition_confidence}</td>
                <td className="muted small">{item.question}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
