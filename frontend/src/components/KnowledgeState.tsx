/**
 * "What do we actually know" - the LOT 4 panel.
 *
 * The layout enforces the distinction the whole system is built around:
 * direction sits on one side, measured edge on the other, and they are never
 * combined into a single number. A strongly bullish market showing
 * NO_MEASURABLE_EDGE is the normal case, not an error, so the panel is
 * designed to make that pairing look deliberate rather than broken.
 */
import type { TodayRead } from "../lib/api";
import { StructureBlock } from "./StructureBlock";

const EDGE_LABEL: Record<string, string> = {
  POSITIVE_EDGE: "Measured edge",
  NEGATIVE_EDGE: "Edge runs against the signal",
  NO_MEASURABLE_EDGE: "No measurable edge",
  INSUFFICIENT_DATA: "Not yet tested",
};

const EDGE_CLASS: Record<string, string> = {
  POSITIVE_EDGE: "pill-good",
  NEGATIVE_EDGE: "pill-bad",
  NO_MEASURABLE_EDGE: "pill-warn",
  INSUFFICIENT_DATA: "pill-info",
};

function directionClass(direction: string): string {
  if (direction.includes("BULLISH")) return "pill-good";
  if (direction.includes("BEARISH")) return "pill-bad";
  return "pill-info";
}

function uncertaintyClass(level: string): string {
  if (level === "LOW") return "pill-good";
  if (level === "MODERATE") return "pill-info";
  return "pill-warn";
}

export function KnowledgeState({ read }: { read: TodayRead }) {
  const { decision_summary: summary, edge, uncertainty, crowding, volatility } = read;

  return (
    <div className="panel section knowledge-state">
      <div className="panel-title">
        What do we actually know about {read.asset}?
      </div>

      <p className="knowledge-statement">{summary.statement}</p>

      <div className="knowledge-grid">
        <div className="knowledge-cell">
          <div className="stat-label">Market direction</div>
          <span className={`pill ${directionClass(summary.market_direction)}`}>
            {summary.market_direction.replace(/_/g, " ")}
          </span>
          <div className="muted small">
            held {summary.direction_confidence}% of the last 20 days
          </div>
        </div>

        <div className="knowledge-cell knowledge-divider">
          <div className="stat-label">Measured edge</div>
          <span className={`pill ${EDGE_CLASS[edge.state] ?? "pill-info"}`}>
            {EDGE_LABEL[edge.state] ?? edge.state}
          </span>
          <div className="muted small">
            {edge.admitted_count} admitted, {edge.rejected_count} rejected
          </div>
        </div>

        <div className="knowledge-cell">
          <div className="stat-label">Leverage / crowding</div>
          <span className="pill pill-info">{crowding.level}</span>
          <div className="muted small">
            direction {crowding.direction} — open interest has two sides
          </div>
        </div>

        <div className="knowledge-cell">
          <div className="stat-label">Volatility regime</div>
          <span className="pill pill-info">
            {volatility.regime.replace(/_/g, " ")}
          </span>
          <div className="muted small">{volatility.direction.toLowerCase()}</div>
        </div>

        <div className="knowledge-cell">
          <div className="stat-label">Uncertainty</div>
          <span className={`pill ${uncertaintyClass(uncertainty.level)}`}>
            {uncertainty.level.replace(/_/g, " ")} {uncertainty.score}/100
          </span>
          <div className="muted small">
            {uncertainty.drivers.slice(0, 2).map((d) => d.driver).join(", ")}
          </div>
        </div>
      </div>

      <StructureBlock asset={read.asset} />

      <details className="knowledge-details">
        <summary>
          Why the edge is {EDGE_LABEL[edge.state]?.toLowerCase() ?? edge.state}
        </summary>
        <p className="muted">{edge.statement}</p>
        {edge.evidence.length > 0 && (
          <table className="table small">
            <thead>
              <tr>
                <th>Signal</th>
                <th>Effect</th>
                <th>Effective n</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {edge.evidence.slice(0, 12).map((e, i) => (
                <tr key={i}>
                  <td>{e.signal}</td>
                  <td>
                    {e.effect_pct === null ? "—" : `${e.effect_pct > 0 ? "+" : ""}${e.effect_pct.toFixed(2)}%`}
                  </td>
                  <td>{e.effective_n ?? "—"}</td>
                  <td className={e.admitted ? "good" : "muted"}>
                    {e.admitted ? "admitted" : e.rejection_reason || "rejected"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted small">{read.direction_source}</p>
      </details>

      <ul className="caveats">
        {summary.caveats.map((c, i) => (
          <li key={i} className="muted small">{c}</li>
        ))}
      </ul>
    </div>
  );
}
