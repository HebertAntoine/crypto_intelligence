/**
 * ETF flows against price, with a selectable visual lag.
 *
 * The lag control exists so the eye can check whether flows move before price.
 * It is explicitly labelled as a visual aid: the measured relationship lives on
 * the Research page, where it is corrected for multiple comparisons and
 * validated out of sample. A visual lead proves nothing on its own.
 */
import { useEffect, useMemo, useState } from "react";
import { api, type EtfVsPrice as EtfVsPriceData } from "../lib/api";
import { ErrorBox, Loading, Unavailable } from "../components/common";

const LAGS = [0, 1, 3, 5, 7] as const;
const SERIES = [
  { key: "flow", label: "Daily" },
  { key: "ma3", label: "3-day avg" },
  { key: "ma5", label: "5-day avg" },
  { key: "ma7", label: "7-day avg" },
  { key: "cumulative", label: "30-day cumulative" },
] as const;

export default function EtfVsPricePanel({ symbol }: { symbol: string }) {
  const [data, setData] = useState<EtfVsPriceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lag, setLag] = useState(0);
  const [days, setDays] = useState(365);
  const [flowSeries, setFlowSeries] = useState<string>("ma7");

  useEffect(() => {
    setData(null);
    api
      .etfVsPrice(symbol, days, lag)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [symbol, days, lag]);

  const chart = useMemo(() => {
    if (!data?.available) return null;
    const flows = (data as any)[flowSeries] as (number | null)[];
    const prices = data.price;
    const valid = prices.filter((p): p is number => p !== null);
    if (!valid.length) return null;

    const priceMin = Math.min(...valid);
    const priceMax = Math.max(...valid);
    const flowValues = flows.filter((f): f is number => f !== null);
    const flowMax = flowValues.length ? Math.max(...flowValues.map(Math.abs)) : 1;

    return { flows, prices, priceMin, priceMax, flowMax };
  }, [data, flowSeries]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="ETF vs price" />;
  if (!data.available) return <div className="panel"><Unavailable reason={data.reason} /></div>;

  const W = 1000;
  const H_PRICE = 220;
  const H_FLOW = 130;

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div className="row" style={{ gap: 6 }}>
          <span className="tiny faint" style={{ marginRight: 4 }}>FLOW SERIES</span>
          {SERIES.map((s) => (
            <button
              key={s.key}
              className={`chip ${flowSeries === s.key ? "chip-on" : ""}`}
              onClick={() => setFlowSeries(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="row" style={{ gap: 6 }}>
          <span className="tiny faint" style={{ marginRight: 4 }}>VISUAL LAG</span>
          {LAGS.map((l) => (
            <button
              key={l}
              className={`chip ${lag === l ? "chip-on" : ""}`}
              onClick={() => setLag(l)}
            >
              {l === 0 ? "none" : `${l}d`}
            </button>
          ))}
        </div>
        <div className="row" style={{ gap: 6 }}>
          {[180, 365, 730].map((d) => (
            <button
              key={d}
              className={`chip ${days === d ? "chip-on" : ""}`}
              onClick={() => setDays(d)}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {chart && (
        <svg viewBox={`0 0 ${W} ${H_PRICE + H_FLOW + 20}`} style={{ width: "100%", height: 400 }}>
          {/* price */}
          <polyline
            fill="none"
            stroke="#e6e9ee"
            strokeWidth="1.5"
            points={chart.prices
              .map((p, i) => {
                if (p === null) return null;
                const x = (i / Math.max(1, chart.prices.length - 1)) * W;
                const y =
                  H_PRICE -
                  ((p - chart.priceMin) / Math.max(1e-9, chart.priceMax - chart.priceMin)) *
                    (H_PRICE - 20) -
                  10;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .filter(Boolean)
              .join(" ")}
          />
          <text x="4" y="12" fill="#66707e" fontSize="10" fontFamily="monospace">
            {symbol} price
          </text>

          {/* zero line for flows */}
          <line
            x1="0" y1={H_PRICE + 10 + H_FLOW / 2}
            x2={W} y2={H_PRICE + 10 + H_FLOW / 2}
            stroke="#2e353f" strokeWidth="1"
          />

          {/* flow bars */}
          {chart.flows.map((f, i) => {
            if (f === null) return null;
            const x = (i / Math.max(1, chart.flows.length - 1)) * W;
            const barWidth = Math.max(1, W / chart.flows.length - 0.5);
            const height = (Math.abs(f) / Math.max(1e-9, chart.flowMax)) * (H_FLOW / 2 - 6);
            const zeroY = H_PRICE + 10 + H_FLOW / 2;
            return (
              <rect
                key={i}
                x={x - barWidth / 2}
                y={f >= 0 ? zeroY - height : zeroY}
                width={barWidth}
                height={height}
                fill={f >= 0 ? "#35c88a" : "#e2564d"}
                opacity="0.8"
              >
                <title>
                  {data.dates[i]?.slice(0, 10)}: {f.toFixed(1)} M$
                </title>
              </rect>
            );
          })}
          <text x="4" y={H_PRICE + 24} fill="#66707e" fontSize="10" fontFamily="monospace">
            ETF {SERIES.find((s) => s.key === flowSeries)?.label} (M$)
            {lag > 0 ? ` — shifted forward ${lag}d` : ""}
          </text>
        </svg>
      )}

      <div className="row small" style={{ justifyContent: "space-between", marginTop: 8 }}>
        <span className="faint tiny">{data.dates[0]?.slice(0, 10)}</span>
        <span className="faint tiny">
          {data.dates[data.dates.length - 1]?.slice(0, 10)}
        </span>
      </div>

      {lag > 0 && (
        <div className="warning-box">
          Flows are drawn {lag} day{lag > 1 ? "s" : ""} later than they occurred, so an apparent
          match means flows moved first. This is a visual aid only — it does not establish
          causality. {data.caveat}
        </div>
      )}
      {lag === 0 && <div className="tiny faint" style={{ marginTop: 8 }}>{data.caveat}</div>}
    </div>
  );
}
