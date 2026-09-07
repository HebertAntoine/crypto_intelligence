/**
 * The main candlestick chart.
 *
 * It renders data it is given and never fetches: the page owns the request, so
 * the chart, the pattern list and the confluence panel below are all reading
 * the same response rather than three that arrived at different moments.
 *
 * Overlays are declared in one table and toggled by key. Adding Bollinger
 * bands, a supertrend or a pattern's trend lines means adding an entry, not
 * editing the drawing code - which is what §3 asks for.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { type ChartData } from "../../lib/api";
import { Loading, Unavailable } from "../common";

export type OverlayKey =
  | "ema20"
  | "ema50"
  | "ema200"
  | "bb"
  | "volume"
  | "levels"
  | "markers";

type OverlaySpec = {
  key: OverlayKey;
  label: string;
  color?: string;
  /** Series in `data.overlays` this entry draws. Empty for non-line overlays. */
  series?: { field: string; color: string; width?: 1 | 2 }[];
};

const OVERLAYS: OverlaySpec[] = [
  {
    key: "ema20",
    label: "EMA 20",
    color: "#5b9bd5",
    series: [{ field: "ema20", color: "#5b9bd5" }],
  },
  {
    key: "ema50",
    label: "EMA 50",
    color: "#d9a441",
    series: [{ field: "ema50", color: "#d9a441" }],
  },
  {
    key: "ema200",
    label: "EMA 200",
    color: "#b06be0",
    series: [{ field: "ema200", color: "#b06be0", width: 2 }],
  },
  {
    key: "bb",
    label: "Bollinger",
    color: "#5c6672",
    series: [
      { field: "bb_upper", color: "#3d4650" },
      { field: "bb_lower", color: "#3d4650" },
    ],
  },
  { key: "volume", label: "Volume" },
  { key: "levels", label: "Supports / résistances" },
  { key: "markers", label: "Événements" },
];

const PANELS = [
  { key: "rsi", label: "RSI" },
  { key: "macd", label: "MACD" },
] as const;

const DEFAULT_OVERLAYS: OverlayKey[] = [
  "ema20",
  "ema50",
  "ema200",
  "volume",
  "levels",
];

function toTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v >= 1000 ? v.toLocaleString("fr-FR", { maximumFractionDigits: 0 })
    : v.toLocaleString("fr-FR", { maximumFractionDigits: 4 });
}

/** Price, move over the period, and the period's real extremes. */
function ChartHeader({ data }: { data: ChartData }) {
  const s = data.summary;
  if (!s?.available) return null;
  const up = (s.change_pct ?? 0) >= 0;
  return (
    <div className="chart-header">
      <div className="chart-price">
        <span className="chart-price-value">{fmtPrice(s.last_price)}</span>
        <span className={`chart-price-change ${up ? "pos" : "neg"}`}>
          {up ? "+" : ""}
          {s.change_pct?.toFixed(2)} %
        </span>
      </div>
      <div className="chart-extremes">
        <span>
          <span className="faint tiny">Haut </span>
          <span className="mono">{fmtPrice(s.period_high)}</span>
        </span>
        <span>
          <span className="faint tiny">Bas </span>
          <span className="mono">{fmtPrice(s.period_low)}</span>
        </span>
        <span className="faint tiny">{s.bars} bougies</span>
        {s.downsampled && (
          <span className="pill pill-info" title={s.note}>
            agrégé {s.downsample_factor}:1
          </span>
        )}
        {s.truncated && (
          <span className="pill pill-warn">historique plus court que la période</span>
        )}
      </div>
    </div>
  );
}

/** OHLC readout that follows the crosshair. */
function Readout({ bar }: { bar: ChartData["candles"][number] | null }) {
  if (!bar) return <div className="chart-readout faint tiny">Survolez le graphique</div>;
  const up = bar.close >= bar.open;
  return (
    <div className={`chart-readout mono tiny ${up ? "pos" : "neg"}`}>
      <span>O {fmtPrice(bar.open)}</span>
      <span>H {fmtPrice(bar.high)}</span>
      <span>L {fmtPrice(bar.low)}</span>
      <span>C {fmtPrice(bar.close)}</span>
      <span className="faint">
        {new Date(bar.time).toLocaleString("fr-FR", {
          dateStyle: "short",
          timeStyle: "short",
        })}
      </span>
    </div>
  );
}

export default function MainChart({
  data,
  loading,
  timeframe,
  height = 440,
}: {
  data: ChartData | null;
  loading: boolean;
  timeframe: string;
  height?: number;
}) {
  const [active, setActive] = useState<Set<string>>(new Set(DEFAULT_OVERLAYS));
  const [panel, setPanel] = useState<string>("rsi");
  const [hovered, setHovered] = useState<ChartData["candles"][number] | null>(null);

  const priceRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const toggle = (key: string) =>
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const byTime = useMemo(() => {
    const map = new Map<number, ChartData["candles"][number]>();
    for (const c of data?.candles ?? []) map.set(toTime(c.time), c);
    return map;
  }, [data]);

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
      timeScale: {
        borderColor: "#232830",
        timeVisible: timeframe !== "1d" && timeframe !== "1w",
        rightOffset: 4,
      },
      // Magnet mode snaps the crosshair to OHLC values, so the readout shows a
      // price that exists rather than wherever the pointer happens to sit.
      crosshair: { mode: 1 },
      handleScroll: true,
      handleScale: true,
      height,
      autoSize: true,
    });
    chartRef.current = chart;

    const candleSeries: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
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
      const volume = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        color: "#2a3038",
      });
      volume.setData(
        data.candles.map((c) => ({
          time: toTime(c.time),
          value: c.volume,
          color:
            c.close >= c.open ? "rgba(53,200,138,0.30)" : "rgba(226,86,77,0.30)",
        })),
      );
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.84, bottom: 0 },
      });
    }

    const addLine = (
      values: (number | null)[],
      color: string,
      width: 1 | 2 = 1,
    ) => {
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
          // A gap during indicator warm-up is honest; a flat line at zero is not.
          .filter(
            (p): p is { time: UTCTimestamp; value: number } =>
              p.value !== null && p.value !== undefined,
          ),
      );
      return series;
    };

    for (const overlay of OVERLAYS) {
      if (!overlay.series || !active.has(overlay.key)) continue;
      for (const line of overlay.series) {
        const values = data.overlays[line.field];
        if (values) addLine(values, line.color, line.width ?? 1);
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
          title: `S ${level.touches}×`,
        });
      }
      for (const level of data.levels.resistance.slice(0, 3)) {
        candleSeries.createPriceLine({
          price: level.price,
          color: "rgba(226,86,77,0.55)",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `R ${level.touches}×`,
        });
      }
    }

    if (active.has("markers") && data.markers.length) {
      const first = toTime(data.candles[0].time);
      const last = toTime(data.candles[data.candles.length - 1].time);
      const markers = data.markers
        .filter((m) => !m.upcoming)
        .map((m) => ({ ...m, t: toTime(m.time) }))
        .filter((m) => m.t >= first && m.t <= last)
        .sort((a, b) => a.t - b.t)
        .map((m) => ({
          time: m.t,
          position: (m.category === "ETF" ? "belowBar" : "aboveBar") as
            | "belowBar"
            | "aboveBar",
          color:
            m.category === "ETF"
              ? m.direction === "in"
                ? "#35c88a"
                : "#e2564d"
              : m.importance === "CRITICAL"
                ? "#d9a441"
                : "#5b9bd5",
          shape: (m.category === "ETF" ? "circle" : "arrowDown") as
            | "circle"
            | "arrowDown",
          text: m.category === "ETF" ? "ETF" : m.kind,
        }));
      if (markers.length) candleSeries.setMarkers(markers);
    }

    const onMove = (param: { time?: unknown }) => {
      const t = param.time as number | undefined;
      setHovered(t === undefined ? null : (byTime.get(t) ?? null));
    };
    chart.subscribeCrosshairMove(onMove);
    chart.timeScale().fitContent();

    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
    };
  }, [data, active, timeframe, height, byTime]);

  // --- indicator panel ------------------------------------------------------
  useEffect(() => {
    if (!panelRef.current || !data?.available || !panel || !data.panels[panel])
      return;

    const chart = createChart(panelRef.current, {
      layout: {
        background: { color: "#12151a" },
        textColor: "#98a1ae",
        fontSize: 10,
      },
      grid: { vertLines: { color: "#1c2129" }, horzLines: { color: "#1c2129" } },
      rightPriceScale: { borderColor: "#232830" },
      timeScale: { borderColor: "#232830", visible: false },
      crosshair: { mode: 1 },
      height: 130,
      autoSize: true,
    });

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
      chart
        .addLineSeries({ color: "#5b9bd5", lineWidth: 1 })
        .setData(points(data.panels.macd));
      chart
        .addLineSeries({ color: "#d9a441", lineWidth: 1 })
        .setData(points(data.panels.macd_signal));
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, panel]);

  return (
    <div className="panel chart-panel">
      {data?.available && <ChartHeader data={data} />}

      <div className="chart-toolbar">
        {OVERLAYS.map((o) => (
          <button
            key={o.key}
            className={`chip ${active.has(o.key) ? "chip-on" : ""}`}
            onClick={() => toggle(o.key)}
            style={
              active.has(o.key) && o.color
                ? { borderColor: o.color, color: o.color }
                : undefined
            }
          >
            {o.label}
          </button>
        ))}
      </div>

      {loading && <Loading what="le graphique" />}
      {!loading && data && !data.available && <Unavailable reason={data.reason} />}

      <Readout bar={hovered} />
      <div
        ref={priceRef}
        className="chart-canvas"
        style={{ width: "100%", height }}
      />

      {data?.available && (
        <>
          <div className="chart-toolbar chart-toolbar-panels">
            {PANELS.map((p) => (
              <button
                key={p.key}
                className={`chip ${panel === p.key ? "chip-on" : ""}`}
                onClick={() => setPanel(panel === p.key ? "" : p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div
            ref={panelRef}
            style={{ width: "100%", height: panel ? 130 : 0 }}
          />
        </>
      )}
    </div>
  );
}
