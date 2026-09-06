/**
 * Interactive candlestick chart with toggleable overlays, level lines,
 * event markers and indicator panels.
 *
 * Data comes from the backend's stored candles, so what is drawn is exactly
 * what the analysis used - the chart cannot disagree with the report.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { api, type ChartData } from "../lib/api";
import { ErrorBox, Loading, Unavailable } from "./common";

const TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"] as const;

const OVERLAY_OPTIONS = [
  { key: "ema20", label: "EMA 20", color: "#5b9bd5" },
  { key: "ema50", label: "EMA 50", color: "#d9a441" },
  { key: "ema200", label: "EMA 200", color: "#b06be0" },
  { key: "bb", label: "Bollinger", color: "#5c6672" },
] as const;

const PANEL_OPTIONS = [
  { key: "rsi", label: "RSI" },
  { key: "macd", label: "MACD" },
] as const;

function toTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

export default function PriceChart({ symbol }: { symbol: string }) {
  const [timeframe, setTimeframe] = useState<string>("1d");
  const [data, setData] = useState<ChartData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<Set<string>>(
    new Set(["ema20", "ema50", "ema200", "levels", "markers", "volume"]),
  );
  const [panel, setPanel] = useState<string>("rsi");

  const priceRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const panelChartRef = useRef<IChartApi | null>(null);

  const toggle = (key: string) => {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .chart(symbol, timeframe)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [symbol, timeframe]);

  const indicators = useMemo(() => (data ? data.overlays : {}), [data]);

  // --- price chart ---------------------------------------------------------
  useEffect(() => {
    if (!priceRef.current || !data?.available || !data.candles.length) return;

    const chart = createChart(priceRef.current, {
      layout: {
        background: { color: "#12151a" },
        textColor: "#98a1ae",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1c2129" },
        horzLines: { color: "#1c2129" },
      },
      rightPriceScale: { borderColor: "#232830" },
      timeScale: { borderColor: "#232830", timeVisible: timeframe !== "1d" && timeframe !== "1w" },
      crosshair: { mode: 0 },
      height: 420,
      autoSize: true,
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#35c88a",
      downColor: "#e2564d",
      borderUpColor: "#35c88a",
      borderDownColor: "#e2564d",
      wickUpColor: "#35c88a",
      wickDownColor: "#e2564d",
    });
    candleSeries.setData(
      data.candles.map((c) => ({
        time: toTime(c.time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    if (active.has("volume")) {
      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        color: "#2a3038",
      });
      volumeSeries.setData(
        data.candles.map((c) => ({
          time: toTime(c.time),
          value: c.volume,
          color: c.close >= c.open ? "rgba(53,200,138,0.35)" : "rgba(226,86,77,0.35)",
        })),
      );
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      });
    }

    const addLine = (values: (number | null)[], color: string, width: 1 | 2 = 1) => {
      const series = chart.addLineSeries({
        color,
        lineWidth: width,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      series.setData(
        data.candles
          .map((c, i) => ({ time: toTime(c.time), value: values[i] }))
          // null marks the indicator warm-up: skipping keeps the chart honest
          // instead of drawing a flat line at zero.
          .filter(
            (p): p is { time: UTCTimestamp; value: number } =>
              p.value !== null && p.value !== undefined,
          ),
      );
      return series;
    };

    for (const option of OVERLAY_OPTIONS) {
      if (option.key === "bb") {
        if (active.has("bb") && indicators.bb_upper) {
          addLine(indicators.bb_upper, "#3d4650");
          addLine(indicators.bb_lower, "#3d4650");
        }
        continue;
      }
      if (active.has(option.key) && indicators[option.key]) {
        addLine(indicators[option.key], option.color, option.key === "ema200" ? 2 : 1);
      }
    }

    if (active.has("levels")) {
      for (const level of data.levels.support.slice(0, 3)) {
        candleSeries.createPriceLine({
          price: level.price,
          color: "rgba(53,200,138,0.55)",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `S ${level.touches}x`,
        });
      }
      for (const level of data.levels.resistance.slice(0, 3)) {
        candleSeries.createPriceLine({
          price: level.price,
          color: "rgba(226,86,77,0.55)",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `R ${level.touches}x`,
        });
      }
    }

    if (active.has("markers") && data.markers.length) {
      const firstTime = toTime(data.candles[0].time);
      const lastTime = toTime(data.candles[data.candles.length - 1].time);
      const markers = data.markers
        .filter((m) => !m.upcoming)
        .map((m) => ({ ...m, t: toTime(m.time) }))
        .filter((m) => m.t >= firstTime && m.t <= lastTime)
        .sort((a, b) => a.t - b.t)
        .map((m) => ({
          time: m.t,
          position: (m.category === "ETF" ? "belowBar" : "aboveBar") as "belowBar" | "aboveBar",
          color:
            m.category === "ETF"
              ? m.direction === "in"
                ? "#35c88a"
                : "#e2564d"
              : m.importance === "CRITICAL"
                ? "#d9a441"
                : "#5b9bd5",
          shape: (m.category === "ETF" ? "circle" : "arrowDown") as "circle" | "arrowDown",
          text: m.category === "ETF" ? "ETF" : m.kind,
        }));
      if (markers.length) candleSeries.setMarkers(markers);
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data, active, indicators, timeframe]);

  // --- indicator panel ------------------------------------------------------
  useEffect(() => {
    if (!panelRef.current || !data?.available || !panel || !data.panels[panel]) return;

    const chart = createChart(panelRef.current, {
      layout: { background: { color: "#12151a" }, textColor: "#98a1ae", fontSize: 10 },
      grid: { vertLines: { color: "#1c2129" }, horzLines: { color: "#1c2129" } },
      rightPriceScale: { borderColor: "#232830" },
      timeScale: { borderColor: "#232830", visible: false },
      height: 130,
      autoSize: true,
    });
    panelChartRef.current = chart;

    const points = (values: (number | null)[]) =>
      data.candles
        .map((c, i) => ({ time: toTime(c.time), value: values[i] }))
        .filter(
          (p): p is { time: UTCTimestamp; value: number } =>
            p.value !== null && p.value !== undefined,
        );

    if (panel === "rsi") {
      const series = chart.addLineSeries({ color: "#5b9bd5", lineWidth: 1 });
      series.setData(points(data.panels.rsi));
      for (const [level, color] of [
        [70, "rgba(226,86,77,0.5)"],
        [30, "rgba(53,200,138,0.5)"],
      ] as const) {
        series.createPriceLine({
          price: level,
          color,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: String(level),
        });
      }
    } else if (panel === "macd") {
      const histogram = chart.addHistogramSeries({ color: "#3d4650" });
      histogram.setData(
        points(data.panels.macd_hist).map((p) => ({
          ...p,
          color: p.value >= 0 ? "rgba(53,200,138,0.6)" : "rgba(226,86,77,0.6)",
        })),
      );
      chart.addLineSeries({ color: "#5b9bd5", lineWidth: 1 }).setData(points(data.panels.macd));
      chart.addLineSeries({ color: "#d9a441", lineWidth: 1 }).setData(points(data.panels.macd_signal));
    }

    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      panelChartRef.current = null;
    };
  }, [data, panel]);

  if (error) return <ErrorBox error={error} />;

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div className="tabs" style={{ borderBottom: "none", marginBottom: 0 }}>
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              className={`tab ${timeframe === tf ? "active" : ""}`}
              onClick={() => setTimeframe(tf)}
            >
              {tf}
            </button>
          ))}
        </div>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {OVERLAY_OPTIONS.map((o) => (
            <button
              key={o.key}
              className={`chip ${active.has(o.key) ? "chip-on" : ""}`}
              onClick={() => toggle(o.key)}
              style={active.has(o.key) ? { borderColor: o.color, color: o.color } : undefined}
            >
              {o.label}
            </button>
          ))}
          {["volume", "levels", "markers"].map((key) => (
            <button
              key={key}
              className={`chip ${active.has(key) ? "chip-on" : ""}`}
              onClick={() => toggle(key)}
            >
              {key === "levels" ? "S/R" : key === "markers" ? "Events" : "Volume"}
            </button>
          ))}
        </div>
      </div>

      {loading && <Loading what="chart" />}
      {!loading && data && !data.available && <Unavailable reason={data.reason} />}

      <div ref={priceRef} style={{ width: "100%", height: 420 }} />

      {data?.available && (
        <>
          <div className="row" style={{ gap: 6, marginTop: 10 }}>
            {PANEL_OPTIONS.map((p) => (
              <button
                key={p.key}
                className={`chip ${panel === p.key ? "chip-on" : ""}`}
                onClick={() => setPanel(panel === p.key ? "" : p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div ref={panelRef} style={{ width: "100%", height: panel ? 130 : 0 }} />
        </>
      )}

      {data?.available && data.patterns.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="panel-title">Patterns detected on this timeframe</div>
          {data.patterns.map((p, i) => (
            <div key={i} className="small" style={{ marginBottom: 4 }}>
              <span className="pill">{p.state}</span>{" "}
              <strong>{p.pattern.replace(/_/g, " ")}</strong>{" "}
              <span className="mono tiny">{p.confidence.toFixed(0)}%</span>
              <div className="tiny faint">{p.notes}</div>
            </div>
          ))}
        </div>
      )}

      {data?.available && (
        <div className="tiny faint" style={{ marginTop: 10 }}>
          {data.candles.length} candles from the local history store. Indicator warm-up
          periods are drawn as gaps, never as zero.
        </div>
      )}
    </div>
  );
}
