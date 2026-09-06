/** Knowledge base: what is indexed, and a live search over it. */
import { useEffect, useState } from "react";
import { api, type KnowledgeDocuments, type KnowledgeHit } from "../lib/api";
import { ErrorBox, Loading } from "../components/common";

export default function KnowledgePage() {
  const [data, setData] = useState<KnowledgeDocuments | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<KnowledgeHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  const load = () => {
    api.knowledgeDocuments().then(setData).catch((e) => setError(String(e)));
  };

  useEffect(load, []);

  const search = () => {
    if (query.trim().length < 2) return;
    setSearching(true);
    api
      .knowledgeSearch(query)
      .then(setHits)
      .catch((e) => setError(String(e)))
      .finally(() => setSearching(false));
  };

  const ingest = () => {
    setIngesting(true);
    fetch("/api/knowledge/ingest", { method: "POST" })
      .then((r) => r.json())
      .then(() => load())
      .catch((e) => setError(String(e)))
      .finally(() => setIngesting(false));
  };

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="knowledge base" />;

  return (
    <>
      <div className="panel section">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="panel-title">Indexed documents</div>
          <button className="refresh-btn" onClick={ingest} disabled={ingesting}>
            {ingesting ? "Ingesting…" : "Re-scan knowledge/"}
          </button>
        </div>
        <div className="stat-grid">
          <div className="stat-box">
            <div className="stat-label">Documents</div>
            <div className="stat-value">{data.stats.documents}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Passages</div>
            <div className="stat-value">{data.stats.chunks}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Full-text index</div>
            <div className="stat-value" style={{ fontSize: 13 }}>
              {data.stats.fts_available ? "available" : "unavailable"}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Categories</div>
            <div className="stat-value" style={{ fontSize: 13 }}>
              {Object.keys(data.stats.by_category).length}
            </div>
          </div>
        </div>

        {data.documents.length === 0 ? (
          <div className="unavailable" style={{ padding: "16px 0" }}>
            No document indexed yet. Drop TXT, MD or PDF files into{" "}
            <span className="mono">knowledge/</span> then run{" "}
            <span className="mono">make ingest</span> (or use the button above).
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Document</th><th>Category</th><th>Type</th>
                <th className="num">Pages</th><th className="num">Chunks</th><th>Indexed</th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map((d) => (
                <tr key={d.id}>
                  <td>{d.title}</td>
                  <td><span className="pill">{d.category}</span></td>
                  <td className="tiny dim">{d.file_type}</td>
                  <td className="num dim">{d.pages ?? "—"}</td>
                  <td className="num">{d.chunks}</td>
                  <td className="tiny faint">{new Date(d.ingested_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel section">
        <div className="panel-title">Search your notes</div>
        <div className="row" style={{ gap: 8 }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            placeholder="divergence RSI, funding, support resistance…"
            style={{
              flex: 1, background: "var(--bg)", border: "1px solid var(--border-strong)",
              color: "var(--text)", padding: "7px 10px", borderRadius: 4,
              fontFamily: "inherit", fontSize: 13,
            }}
          />
          <button className="refresh-btn" onClick={search} disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </button>
        </div>

        {hits && hits.length === 0 && (
          <div className="unavailable" style={{ marginTop: 12 }}>
            No passage matched. The index is lexical (BM25) — a synonym never written in
            your documents will not be found.
          </div>
        )}
        {hits?.map((h) => (
          <div key={h.chunk_id} className="evidence-item" style={{ marginTop: 10 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong className="small">{h.document_title}</strong>
              <span className="row" style={{ gap: 6 }}>
                <span className="pill">{h.category}</span>
                <span className="mono tiny faint">score {h.score.toFixed(2)}</span>
              </span>
            </div>
            <div className="small dim" style={{ marginTop: 6 }}>{h.text.slice(0, 600)}</div>
          </div>
        ))}
      </div>

      <div className="panel">
        <div className="panel-title">How this is used</div>
        <div className="small dim">
          Your documents are a source of <strong>knowledge</strong>, never of real-time data.
          They live in a separate table from market observations, so a price written in a PDF
          can never be presented as a market datapoint. During analysis, the data detects a
          condition (say an RSI divergence on ETH 4H), your notes explain what it means, and
          the passage used is cited in the report.
        </div>
      </div>
    </>
  );
}
