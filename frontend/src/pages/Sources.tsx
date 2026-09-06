import { useEffect, useState } from "react";
import { api, type Evaluation, type KnowledgeStats, type ProvidersResponse } from "../lib/api";
import { ErrorBox, Loading } from "../components/common";

export default function SourcesPage() {
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [knowledge, setKnowledge] = useState<KnowledgeStats | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.providers(), api.knowledgeStats(), api.evaluation()])
      .then(([p, k, e]) => {
        setProviders(p);
        setKnowledge(k);
        setEvaluation(e);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!providers) return <Loading what="source status" />;

  const available = providers.providers.filter((p) => p.available);
  const unavailable = providers.providers.filter((p) => !p.available);

  return (
    <>
      <div className="panel section">
        <div className="panel-title">
          Providers — {available.length} available, {unavailable.length} not configured
          {providers.mock_mode && <span className="badge-mode" style={{ marginLeft: 10 }}>MOCK MODE</span>}
        </div>
        <table>
          <tbody>
            {available.map((p) => (
              <tr key={p.name}>
                <td className="pos" style={{ width: 40 }}>OK</td>
                <td className="mono">{p.name}</td>
                <td className="tiny faint">{p.reason}</td>
              </tr>
            ))}
            {unavailable.map((p) => (
              <tr key={p.name}>
                <td className="unavailable" style={{ width: 40 }}>—</td>
                <td className="mono dim">{p.name}</td>
                <td className="tiny unavailable">{p.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="tiny faint" style={{ marginTop: 12 }}>
          Providers without a key report UNAVAILABLE. No value is ever invented to fill the gap.
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-title">Knowledge base</div>
          {knowledge && (
            <>
              <div className="kv"><span>Documents</span><span>{knowledge.documents}</span></div>
              <div className="kv"><span>Indexed passages</span><span>{knowledge.chunks}</span></div>
              <div className="kv"><span>Full-text search</span><span>{knowledge.fts_available ? "available" : "unavailable"}</span></div>
              {Object.entries(knowledge.by_category).map(([c, n]) => (
                <div key={c} className="kv"><span className="tiny">{c}</span><span className="tiny">{n}</span></div>
              ))}
              <div className="tiny faint" style={{ marginTop: 10 }}>
                Drop TXT / MD / PDF files into knowledge/ then run <span className="mono">make ingest</span>.
                These are a source of knowledge, never of real-time data.
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">Self-evaluation</div>
          {evaluation && (
            <>
              <div className="kv"><span>Reports recorded</span><span>{evaluation.total_reports}</span></div>
              <div className="kv"><span>Outcomes evaluated</span><span>{evaluation.evaluated_outcomes}</span></div>
              {Object.entries(evaluation.direction_accuracy ?? {}).map(([h, acc]) => (
                <div key={h} className="kv">
                  <span className="tiny">Direction accuracy {h}</span>
                  <span className="tiny">
                    {acc === null ? "—" : `${acc.toFixed(1)}%`}
                    <span className="faint"> (n={evaluation.sample_sizes[h] ?? 0})</span>
                  </span>
                </div>
              ))}
              {evaluation.note && (
                <div className="tiny faint" style={{ marginTop: 10 }}>{evaluation.note}</div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
