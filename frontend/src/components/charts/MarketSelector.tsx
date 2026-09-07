/**
 * Block A: what the whole page is looking at.
 *
 * One control surface for asset, timeframe and display period. Changing any of
 * the three refreshes every analysis below, so the selection lives in the page
 * and is passed down rather than being duplicated per panel - two panels
 * disagreeing about which timeframe is shown is the bug this prevents.
 */

export const ASSETS = ["BTC", "ETH", "SOL"] as const;

export const TIMEFRAMES = [
  { key: "15m", label: "15 min" },
  { key: "1h", label: "1 h" },
  { key: "4h", label: "4 h" },
  { key: "1d", label: "1 jour" },
  { key: "1w", label: "1 semaine" },
] as const;

export const PERIODS = [
  { key: "7d", label: "7 jours" },
  { key: "30d", label: "30 jours" },
  { key: "3m", label: "3 mois" },
  { key: "1y", label: "1 an" },
  { key: "max", label: "Maximum" },
] as const;

export type Selection = {
  asset: string;
  timeframe: string;
  period: string;
};

function Group({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly { key: string; label: string }[];
  onChange: (key: string) => void;
}) {
  return (
    <label className="selector-group">
      <span className="selector-label">{label}</span>
      <select
        className="selector-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function MarketSelector({
  selection,
  onChange,
  children,
}: {
  selection: Selection;
  onChange: (next: Selection) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="market-selector">
      <div className="selector-controls">
        <Group
          label="Actif"
          value={selection.asset}
          options={ASSETS.map((a) => ({ key: a, label: a }))}
          onChange={(asset) => onChange({ ...selection, asset })}
        />
        <Group
          label="Timeframe"
          value={selection.timeframe}
          options={TIMEFRAMES}
          onChange={(timeframe) => onChange({ ...selection, timeframe })}
        />
        <Group
          label="Période"
          value={selection.period}
          options={PERIODS}
          onChange={(period) => onChange({ ...selection, period })}
        />
      </div>
      {children && <div className="selector-extra">{children}</div>}
    </div>
  );
}
