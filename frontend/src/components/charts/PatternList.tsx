/**
 * The "patterns actifs" section.
 *
 * The rule this component exists to enforce: recognition confidence and
 * measured edge are shown together, always. A 91/100 recognition next to
 * NO_MEASURABLE_EDGE must read as one sentence - "we see this shape clearly,
 * and we cannot say what follows it" - because showing the 91 alone is exactly
 * how an analysis tool turns into a signal service.
 *
 * Cards are selectable so the chart can centre on a pattern (LOT 5) and the
 * history panel can look up its past occurrences (LOT 7).
 */
import { type PatternRead } from "../../lib/api";

const EDGE_CLASS: Record<string, string> = {
  POSITIVE_EDGE: "pill-good",
  NEGATIVE_EDGE: "pill-bad",
  NO_MEASURABLE_EDGE: "pill-warn",
  UNSTABLE: "pill-warn",
  INSUFFICIENT_DATA: "pill-info",
  NOT_YET_TESTED: "pill-info",
};

const EDGE_LABEL: Record<string, string> = {
  POSITIVE_EDGE: "avantage mesuré",
  NEGATIVE_EDGE: "avantage négatif",
  NO_MEASURABLE_EDGE: "aucun avantage mesurable",
  UNSTABLE: "instable",
  INSUFFICIENT_DATA: "données insuffisantes",
  NOT_YET_TESTED: "non encore testé",
};

const DIRECTION_LABEL: Record<string, string> = {
  BULLISH: "Haussier",
  BEARISH: "Baissier",
  NEUTRAL: "Neutre",
};

const DIRECTION_CLASS: Record<string, string> = {
  BULLISH: "pos",
  BEARISH: "neg",
  NEUTRAL: "neu",
};

const CLASS_HINT: Record<string, string> = {
  DETERMINISTIC: "géométrie entièrement spécifiée",
  HEURISTIC: "spécifiée, mais les seuils sont des choix",
  HUMAN_LIKE: "approche ce qu'un analyste trace",
  EXPERIMENTAL: "définition encore trop subjective pour être fiable",
};

function prettyName(name: string): string {
  return name.replace(/_/g, " ");
}

function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export default function PatternList({
  patterns,
  timeframe,
  selectedId,
  onSelect,
  separationNote,
}: {
  patterns: PatternRead[];
  timeframe: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  separationNote?: string;
}) {
  if (patterns.length === 0) {
    return (
      <div className="panel section">
        <div className="panel-title">Patterns actifs</div>
        <p className="muted">
          Aucune figure détectée sur ce timeframe. C'est le résultat normal la
          plupart du temps — un détecteur qui trouve toujours quelque chose ne
          trouve rien.
        </p>
      </div>
    );
  }

  return (
    <div className="panel section">
      <div className="panel-title">Patterns actifs ({patterns.length})</div>

      <div className="pattern-grid">
        {patterns.map((p) => {
          const id = `${p.name}-${p.detected_at}`;
          const open = selectedId === id;
          return (
            <article
              key={id}
              className={`pattern-card ${open ? "pattern-card-open" : ""}`}
            >
              <button
                className="pattern-head"
                onClick={() => onSelect(open ? null : id)}
                aria-expanded={open}
              >
                <span className="pattern-name">{prettyName(p.name)}</span>
                <span
                  className={`pattern-direction ${DIRECTION_CLASS[p.direction_if_textbook] ?? "neu"}`}
                >
                  {DIRECTION_LABEL[p.direction_if_textbook] ?? p.direction_if_textbook}
                </span>
                <span className="pattern-meta mono tiny">
                  reconnaissance {p.recognition_confidence.toFixed(0)}/100 · {timeframe}
                </span>
                <span className="pattern-pills">
                  <span className="pill pill-info">{p.state}</span>
                  <span className={`pill ${EDGE_CLASS[p.edge_state] ?? "pill-info"}`}>
                    {EDGE_LABEL[p.edge_state] ?? p.edge_state}
                  </span>
                </span>
              </button>

              {open && (
                <div className="pattern-body">
                  <p className="muted small">
                    <strong>{p.pattern_class}</strong> —{" "}
                    {CLASS_HINT[p.pattern_class] ?? ""}
                  </p>
                  <p className="muted small">{p.notes}</p>

                  <table className="table small">
                    <tbody>
                      <tr>
                        <td>Lecture théorique</td>
                        <td>
                          {DIRECTION_LABEL[p.direction_if_textbook] ??
                            p.direction_if_textbook}
                        </td>
                      </tr>
                      <tr>
                        <td>Avantage mesuré</td>
                        <td>{EDGE_LABEL[p.edge_state] ?? p.edge_state}</td>
                      </tr>
                      {Object.entries(p.key_levels).map(([key, value]) => (
                        <tr key={key}>
                          <td>{key.replace(/_/g, " ")}</td>
                          <td className="mono">{num(value, 2)}</td>
                        </tr>
                      ))}
                      <tr>
                        <td>Invalidation</td>
                        <td>{p.invalidation_rule || "—"}</td>
                      </tr>
                    </tbody>
                  </table>

                  {Object.keys(p.components ?? {}).length > 0 && (
                    <>
                      <div className="panel-title" style={{ marginTop: 12 }}>
                        Comment ce score est obtenu
                      </div>
                      <table className="table small">
                        <tbody>
                          {Object.entries(p.components).map(([key, value]) => (
                            <tr key={key}>
                              <td>{key.replace(/_/g, " ")}</td>
                              <td className="mono">
                                {typeof value === "number"
                                  ? num(value, 2)
                                  : String(value)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  )}

                  <p className="muted small separation">{p.separation_note}</p>
                </div>
              )}
            </article>
          );
        })}
      </div>

      {separationNote && (
        <p className="muted small separation">{separationNote}</p>
      )}
    </div>
  );
}
