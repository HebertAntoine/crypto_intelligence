/**
 * "Today" - the page that must be readable in ten seconds.
 *
 * Regime and entry timing are shown side by side on every card, because the
 * combination is the actual message: a bullish trend with poor timing is a
 * different instruction from a bullish trend with good timing.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AssetDetail, type CalendarData, type GlobalMarket, type TodayRead } from "../lib/api";
import { ErrorBox, Loading, fmtNumber, fmtSigned, signClass } from "../components/common";
import { KnowledgeState } from "../components/KnowledgeState";

export default function Today() {
  const [assets, setAssets] = useState<AssetDetail[] | null>(null);
  const [global, setGlobal] = useState<GlobalMarket | null>(null);
  const [calendar, setCalendar] = useState<CalendarData | null>(null);
  const [knowledge, setKnowledge] = useState<TodayRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      Promise.all(["BTC", "ETH", "SOL"].map((s) => api.asset(s))),
      api.global().catch(() => null),
      api.calendar(30).catch(() => null),
    ])
      .then(([a, g, c]) => {
        setAssets(a);
        setGlobal(g);
        setCalendar(c);
      })
      .catch((e) => setError(String(e)));

    // Loaded separately: the knowledge panel must still render if the
    // heavier per-asset analysis is unavailable.
    Promise.all(["BTC", "ETH", "SOL"].map((s) => api.today(s)))
      .then(setKnowledge)
      .catch(() => setKnowledge(null));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!assets) return <Loading what="today's market read" />;

  const nextEvent = calendar?.all_upcoming?.[0];

  return (
    <>
      {knowledge?.map((read) => (
        <KnowledgeState key={read.asset} read={read} />
      ))}

      <div className="panel section">
        <div className="panel-title">Global market</div>
        <div className="stat-grid">
          <div className="stat-box">
            <div className="stat-label">Risk regime</div>
            <div className="stat-value">{global?.risk_regime ?? "UNAVAILABLE"}</div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Avg conviction</div>
            <div className={`stat-value ${signClass(global?.average_conviction)}`}>
              {fmtSigned(global?.average_conviction, 1)}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Macro</div>
            <div className="stat-value" style={{ fontSize: 13 }}>
              {global?.macro?.available ? global.macro.risk_appetite : "UNAVAILABLE"}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Liquidity</div>
            <div className="stat-value" style={{ fontSize: 13 }}>
              {global?.liquidity?.available ? global.liquidity.regime : "UNAVAILABLE"}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Geopolitical</div>
            <div className="stat-value" style={{ fontSize: 13 }}>
              {global?.geopolitics?.available ? global.geopolitics.level : "UNAVAILABLE"}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-label">Next event</div>
            <div className="stat-value" style={{ fontSize: 12 }}>
              {nextEvent ? `${nextEvent.name} in ${nextEvent.hours_until.toFixed(0)}h` : "none"}
            </div>
          </div>
        </div>
      </div>

      <div className="grid-3">
        {assets.map((a) => (
          <TodayCard key={a.asset} data={a} />
        ))}
      </div>
    </>
  );
}

function TodayCard({ data }: { data: AssetDetail }) {
  const regime = data.regime;
  const timing = data.entry_timing;
  const conviction = data.conviction;
  const contradictions = data.contradictions?.contradictions ?? [];
  const catalysts = data.synthesis?.key_catalysts ?? [];
  const risks = timing?.risks ?? [];

  const nuance = nuanceLine(regime?.regime, timing?.timing);

  return (
    <Link to={`/asset/${data.asset}`} className="today-card">
      <div className="asset-card-head">
        <span className="asset-symbol">{data.asset}</span>
        <span className="asset-price">
          {fmtNumber(data.price, data.asset === "SOL" ? 2 : 0)}
        </span>
      </div>
      <div className={`asset-change ${signClass(data.change_24h_pct)}`} style={{ marginBottom: 10 }}>
        24h {fmtSigned(data.change_24h_pct, 2, "%")}
      </div>

      <div className="row" style={{ gap: 8, marginBottom: 8 }}>
        <span className={`regime-badge regime-${regime?.regime ?? "UNDETERMINED"}`}>
          {regime?.regime ?? "UNDETERMINED"}
        </span>
        <span className={`timing-badge timing-${timing?.timing ?? "UNDETERMINED"}`}>
          {timing?.timing ?? "UNDETERMINED"}
        </span>
      </div>
      {nuance && <div className="nuance">{nuance}</div>}

      <div className="conviction-row">
        <span className="conviction-label">Conviction short</span>
        <span className={`conviction-value ${signClass(conviction?.short?.score)}`}>
          {fmtSigned(conviction?.short?.score, 1)}
        </span>
      </div>
      <div className="conviction-row">
        <span className="conviction-label">Conviction medium</span>
        <span className={`conviction-value ${signClass(conviction?.medium?.score)}`}>
          {fmtSigned(conviction?.medium?.score, 1)}
        </span>
      </div>
      <div className="conviction-row">
        <span className="conviction-label">Confidence</span>
        <span className="conviction-value dim">
          {conviction?.overall_confidence?.toFixed(0) ?? "—"}%
        </span>
      </div>

      {timing?.positives?.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="tiny faint" style={{ marginBottom: 2 }}>SUPPORTIVE</div>
          <ul className="finding-list positive">
            {timing.positives.slice(0, 3).map((p, i) => (
              <li key={i} className="tiny">{p.split(" — ")[0]}</li>
            ))}
          </ul>
        </div>
      )}
      {timing?.negatives?.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="tiny faint" style={{ marginBottom: 2 }}>ADVERSE</div>
          <ul className="finding-list negative">
            {timing.negatives.slice(0, 3).map((n, i) => (
              <li key={i} className="tiny">{n.split(" — ")[0]}</li>
            ))}
          </ul>
        </div>
      )}

      {contradictions.length > 0 && (
        <div className="tiny" style={{ marginTop: 8, color: "var(--warn)" }}>
          ⚠ {contradictions[0].description.slice(0, 90)}
        </div>
      )}
      {risks.length > 0 && (
        <div className="tiny faint" style={{ marginTop: 6 }}>
          Risk: {risks[0].slice(0, 90)}
        </div>
      )}
      {catalysts.length > 0 && (
        <div className="tiny faint" style={{ marginTop: 6 }}>
          Next: {catalysts[0].slice(0, 90)}
        </div>
      )}
    </Link>
  );
}

function nuanceLine(regime?: string, timing?: string): string | null {
  if (!regime || !timing) return null;
  const bullish = regime === "BULLISH" || regime === "STRONGLY_BULLISH";
  const bearish = regime === "BEARISH" || regime === "STRONGLY_BEARISH";
  const poor = timing === "WAIT" || timing === "UNFAVORABLE" || timing === "VERY_UNFAVORABLE";
  const good = timing === "FAVORABLE" || timing === "VERY_FAVORABLE";

  if (bullish && poor) return "Trend favourable, immediate entry is not.";
  if (bullish && good) return "Trend and timing both constructive.";
  if (bearish && good) return "Trend adverse; short term looks stretched down.";
  if (bearish && poor) return "Trend and timing both cautious.";
  return null;
}
