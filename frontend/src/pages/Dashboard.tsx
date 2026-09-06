import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AssetCard } from "../lib/api";
import { ErrorBox, Loading, Value, fmtSigned, signClass } from "../components/common";

export default function Dashboard() {
  const [cards, setCards] = useState<AssetCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.assets().then(setCards).catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!cards) return <Loading what="market analysis (first run collects from all sources)" />;

  return (
    <>
      <div className="grid-3">
        {cards.map((c) => (
          <AssetCardView key={c.asset} card={c} />
        ))}
      </div>
    </>
  );
}

function AssetCardView({ card }: { card: AssetCard }) {
  if (!card.available) {
    return (
      <div className="asset-card">
        <div className="asset-symbol">{card.asset}</div>
        <div className="unavailable" style={{ marginTop: 12 }}>
          UNAVAILABLE — {card.error}
        </div>
      </div>
    );
  }

  return (
    <Link to={`/asset/${card.asset}`} className="asset-card">
      <div className="asset-card-head">
        <span className="asset-symbol">{card.asset}</span>
        <span className="asset-price">
          <Value v={card.price} decimals={card.asset === "SOL" ? 2 : 0} />
        </span>
      </div>

      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className={`asset-change ${signClass(card.change_24h_pct)}`}>
          24h {fmtSigned(card.change_24h_pct, 2, "%")}
        </span>
        <span className={`asset-change ${signClass(card.change_7d_pct)}`}>
          7d {fmtSigned(card.change_7d_pct, 2, "%")}
        </span>
      </div>

      <div className="asset-regime">{card.market_regime}</div>

      <div className="conviction-row">
        <span className="conviction-label">Short term</span>
        <span className={`conviction-value ${signClass(card.conviction_short)}`}>
          {fmtSigned(card.conviction_short, 1)}
        </span>
      </div>
      <div className="conviction-row">
        <span className="conviction-label">Medium term</span>
        <span className={`conviction-value ${signClass(card.conviction_medium)}`}>
          {fmtSigned(card.conviction_medium, 1)}
        </span>
      </div>
      <div className="conviction-row">
        <span className="conviction-label">Long term</span>
        <span className={`conviction-value ${signClass(card.conviction_long)}`}>
          {fmtSigned(card.conviction_long, 1)}
        </span>
      </div>
      <div className="conviction-row">
        <span className="conviction-label">Confidence</span>
        <span className="conviction-value dim">{card.confidence?.toFixed(0)}%</span>
      </div>

      <div className="row tiny faint" style={{ marginTop: 10, justifyContent: "space-between" }}>
        <span>{card.label_medium}</span>
        <span>
          {card.domains_available}/10 domains
          {card.contradiction_strength && card.contradiction_strength >= 65 ? " · CONFLICTED" : ""}
        </span>
      </div>
      {card.generated_at && (
        <div className="tiny faint" style={{ marginTop: 4 }}>
          Last analysis {new Date(card.generated_at).toLocaleTimeString()}
        </div>
      )}
    </Link>
  );
}
