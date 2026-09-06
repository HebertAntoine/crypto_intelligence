/** The daily intelligence report, rendered as produced by the backend. */
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorBox, Loading } from "../components/common";

export default function DailyReportPage() {
  const [text, setText] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = () => {
    setRefreshing(true);
    api
      .dailyReport()
      .then((r) => {
        setText(r.text);
        setGeneratedAt(r.generated_at);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setRefreshing(false));
  };

  useEffect(load, []);

  if (error) return <ErrorBox error={error} />;
  if (!text) return <Loading what="daily report" />;

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div className="panel-title" style={{ margin: 0 }}>
          Daily intelligence report
          {generatedAt && (
            <span className="tiny faint" style={{ marginLeft: 10 }}>
              {new Date(generatedAt).toLocaleString()}
            </span>
          )}
        </div>
        <button className="refresh-btn" onClick={load} disabled={refreshing}>
          {refreshing ? "Regenerating…" : "Regenerate"}
        </button>
      </div>
      <pre className="report-text">{text}</pre>
    </div>
  );
}
