/** Market overview: price, 24h move, decision and event risk for BTC/ETH/SOL. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBox, Loading, fmtNumber, fmtSigned, signClass } from "../components/common";
import { api, type AssetDetail, type FutureDecision } from "../lib/api";

type MarketRead = { market: AssetDetail; future: FutureDecision };

const decisionLabel: Record<FutureDecision["decision"], string> = {
  BUY: "ACHETER",
  WAIT: "ATTENDRE",
  SELL: "VENDRE",
  INSUFFICIENT_DATA: "DONNÉES INSUFFISANTES",
};

export default function Today() {
  const [reads, setReads] = useState<MarketRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all(
      ["BTC", "ETH", "SOL"].map(async (symbol) => ({
        market: await api.asset(symbol),
        future: await api.future(symbol),
      })),
    )
      .then(setReads)
      .catch((reason) => setError(String(reason)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!reads) return <Loading what="la vue des marchés" />;

  return (
    <>
      <div className="page-heading section">
        <div>
          <div className="panel-title">Marchés</div>
          <h2>Ce qui arrive, actif par actif</h2>
          <p className="dim">Prix actuel, décision à 7 jours et risque événementiel.</p>
        </div>
      </div>
      <div className="grid-3">
        {reads.map(({ market, future }) => (
          <Link
            key={market.asset}
            to={`/analyse?asset=${market.asset}`}
            className="asset-card future-market-card"
          >
            <div className="asset-card-head">
              <span className="asset-symbol">{market.asset}</span>
              <span className="asset-price">
                {market.price == null
                  ? "INDISPONIBLE"
                  : fmtNumber(market.price, market.asset === "SOL" ? 2 : 0)}
              </span>
            </div>
            <div className={`asset-change ${signClass(market.change_24h_pct)}`}>
              24 h {fmtSigned(market.change_24h_pct, 2, "%")}
            </div>
            <div className={`future-decision future-decision-${future.decision}`}>
              {decisionLabel[future.decision]}
            </div>
            <div className="conviction-row">
              <span className="conviction-label">Risque événementiel</span>
              <span className="conviction-value">{future.event_risk.level}</span>
            </div>
            <div className="conviction-row">
              <span className="conviction-label">Mouvement attendu</span>
              <span className="conviction-value">{future.expected_movement}</span>
            </div>
            <div className="conviction-row">
              <span className="conviction-label">Couverture</span>
              <span className="conviction-value">{future.families.coverage}</span>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
