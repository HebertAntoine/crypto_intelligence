import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorBox, Loading, fmtNumber, fmtSigned, signClass } from "../components/common";
import {
  api,
  calibratedScenarioProbability,
  orderedGlobalRiskHorizons,
  publicFutureScenarios,
  type AssetDetail,
  type DecisionHorizon,
  type FutureDecision,
  type FutureEventRead,
  type GlobalRiskRead,
  type GlobalRiskHorizonRead,
  type FutureScenarioRead,
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
  const [globalRisk, setGlobalRisk] = useState<GlobalRiskRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDecision(null);
    setTimeline(null);
    setGlobalRisk(null);
    setError(null);
    Promise.all([
      api.future(asset, horizon),
      api.futureTimeline(asset),
      api.asset(asset),
      api.globalRisk(asset),
    ])
      .then(([nextDecision, nextTimeline, nextMarket, nextGlobalRisk]) => {
        setDecision(nextDecision);
        setTimeline(nextTimeline);
        setMarket(nextMarket);
        setGlobalRisk(nextGlobalRisk);
      })
      .catch((reason) => setError(String(reason)));
  }, [asset, horizon]);

  const selectAsset = (next: string) => setParams({ asset: next });
  if (error) return <ErrorBox error={error} />;
  if (!decision || !timeline || !market || !globalRisk) {
    return <Loading what={`l'analyse ${asset}`} />;
  }

  const nextEvent = decision.next_major_event;
  const familyItems = Object.values(decision.families.items);
  const scenarios = publicFutureScenarios(decision.scenarios);
  const riskHorizons = orderedGlobalRiskHorizons(globalRisk.risk_horizons);

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
        <div className="future-section-head">
          <div className="panel-title">Risque global</div>
          <span className="tiny faint">Fenêtres disjointes · aucune probabilité de rendement</span>
        </div>
        <div className="global-risk-grid">
          {riskHorizons.map((item) => (
            <GlobalRiskCard key={item.horizon} risk={item} />
          ))}
        </div>
        {riskHorizons.length !== 3 && (
          <div className="unavailable">
            Contrat de risque incomplet : {riskHorizons.length}/3 horizon(s) reçu(s).
          </div>
        )}
        <div className="tiny faint global-risk-methodology">{globalRisk.methodology}</div>
      </section>

      <section className="panel section">
        <div className="panel-title">Scénarios</div>
        {scenarios.length !== 3 && (
          <div className="unavailable">
            Contrat de scénarios incomplet : {scenarios.length}/3 scénario(s) public(s) reçu(s).
          </div>
        )}
        <div className="scenario-grid">
          {scenarios.map((scenario) => <ScenarioCard key={scenario.id} scenario={scenario} />)}
        </div>
      </section>
    </>
  );
}

function GlobalRiskCard({ risk }: { risk: GlobalRiskHorizonRead }) {
  const limitations = risk.data_coverage.limitations;
  return (
    <article className={`global-risk-card global-risk-${risk.risk_level.toLowerCase()}`}>
      <div className="row">
        <strong>{riskHorizonLabel(risk.horizon)}</strong>
        <span className="pill">{riskLevelLabel(risk.risk_level)}</span>
      </div>
      <div className="tiny dim">
        {risk.data_coverage.usable_family_count}/5 familles utilisables
        {` · ${risk.data_coverage.authorized_event_count} événement(s) autorisé(s)`}
      </div>
      {risk.main_drivers.length > 0 ? (
        <ul className="finding-list neutral">
          {risk.main_drivers.slice(0, 3).map((driver) => <li key={driver}>{driver}</li>)}
        </ul>
      ) : (
        <div className="unavailable">Aucun facteur dominant sourcé dans cette fenêtre.</div>
      )}
      {risk.counter_signals.length > 0 && (
        <details className="future-details">
          <summary>Signaux contraires</summary>
          <ScenarioList title="Contradictions observées" items={risk.counter_signals} />
        </details>
      )}
      {limitations.length > 0 && (
        <div className="tiny faint">Limites : {limitations.join(" ")}</div>
      )}
      <div className="tiny faint">
        Évolution : {riskChangeLabel(risk.change_since_previous)}
      </div>
    </article>
  );
}

function riskHorizonLabel(value: GlobalRiskHorizonRead["horizon"]): string {
  return ({
    "1-7d": "1 à 7 jours",
    "8-30d": "8 à 30 jours",
    "31-90d": "31 à 90 jours",
  } as const)[value];
}

function riskLevelLabel(value: GlobalRiskHorizonRead["risk_level"]): string {
  return ({
    LOW: "FAIBLE",
    MODERATE: "MODÉRÉ",
    HIGH: "ÉLEVÉ",
    CRITICAL: "CRITIQUE",
    INDETERMINATE: "INDÉTERMINÉ",
  } as const)[value];
}

function riskChangeLabel(value: GlobalRiskHorizonRead["change_since_previous"]): string {
  return ({
    INCREASED: "en hausse",
    DECREASED: "en baisse",
    UNCHANGED: "inchangée",
    NOT_AVAILABLE: "comparaison précédente indisponible",
  } as const)[value];
}

function ScenarioCard({ scenario }: { scenario: FutureScenarioRead }) {
  const probability = calibratedScenarioProbability(scenario);
  const calibration = probability == null ? null : scenario.calibration_metadata;

  return (
    <article className="scenario-card">
      <strong>{scenarioName(scenario.id)}</strong>
      <p className="small">{scenario.hypothesis}</p>
      <div className="row small">
        <span>{directionLabel[scenario.directional_bias] ?? scenario.directional_bias}</span>
        <span>Mouvement {scenario.expected_movement}</span>
      </div>
      <div className="tiny faint">
        Horizon {scenario.horizon}
        {scenario.affected_assets.length > 0 && ` · Actifs ${scenario.affected_assets.join(", ")}`}
      </div>
      <div className="tiny faint">
        Probabilité : {probability == null
          ? "non quantifiée — aucun modèle calibré publié"
          : `${Math.round(probability * 100)} % · modèle calibré`}
      </div>
      <div className="tiny faint">
        Confiance d'analyse : {Math.round(scenario.confidence * 100)} %
      </div>

      <details className="future-details">
        <summary>Hypothèses, preuves et conditions</summary>
        <div className="future-detail-body">
          <ScenarioList title="Éléments déjà confirmés" items={scenario.confirmed_evidence} />
          <ScenarioList title="Chaîne d'événements" items={scenario.event_chain} />
          <ScenarioList title="Conditions observables" items={scenario.conditions} />
          <ScenarioList title="Signaux de confirmation" items={scenario.confirmation_signals} />
          <ScenarioList title="Signaux d'invalidation" items={scenario.invalidation_conditions} />
          <ScenarioList title="Incertitudes" items={scenario.uncertainties} />
          {scenario.prudence_note && <p className="small dim">Prudence : {scenario.prudence_note}</p>}
          {scenario.evidence_ids.length > 0 && (
            <div className="tiny faint">Preuves : {scenario.evidence_ids.join(" · ")}</div>
          )}
          {probability != null && (
            <div className="tiny faint">
              Source de probabilité : {scenario.probability_source ?? "non documentée"}
              {scenario.probability_observed_at
                ? ` · observée ${formatDate(scenario.probability_observed_at)}`
                : ""}
            </div>
          )}
          {calibration && (
            <div className="tiny faint">
              Calibration : {calibration.model_name} v{calibration.model_version}
              {` · ${calibration.calibration_method}`}
              {` · hors échantillon n=${calibration.out_of_sample_sample_size}`}
              {` · ${calibration.evaluation_metric} ${calibration.evaluation_score}`}
              {` · cible ${calibration.target_definition} (${calibration.target_horizon})`}
              {` · évaluée ${formatDate(calibration.evaluated_at)}`}
              {calibration.evidence_ids.length > 0
                ? ` · preuves ${calibration.evidence_ids.join(", ")}`
                : ""}
            </div>
          )}
        </div>
      </details>
    </article>
  );
}

function ScenarioList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <h4>{title}</h4>
      <ul className="finding-list neutral">
        {items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}
      </ul>
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
      base_case: "Scénario intermédiaire",
      bullish_case: "Scénario favorable",
      bearish_case: "Scénario défavorable",
    } as Record<string, string>
  )[value] ?? value;
}
