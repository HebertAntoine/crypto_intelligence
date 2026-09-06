/**
 * "WHY?" for a computed verdict (entry timing, market regime).
 *
 * Shows three layers, in order: which factors pushed the result and by how
 * much, the arithmetic that combined them, and the raw observations behind it.
 */
import { useEffect, useState } from "react";
import { api, type Evidence } from "../lib/api";
import { FreshnessBadge } from "./common";

interface Factor {
  name: string;
  value: string;
  contribution: number;
  weight: number;
  detail: string;
  favourable?: boolean;
}

export function WhyVerdict({
  title,
  verdict,
  score,
  confidence,
  factors,
  explanation,
  evidenceIds,
  missing,
}: {
  title: string;
  verdict: string;
  score: number;
  confidence: number;
  factors: Factor[];
  explanation?: string;
  evidenceIds: string[];
  missing?: string[];
}) {
  const [open, setOpen] = useState(false);
  const [evidence, setEvidence] = useState<Evidence[] | null>(null);
  const [showFormula, setShowFormula] = useState(false);

  useEffect(() => {
    if (!open || evidence || !evidenceIds.length) return;
    api.whyBatch(evidenceIds.slice(0, 40)).then(setEvidence).catch(() => setEvidence([]));
  }, [open, evidence, evidenceIds]);

  const positives = factors.filter((f) => f.contribution > 0 && f.weight > 0);
  const negatives = factors.filter((f) => f.contribution < 0 && f.weight > 0);

  return (
    <>
      <button className="why-trigger" onClick={() => setOpen(true)}>WHY?</button>
      {open && (
        <>
          <div className="drawer-backdrop" onClick={() => setOpen(false)} />
          <div className="drawer">
            <button className="drawer-close" onClick={() => setOpen(false)}>×</button>
            <h3>{title} = {verdict}</h3>
            <div className="small dim" style={{ marginBottom: 14 }}>
              Score {score >= 0 ? "+" : ""}{score.toFixed(1)} · confidence {confidence.toFixed(0)}%
            </div>

            {positives.length > 0 && (
              <>
                <div className="panel-title" style={{ marginTop: 14 }}>Positive factors</div>
                {positives
                  .sort((a, b) => b.contribution * b.weight - a.contribution * a.weight)
                  .map((f, i) => <FactorRow key={i} factor={f} />)}
              </>
            )}

            {negatives.length > 0 && (
              <>
                <div className="panel-title" style={{ marginTop: 14 }}>Negative factors</div>
                {negatives
                  .sort((a, b) => a.contribution * a.weight - b.contribution * b.weight)
                  .map((f, i) => <FactorRow key={i} factor={f} />)}
              </>
            )}

            {missing && missing.length > 0 && (
              <>
                <div className="panel-title" style={{ marginTop: 14 }}>Not available</div>
                <ul className="finding-list neutral">
                  {missing.map((m, i) => <li key={i} className="tiny unavailable">{m}</li>)}
                </ul>
              </>
            )}

            {explanation && (
              <>
                <div className="panel-title" style={{ marginTop: 16 }}>
                  Formula
                  <button
                    className="why-trigger"
                    onClick={() => setShowFormula(!showFormula)}
                    style={{ marginLeft: 8 }}
                  >
                    {showFormula ? "hide" : "show"}
                  </button>
                </div>
                {showFormula && <pre className="explanation">{explanation}</pre>}
              </>
            )}

            <div className="panel-title" style={{ marginTop: 16 }}>Data used</div>
            {!evidenceIds.length && (
              <div className="unavailable tiny">
                This verdict derives from computed indicators rather than directly from
                stored observations.
              </div>
            )}
            {evidence?.length === 0 && evidenceIds.length > 0 && (
              <div className="unavailable tiny">
                Evidence rows are no longer in the database (they may have been purged).
              </div>
            )}
            {evidence?.map((e) => (
              <div key={e.id} className="evidence-item">
                <div className="evidence-metric">
                  {e.metric} = {String(e.value)} {e.unit}
                </div>
                <div className="evidence-meta">
                  {e.source} · {e.provider} · {new Date(e.timestamp).toLocaleString()} ·{" "}
                  <FreshnessBadge freshness={e.freshness} />
                </div>
                {e.source_url && (
                  <div className="evidence-meta">
                    <a href={e.source_url} target="_blank" rel="noreferrer">{e.source_url}</a>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function FactorRow({ factor }: { factor: Factor }) {
  const magnitude = Math.min(Math.abs(factor.contribution), 100) / 2;
  const color = factor.contribution > 0 ? "var(--bull)" : "var(--bear)";
  return (
    <div style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="small">
          {factor.name}: <span className="mono">{factor.value}</span>
        </span>
        <span className="row" style={{ gap: 8 }}>
          <span className="mono tiny faint">w {factor.weight.toFixed(1)}</span>
          <span
            className="mono small"
            style={{ color, minWidth: 44, textAlign: "right" }}
          >
            {factor.contribution >= 0 ? "+" : ""}{factor.contribution.toFixed(0)}
          </span>
        </span>
      </div>
      <div className="factor-bar" style={{ marginTop: 4 }}>
        <div
          className="factor-fill"
          style={{
            background: color,
            left: factor.contribution >= 0 ? "50%" : `${50 - magnitude}%`,
            width: `${magnitude}%`,
          }}
        />
      </div>
      {factor.detail && <div className="tiny faint" style={{ marginTop: 3 }}>{factor.detail}</div>}
    </div>
  );
}
