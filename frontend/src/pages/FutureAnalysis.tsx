import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorBox, Loading, fmtNumber, fmtSigned, signClass } from "../components/common";
import {
  api,
  type AssetDetail,
  type DecisionHorizon,
  type FutureDecision,
  type FutureEventRead,
  type FutureTimeline,
} from "../lib/api";

const assets = ["BTC", "ETH", "SOL"] as const;
const horizons: DecisionHorizon[] = ["24h", "7d", "30d"];
const decisionLabel: Record<FutureDecision["decision"], string> = {
  BUY: "ACHETER",
  WAIT: "ATTENDRE",
  SELL: "VENDRE",
  INSUFFICIENT_DATA: "DONNÉES INSUFFISANTES",
};
const directionLabel: Record<string, string> = {
  STRONGLY_BULLISH: "FORTEMENT HAUSSIER",
  BULLISH: "HAUSSIER",
  NEUTRAL: "NEUTRE",
  BEARISH: "BAISSIER",
  STRONGLY_BEARISH: "FORTEMENT BAISSIER",
};

export default function FutureAnalysis() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("asset")?.toUpperCase();
  const asset = assets.includes(requested as (typeof assets)[number]) ? requested! : "BTC";
  const [horizon, setHorizon] = useState<DecisionHorizon>("7d");
  const [decision, setDecision] = useState<FutureDecision | null>(null);
  const [timeline, setTimeline] = useState<FutureTimeline | null>(null);
  const [market, setMarket] = useState<AssetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDecision(null);
    setTimeline(null);
    setError(null);
    Promise.all([api.future(asset, horizon), api.futureTimeline(asset), api.asset(asset)])
      .then(([nextDecision, nextTimeline, nextMarket]) => {
        setDecision(nextDecision);
        setTimeline(nextTimeline);
        setMarket(nextMarket);
      })
      .catch((reason) => setError(String(reason)));
  }, [asset, horizon]);

  const selectAsset = (next: string) => setParams({ asset: next });
  if (error) return <ErrorBox error={error} />;
  if (!decision || !timeline || !market) return <Loading what={`l'analyse ${asset}`} />;

  const nextEvent = decision.next_major_event;
  const familyItems = Object.values(decision.families.items);

  return (
    <>
      <section className="panel section future-selector">
        <div>
          <div className="panel-title">Analyse prospective</div>
          <div className="asset-tabs" aria-label="Choisir un actif">
            {assets.map((symbol) => (
              <button
                key={symbol}
                className={symbol === asset ? "asset-tab asset-tab-active" : "asset-tab"}
                onClick={() => selectAsset(symbol)}
              >
                {symbol}
              </button>
            ))}
          </div>
        </div>
        <div className="asset-live-price">
          <strong>{asset}</strong>
          <span>
            {market.price == null
              ? "INDISPONIBLE"
              : fmtNumber(market.price, asset === "SOL" ? 2 : 0)}
          </span>
          <span className={signClass(market.change_24h_pct)}>
            {fmtSigned(market.change_24h_pct, 2, "%")}
          </span>
        </div>
      </section>

      <section className={`panel section decision-hero decision-hero-${decision.decision}`}>
        <div className="panel-title">Est-ce le bon moment pour acheter ?</div>
        <div className="decision-word">{decisionLabel[decision.decision]}</div>
        <p className="decision-subtitle">
          {decision.reasons[0]?.explanation ?? "Aucune raison actuelle suffisamment sourcée."}
        </p>
        <div className="decision-metrics">
          <Metric label="Risque événementiel" value={decision.event_risk.level} />
          <Metric label="Horizon" value={horizon} />
          <Metric
            label="Biais"
            value={directionLabel[decision.directional_bias] ?? decision.directional_bias}
          />
          <Metric label="Volatilité attendue" value={decision.expected_movement} />
          <Metric
            label="Confiance d'analyse"
            value={`${Math.round(decision.decision_confidence * 100)} %`}
          />
        </div>
        <div className="horizon-tabs" aria-label="Choisir l'horizon">
          {horizons.map((item) => (
            <button
              key={item}
              className={item === horizon ? "asset-tab asset-tab-active" : "asset-tab"}
              onClick={() => setHorizon(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </section>

      <div className="grid-2 section">
        <section className="panel">
          <div className="panel-title">Prochain catalyseur</div>
          {nextEvent ? (
            <>
              <h3 className="future-event-title">{String(nextEvent.title)}</h3>
              <div className="row small dim">
                <span>{formatDate(String(nextEvent.scheduled_at))}</span>
                <span>{countdown(Number(nextEvent.hours_until) * 3600)}</span>
                <span className={`pill ${importanceClass(String(nextEvent.importance))}`}>
                  {String(nextEvent.importance)}
                </span>
              </div>
            </>
          ) : (
            <div className="unavailable">Aucun événement sourcé dans cet horizon.</div>
          )}
        </section>

        <section className="panel">
          <div className="panel-title">Pourquoi ?</div>
          <ul className="future-reason-list">
            {decision.reasons.slice(0, 3).map((reason, index) => (
              <li key={`${reason.title}-${index}`}>
                <strong>{reason.title}</strong>
                <span>{reason.explanation}</span>
              </li>
            ))}
          </ul>
          <details className="future-details">
            <summary>Pourquoi {decisionLabel[decision.decision].toLowerCase()} ?</summary>
            <div className="future-detail-body">
              {decision.reasons.map((reason, index) => (
                <article key={`${reason.title}-detail-${index}`} className="reason-detail">
                  <div className="row">
                    <strong>{reason.title}</strong>
                    {reason.impact && <span className="pill">Impact {reason.impact}</span>}
                  </div>
                  <p>{reason.explanation}</p>
                  <div className="tiny faint">
                    {reason.date_time ? formatDate(reason.date_time) : "Heure non applicable"}
                    {reason.source && (
                      <>
                        {" · "}
                        {reason.source_url ? (
                          <a href={reason.source_url}>{reason.source}</a>
                        ) : (
                          reason.source
                        )}
                      </>
                    )}
                  </div>
                </article>
              ))}
              <h4>Ce qui pourrait changer la décision</h4>
              <ul className="finding-list neutral">
                {decision.what_could_change_decision.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </details>
        </section>
      </div>

      <section className="panel section">
        <div className="future-section-head">
          <div className="panel-title">5 familles</div>
          <strong>{decision.families.coverage}</strong>
        </div>
        <div className="family-grid">
          {familyItems.map((family) => (
            <div
              key={family.family}
              className={`family-slot ${family.available ? "" : "family-unavailable"}`}
            >
              <div className="family-name">{family.label}</div>
              <div className="family-direction">
                {family.available
                  ? directionLabel[family.directional_bias ?? ""] ?? family.directional_bias
                  : "INDISPONIBLE"}
              </div>
              <div className="tiny dim">
                {family.available ? family.summary : family.unavailable_reason}
              </div>
              <div className="tiny faint">{family.freshness}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel section">
        <div className="panel-title">Ce qui arrive</div>
        {timeline.events.length ? (
          <div className="future-timeline">
            {timeline.events.map((event) => (
              <TimelineEvent key={event.id} event={event} />
            ))}
          </div>
        ) : (
          <div className="unavailable">Aucun événement sourcé dans les 30 prochains jours.</div>
        )}
      </section>

      <section className="panel section">
        <div className="panel-title">Scénarios</div>
        <div className="scenario-grid">
          {decision.scenarios.map((scenario) => (
            <article key={scenario.id} className="scenario-card">
              <strong>{scenarioName(scenario.id)}</strong>
              <div className="row small">
                <span>{directionLabel[scenario.directional_bias] ?? scenario.directional_bias}</span>
                <span>Mouvement {scenario.expected_movement}</span>
              </div>
              <p className="small dim">{scenario.event_chain.join(" → ")}</p>
              <div className="tiny faint">
                Probabilité : {scenario.probability == null
                  ? "non défendable avec les données disponibles"
                  : `${Math.round(scenario.probability * 100)} % · ${scenario.probability_source}`}
              </div>
              <div className="tiny faint">
                Confiance d'analyse : {Math.round(scenario.confidence * 100)} %
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TimelineEvent({ event }: { event: FutureEventRead }) {
  return (
    <article className="timeline-event">
      <time>{event.scheduled_at ? formatDate(event.scheduled_at) : "EN COURS"}</time>
      <div>
        <strong>{event.title}</strong>
        <div className="tiny dim">
          {event.countdown_seconds == null
            ? "Événement non planifié"
            : countdown(event.countdown_seconds)}
          {` · ${event.directional_bias} · amplitude ${event.expected_movement}`}
        </div>
        <div className="tiny faint">
          {event.source_url ? <a href={event.source_url}>{event.source}</a> : event.source}
          {` · ${event.freshness}`}
        </div>
      </div>
      <span className={`pill ${importanceClass(event.importance)}`}>{event.importance}</span>
    </article>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date indisponible"
    : new Intl.DateTimeFormat("fr-FR", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

function countdown(seconds: number): string {
  if (!Number.isFinite(seconds)) return "compte à rebours indisponible";
  const hours = Math.floor(Math.max(0, seconds) / 3600);
  if (hours < 48) return `dans ${hours} h`;
  return `dans ${Math.floor(hours / 24)} j`;
}

function importanceClass(value: string): string {
  if (value === "CRITICAL") return "pill-critical";
  if (value === "HIGH") return "pill-important";
  return "pill-watch";
}

function scenarioName(value: string): string {
  return (
    {
      base_case: "Scénario central",
      bullish_case: "Scénario haussier",
      bearish_case: "Scénario baissier",
      tail_risk_case: "Risque extrême",
    } as Record<string, string>
  )[value] ?? value;
}
