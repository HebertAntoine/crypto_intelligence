/**
 * Graphiques & Patterns - the technical analysis centre of the application.
 *
 * This page replaces the old "Chart Intelligence", which read a chart without
 * ever drawing one. The order of the blocks is the reading order the brief
 * asks for: chart first, then the figures found on it, then the structure
 * around them, then what the data can and cannot support.
 *
 * One request feeds the chart, one feeds the structural reading. Both are
 * driven by the same selection, so nothing on the page can be showing a
 * different asset or timeframe from anything else.
 */
import { useCallback, useEffect, useState } from "react";
import MarketSelector, { type Selection } from "../components/charts/MarketSelector";
import MainChart from "../components/charts/MainChart";
import PatternList from "../components/charts/PatternList";
import { ErrorBox, Loading } from "../components/common";
import { api, type ChartData, type StructureRead } from "../lib/api";

function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

const STRUCTURE_LABEL: Record<string, string> = {
  HH_HL: "sommets et creux ascendants",
  LH_LL: "sommets et creux descendants",
  MIXED: "structure mixte",
  RANGE: "range",
  UNDETERMINED: "indéterminée",
};

/** Range boundaries and how they were established. */
function RangePanel({ data }: { data: StructureRead }) {
  const range = data.location.range;
  if (!range) return null;

  return (
    <div className="panel section">
      <div className="panel-title">Range</div>
      {!range.valid ? (
        <p className="muted">{range.reason}</p>
      ) : (
        <>
          <p>{data.location.range_summary}</p>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Bande</th>
                  <th>Touches</th>
                  <th>Dispersion (ATR)</th>
                  <th>Clôtures traversantes</th>
                  <th>Qualité</th>
                </tr>
              </thead>
              <tbody>
                {[range.top_zone, range.bottom_zone].map((zone) =>
                  zone ? (
                    <tr key={zone.kind}>
                      <td>{zone.kind}</td>
                      <td className="mono">
                        {num(zone.low)} – {num(zone.high)}
                      </td>
                      <td className="mono">{zone.quality.touches}</td>
                      <td className="mono">{num(zone.quality.dispersion_atr)}</td>
                      <td className="mono">{zone.quality.close_penetrations}</td>
                      <td className="mono">{zone.quality.score.toFixed(0)}/100</td>
                    </tr>
                  ) : null,
                )}
              </tbody>
            </table>
          </div>
          {(data.location.explanation ?? []).length > 0 && (
            <>
              <div className="panel-title" style={{ marginTop: 14 }}>
                Pourquoi ces bornes
              </div>
              <ul className="caveats">
                {data.location.explanation.map((line, i) => (
                  <li key={i} className="muted small">
                    {line}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}

/** Swing structure: what the market has actually confirmed. */
function StructurePanel({ data }: { data: StructureRead }) {
  const ms = data.market_structure;
  return (
    <div className="panel section">
      <div className="panel-title">Structure de marché</div>
      <p>{ms.interpretation}</p>
      <div className="table-scroll">
        <table className="table small">
          <tbody>
            <tr>
              <td>Dernier sommet ascendant confirmé</td>
              <td className="mono">{num(ms.last_confirmed_hh)}</td>
            </tr>
            <tr>
              <td>Dernier creux ascendant confirmé</td>
              <td className="mono">{num(ms.last_confirmed_hl)}</td>
            </tr>
            <tr>
              <td>Dernier sommet descendant confirmé</td>
              <td className="mono">{num(ms.last_confirmed_lh)}</td>
            </tr>
            <tr>
              <td>Dernier creux descendant confirmé</td>
              <td className="mono">{num(ms.last_confirmed_ll)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {ms.events.length > 0 && (
        <div className="table-scroll" style={{ marginTop: 12 }}>
          <table className="table small">
            <thead>
              <tr>
                <th>Événement</th>
                <th>Direction</th>
                <th>Niveau</th>
                <th>Confirmé le</th>
              </tr>
            </thead>
            <tbody>
              {ms.events.map((e, i) => (
                <tr key={i}>
                  <td>{e.kind}</td>
                  <td>{e.direction}</td>
                  <td className="mono">{num(e.level)}</td>
                  <td className="mono">{e.confirmation_time.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small separation">{ms.caveat}</p>
    </div>
  );
}

export default function ChartsPatterns() {
  const [selection, setSelection] = useState<Selection>({
    asset: "BTC",
    timeframe: "4h",
    period: "3m",
  });
  const [chart, setChart] = useState<ChartData | null>(null);
  const [structure, setStructure] = useState<StructureRead | null>(null);
  const [chartLoading, setChartLoading] = useState(true);
  const [structureLoading, setStructureLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPattern, setSelectedPattern] = useState<string | null>(null);

  const { asset, timeframe, period } = selection;

  // The chart and the structural reading are fetched separately: the chart is
  // fast and should paint immediately, while the structural pass is heavier.
  // Waiting for both would make every selection change feel broken.
  useEffect(() => {
    let cancelled = false;
    setChartLoading(true);
    setError(null);
    api
      .chart(asset, timeframe, period)
      .then((d) => {
        if (!cancelled) setChart(d);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setChartLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [asset, timeframe, period]);

  useEffect(() => {
    let cancelled = false;
    setStructureLoading(true);
    setSelectedPattern(null);
    api
      .structure(asset, timeframe)
      .then((d) => {
        if (!cancelled) setStructure(d);
      })
      .catch(() => {
        if (!cancelled) setStructure(null);
      })
      .finally(() => {
        if (!cancelled) setStructureLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [asset, timeframe]);

  const handleSelection = useCallback((next: Selection) => setSelection(next), []);

  if (error) return <ErrorBox error={error} />;

  return (
    <>
      <div className="panel section">
        <div className="panel-title">Graphiques &amp; Patterns</div>
        <MarketSelector selection={selection} onChange={handleSelection} />
      </div>

      <MainChart data={chart} loading={chartLoading} timeframe={timeframe} />

      {structureLoading && (
        <div className="panel section">
          <Loading what={`la structure ${asset} ${timeframe}`} />
        </div>
      )}

      {!structureLoading && structure && (
        <>
          <PatternList
            patterns={structure.patterns}
            timeframe={timeframe}
            selectedId={selectedPattern}
            onSelect={setSelectedPattern}
            separationNote={structure.separation_note}
          />

          <div className="stat-grid">
            <div className="stat-box">
              <div className="stat-label">Structure</div>
              <div className="stat-value">
                {STRUCTURE_LABEL[structure.market_structure.state] ??
                  structure.market_structure.state.replace(/_/g, " ")}
              </div>
              <div className="muted small">
                {structure.market_structure.labels.join(" ") ||
                  "aucun swing étiqueté"}
              </div>
            </div>
            <div className="stat-box">
              <div className="stat-label">Localisation</div>
              <div className="stat-value">
                {structure.location.state.replace(/_/g, " ")}
              </div>
              <div className="muted small">
                position {num(structure.location.relative_position)}
              </div>
            </div>
          </div>

          <p className="invalidation-box">
            <strong>Ce qui invaliderait cette lecture : </strong>
            {structure.location.invalidation ||
              "aucune invalidation structurelle objective"}
          </p>

          <RangePanel data={structure} />
          <StructurePanel data={structure} />
        </>
      )}
    </>
  );
}
