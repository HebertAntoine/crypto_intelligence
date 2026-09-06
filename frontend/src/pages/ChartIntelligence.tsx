/**
 * Chart Intelligence: what the system sees in the chart, and what it has
 * actually verified about it.
 *
 * The layout enforces the LOT 5 rule everywhere: a pattern's recognition
 * confidence and its edge verdict sit side by side, never merged. A
 * 91/100 recognition with NO_MEASURABLE_EDGE must read as one coherent
 * statement - "we see this clearly, and we cannot say what follows" - rather
 * than as a strong signal.
 */
import { useEffect, useState } from "react";
import { api, type StructureRead, type PatternRead } from "../lib/api";
import { ErrorBox, Loading } from "../components/common";

const ASSETS = ["BTC", "ETH", "SOL"];
const TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"];

const EDGE_CLASS: Record<string, string> = {
  POSITIVE_EDGE: "pill-good",
  NEGATIVE_EDGE: "pill-bad",
  NO_MEASURABLE_EDGE: "pill-warn",
  UNSTABLE: "pill-warn",
  INSUFFICIENT_DATA: "pill-info",
  NOT_YET_TESTED: "pill-info",
};

const CLASS_HINT: Record<string, string> = {
  DETERMINISTIC: "geometry fully specified",
  HEURISTIC: "specified, but thresholds are choices",
  HUMAN_LIKE: "approximates what an analyst draws",
  EXPERIMENTAL: "definition still too subjective to trust",
};

function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function PatternCard({ pattern }: { pattern: PatternRead }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="pattern-card">
      <button className="pattern-head" onClick={() => setOpen(!open)}>
        <span className="pattern-name">{pattern.name.replace(/_/g, " ")}</span>
        <span className="pill pill-info">{pattern.state}</span>
        <span className="muted small">
          recognition {pattern.recognition_confidence.toFixed(0)}/100
        </span>
        <span className={`pill ${EDGE_CLASS[pattern.edge_state] ?? "pill-info"}`}>
          {pattern.edge_state.replace(/_/g, " ")}
        </span>
      </button>
      {open && (
        <div className="pattern-body">
          <p className="muted small">
            <strong>{pattern.pattern_class}</strong> —{" "}
            {CLASS_HINT[pattern.pattern_class] ?? ""}
          </p>
          <p className="muted small">{pattern.notes}</p>
          <table className="table small">
            <tbody>
              <tr>
                <td>Textbook reading</td>
                <td>{pattern.direction_if_textbook}</td>
              </tr>
              <tr>
                <td>Measured edge</td>
                <td>{pattern.edge_state.replace(/_/g, " ")}</td>
              </tr>
              {Object.entries(pattern.key_levels).map(([key, value]) => (
                <tr key={key}>
                  <td>{key.replace(/_/g, " ")}</td>
                  <td>{num(value, 4)}</td>
                </tr>
              ))}
              <tr>
                <td>Invalidation</td>
                <td>{pattern.invalidation_rule || "—"}</td>
              </tr>
            </tbody>
          </table>
          <p className="muted small separation">{pattern.separation_note}</p>
        </div>
      )}
    </div>
  );
}

export default function ChartIntelligence() {
  const [asset, setAsset] = useState("BTC");
  const [timeframe, setTimeframe] = useState("4h");
  const [data, setData] = useState<StructureRead | null>(null);
  const [opportunity, setOpportunity] = useState<any>(null);
  const [multi, setMulti] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState({
    range: true,
    swings: true,
    structure: true,
    patterns: true,
  });

  useEffect(() => {
    setData(null);
    Promise.all([
      api.structure(asset, timeframe),
      api.entryOpportunity(asset, timeframe).catch(() => null),
      api.structureMultiTimeframe(asset).catch(() => null),
    ])
      .then(([s, o, m]) => {
        setData(s);
        setOpportunity(o);
        setMulti(m);
      })
      .catch((e) => setError(String(e)));
  }, [asset, timeframe]);

  if (error) return <ErrorBox error={error} />;

  const range = data?.location.range;

  return (
    <>
      <div className="panel section">
        <div className="panel-title">
          Chart Intelligence
          <span className="tabs">
            {ASSETS.map((a) => (
              <button
                key={a}
                className={a === asset ? "tab tab-active" : "tab"}
                onClick={() => setAsset(a)}
              >
                {a}
              </button>
            ))}
          </span>
          <span className="tabs">
            {TIMEFRAMES.map((t) => (
              <button
                key={t}
                className={t === timeframe ? "tab tab-active" : "tab"}
                onClick={() => setTimeframe(t)}
              >
                {t}
              </button>
            ))}
          </span>
        </div>

        <div className="layer-toggles">
          {Object.keys(layers).map((key) => (
            <label key={key} className="layer-toggle">
              <input
                type="checkbox"
                checked={(layers as any)[key]}
                onChange={() =>
                  setLayers({ ...layers, [key]: !(layers as any)[key] })
                }
              />
              {key}
            </label>
          ))}
        </div>

        {!data ? (
          <Loading what={`${asset} ${timeframe} structure`} />
        ) : (
          <>
            <div className="stat-grid">
              <div className="stat-box">
                <div className="stat-label">Market structure</div>
                <div className="stat-value">
                  {data.market_structure.state.replace(/_/g, " ")}
                </div>
                <div className="muted small">
                  {data.market_structure.labels.join(" ") || "no labelled swings"}
                </div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Location</div>
                <div className="stat-value">
                  {data.location.state.replace(/_/g, " ")}
                </div>
                <div className="muted small">
                  position {num(data.location.relative_position)}
                </div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Entry opportunity</div>
                <div className="stat-value">{opportunity?.state ?? "…"}</div>
                <div className="muted small">
                  measured edge: {opportunity?.measured_edge_state ?? "…"}
                </div>
              </div>
            </div>

            <p className="invalidation-box">
              <strong>What would invalidate this:</strong>{" "}
              {data.location.invalidation || "no objective structural invalidation"}
            </p>
          </>
        )}
      </div>

      {layers.range && range && (
        <div className="panel section">
          <div className="panel-title">Range</div>
          {!range.valid ? (
            <p className="muted">{range.reason}</p>
          ) : (
            <>
              <p>{data?.location.range_summary}</p>
              <table className="table">
                <thead>
                  <tr>
                    <th>Zone</th><th>Band</th><th>Touches</th>
                    <th>Dispersion (ATR)</th><th>Closes through</th><th>Quality</th>
                  </tr>
                </thead>
                <tbody>
                  {[range.top_zone, range.bottom_zone].map((zone) =>
                    zone ? (
                      <tr key={zone.kind}>
                        <td>{zone.kind}</td>
                        <td>
                          {num(zone.low, 2)} – {num(zone.high, 2)}
                        </td>
                        <td>{zone.quality.touches}</td>
                        <td>{num(zone.quality.dispersion_atr)}</td>
                        <td>{zone.quality.close_penetrations}</td>
                        <td>{zone.quality.score.toFixed(0)}/100</td>
                      </tr>
                    ) : null
                  )}
                </tbody>
              </table>
              <h4>Why these are the boundaries</h4>
              <ul className="caveats">
                {(data?.location.explanation ?? []).map((line, i) => (
                  <li key={i} className="muted small">{line}</li>
                ))}
              </ul>
              {range.deviations.length > 0 && (
                <>
                  <h4>Deviations ({range.deviations.length})</h4>
                  <table className="table small">
                    <thead>
                      <tr>
                        <th>Direction</th><th>Started</th><th>Bars outside</th>
                        <th>Distance (ATR)</th><th>Closed outside</th><th>Reversed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {range.deviations.slice(0, 10).map((d: any, i: number) => (
                        <tr key={i}>
                          <td>{d.direction}</td>
                          <td>{d.started_at?.slice(0, 10)}</td>
                          <td>{d.bars_outside}</td>
                          <td>{num(d.max_distance_atr)}</td>
                          <td>{d.closed_outside ? "yes" : "no"}</td>
                          <td>{d.followed_through ? "yes" : "no"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted small">
                    Whether a deviation predicts a reversal is measured separately and
                    is not assumed here.
                  </p>
                </>
              )}
            </>
          )}
        </div>
      )}

      {layers.structure && data && (
        <div className="panel section">
          <div className="panel-title">Swing structure</div>
          <p>{data.market_structure.interpretation}</p>
          <table className="table small">
            <tbody>
              <tr><td>Last confirmed HH</td><td>{num(data.market_structure.last_confirmed_hh)}</td></tr>
              <tr><td>Last confirmed HL</td><td>{num(data.market_structure.last_confirmed_hl)}</td></tr>
              <tr><td>Last confirmed LH</td><td>{num(data.market_structure.last_confirmed_lh)}</td></tr>
              <tr><td>Last confirmed LL</td><td>{num(data.market_structure.last_confirmed_ll)}</td></tr>
            </tbody>
          </table>
          {data.market_structure.events.length > 0 && (
            <table className="table small">
              <thead>
                <tr><th>Event</th><th>Direction</th><th>Level</th><th>Confirmed at</th></tr>
              </thead>
              <tbody>
                {data.market_structure.events.map((e, i) => (
                  <tr key={i}>
                    <td>{e.kind}</td><td>{e.direction}</td>
                    <td>{num(e.level)}</td><td>{e.confirmation_time.slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small separation">{data.market_structure.caveat}</p>
        </div>
      )}

      {layers.patterns && data && (
        <div className="panel section">
          <div className="panel-title">Patterns ({data.patterns.length})</div>
          {data.patterns.length === 0 ? (
            <p className="muted">
              No pattern detected. This is the normal outcome most of the time.
            </p>
          ) : (
            data.patterns.map((p, i) => <PatternCard key={i} pattern={p} />)
          )}
          <p className="muted small separation">{data.separation_note}</p>
        </div>
      )}

      {multi && (
        <div className="panel section">
          <div className="panel-title">Across timeframes</div>
          <table className="table">
            <thead>
              <tr><th>Timeframe</th><th>Structure</th><th>Location</th><th>Position</th></tr>
            </thead>
            <tbody>
              {Object.entries(multi.location?.timeframes ?? {}).map(
                ([tf, loc]: [string, any]) => (
                  <tr key={tf}>
                    <td>{tf}</td>
                    <td>
                      {multi.market_structure?.timeframes?.[tf]?.state?.replace(
                        /_/g, " "
                      ) ?? "—"}
                    </td>
                    <td>{loc.state?.replace(/_/g, " ")}</td>
                    <td>{num(loc.relative_position)}</td>
                  </tr>
                )
              )}
            </tbody>
          </table>
          {multi.location?.conflict && (
            <p className="pill pill-warn">{multi.location.conflict}</p>
          )}
          {multi.market_structure?.conflict && (
            <p className="pill pill-warn">{multi.market_structure.conflict}</p>
          )}
        </div>
      )}
    </>
  );
}
