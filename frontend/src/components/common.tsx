/** Small presentational primitives shared across pages. */
import { useEffect, useState } from "react";
import { api, type Evidence } from "../lib/api";

export function fmtNumber(v: number | null | undefined, decimals = 2, unit = ""): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "UNAVAILABLE";
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T${unit}`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B${unit}`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M${unit}`;
  return v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + unit;
}

export function fmtSigned(v: number | null | undefined, decimals = 2, unit = ""): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "UNAVAILABLE";
  return `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}${unit}`;
}

export function signClass(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "unavailable";
  if (v > 0.05) return "pos";
  if (v < -0.05) return "neg";
  return "neu";
}

/** Missing data is rendered as an explicit UNAVAILABLE, never as a zero. */
export function Value({ v, decimals = 2, unit = "", signed = false }: {
  v: number | null | undefined; decimals?: number; unit?: string; signed?: boolean;
}) {
  if (v === null || v === undefined || Number.isNaN(v)) {
    return <span className="unavailable">UNAVAILABLE</span>;
  }
  return (
    <span className={`mono ${signed ? signClass(v) : ""}`}>
      {signed ? fmtSigned(v, decimals, unit) : fmtNumber(v, decimals, unit)}
    </span>
  );
}

export function FreshnessBadge({ freshness }: { freshness: string }) {
  return <span className={`fresh fresh-${freshness}`}>{freshness.replace("_", " ")}</span>;
}

export function ImportancePill({ importance }: { importance: string }) {
  return <span className={`pill pill-${importance.toLowerCase()}`}>{importance}</span>;
}

export function LegalStatusPill({ status }: { status: string }) {
  return <span className={`pill legal-${status}`}>{status.replace(/_/g, " ")}</span>;
}

export function ScoreBar({ score, available }: { score: number; available: boolean }) {
  if (!available) return <div className="score-track" />;
  const pct = Math.min(Math.abs(score), 100) / 2;
  const color = score > 0 ? "var(--bull)" : score < 0 ? "var(--bear)" : "var(--neutral)";
  return (
    <div className="score-track">
      <div
        className="score-fill"
        style={{
          background: color,
          left: score >= 0 ? "50%" : `${50 - pct}%`,
          width: `${pct}%`,
        }}
      />
    </div>
  );
}

/**
 * "WHY?" - unrolls a conclusion back to the raw observations that produced it,
 * with source, value, timestamp and freshness for each one.
 */
export function WhyButton({ evidenceIds, label }: { evidenceIds: string[]; label: string }) {
  const [open, setOpen] = useState(false);
  const [evidence, setEvidence] = useState<Evidence[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || evidence) return;
    api
      .whyBatch(evidenceIds.slice(0, 40))
      .then(setEvidence)
      .catch((e) => setError(String(e)));
  }, [open, evidence, evidenceIds]);

  if (!evidenceIds.length) return null;

  return (
    <>
      <button className="why-trigger" onClick={() => setOpen(true)}>
        WHY?
      </button>
      {open && (
        <>
          <div className="drawer-backdrop" onClick={() => setOpen(false)} />
          <div className="drawer">
            <button className="drawer-close" onClick={() => setOpen(false)}>
              ×
            </button>
            <h3>Evidence — {label}</h3>
            <p className="faint small">
              Every conclusion in this tool traces back to observations with a source,
              a value and a timestamp. These are the facts behind this one.
            </p>
            {error && <div className="error-box">{error}</div>}
            {!evidence && !error && <div className="loading">Loading evidence…</div>}
            {evidence?.length === 0 && (
              <div className="unavailable">
                No stored observations for this conclusion (it may derive from computed
                values rather than directly from raw facts).
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
                    <a href={e.source_url} target="_blank" rel="noreferrer">
                      {e.source_url}
                    </a>
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

export function Unavailable({ reason }: { reason?: string | null }) {
  return (
    <div className="unavailable" style={{ padding: "12px 0" }}>
      UNAVAILABLE{reason ? ` — ${reason}` : ""}
    </div>
  );
}

export function Loading({ what = "data" }: { what?: string }) {
  return <div className="loading">Loading {what}…</div>;
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="error-box">Error: {error}</div>;
}
