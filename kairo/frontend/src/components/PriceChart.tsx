import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type IPriceLine, type ISeriesApi, type UTCTimestamp, type SeriesMarker, type Time, LineStyle } from "lightweight-charts";
import type { NewsItem, PricePoint, Window } from "../types";

const nyTime = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
const nyDate = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
const BAR_SECONDS: Record<Window, number> = { "1d": 300, "5d": 1800, "1mo": 86400 };

// Same values as styles.css. Used when the stylesheet hasn't applied yet
// (Safari can run this before the CSS is ready, and the chart library
// crashes on an empty color).
const FALLBACK: Record<string, string> = {
  "--faint": "#626d82", "--muted": "#9aa4b6", "--grid": "#121926", "--line-2": "#273246",
  "--up": "#34d399", "--down": "#f87171", "--gold": "#f2b84b",
};

function css(name: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return /^#[0-9a-f]{6}$/i.test(v) ? v : FALLBACK[name];
}

interface Props {
  series: PricePoint[];
  news: NewsItem[];
  window: Window;
  up: boolean;
  highlighted: string[];
  reference: number | null; // previous close, drawn as a dotted line
  live: { price: number; t: number } | null;
}

/** Price chart with dots where company headlines landed, updated with live prices. */
export default function PriceChart({ series, news, window, up, highlighted, reference, live }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const area = useRef<ISeriesApi<"Area"> | null>(null);
  const lastTime = useRef(0);
  const refLine = useRef<IPriceLine | null>(null);

  useEffect(() => {
    if (!box.current) return;
    const c = createChart(box.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: css("--faint"), fontFamily: "Geist, Inter, system-ui, sans-serif", fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: css("--grid") } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
      timeScale: { borderVisible: false, timeVisible: true },
      crosshair: {
        horzLine: { labelBackgroundColor: css("--line-2"), color: css("--line-2") },
        vertLine: { labelBackgroundColor: css("--line-2"), color: css("--line-2") },
      },
      handleScroll: false,
      handleScale: false,
    });
    chart.current = c;
    area.current = c.addAreaSeries({ lineWidth: 2, priceLineVisible: false, lastPriceAnimation: 1 });
    return () => c.remove();
  }, []);

  useEffect(() => {
    const c = chart.current, s = area.current;
    if (!c || !s || !series.length) return;
    const fmt = (t: number) => (window === "1d" ? nyTime : nyDate).format(new Date(t * 1000));
    c.applyOptions({
      timeScale: { tickMarkFormatter: (t: Time) => fmt(t as number) },
      localization: { timeFormatter: (t: Time) => `${nyDate.format(new Date((t as number) * 1000))} ${nyTime.format(new Date((t as number) * 1000))} ET` },
    });
    const color = up ? css("--up") : css("--down");
    s.applyOptions({ lineColor: color, topColor: color + "40", bottomColor: color + "00" });

    const data = series.map((p) => ({ time: Math.floor(Date.parse(p.t) / 1000) as UTCTimestamp, value: p.price }));
    s.setData(data);
    lastTime.current = data[data.length - 1].time;

    if (refLine.current) s.removePriceLine(refLine.current);
    refLine.current = null;
    if (reference && window === "1d") {
      refLine.current = s.createPriceLine({ price: reference, color: css("--faint"), lineStyle: LineStyle.Dotted, lineWidth: 1,
                          axisLabelVisible: false, title: "prev close" });
    }

    // Snap each headline to the nearest bar so the dot sits on the line.
    const first = data[0].time, last = data[data.length - 1].time;
    const markers: SeriesMarker<Time>[] = news
      .filter((n) => n.bucket === "company" || highlighted.includes(n.id))
      .map((n) => ({ n, t: Math.floor(Date.parse(n.published_at) / 1000) }))
      .filter(({ t }) => t >= first && t <= last)
      .map(({ n, t }) => {
        const bar = data.reduce((a, b) => (Math.abs(b.time - t) < Math.abs(a.time - t) ? b : a));
        const hot = highlighted.includes(n.id);
        return { time: bar.time, position: "aboveBar" as const, shape: "circle" as const,
                 color: hot ? css("--gold") : css("--muted"), size: hot ? 1.5 : 0.7 };
      })
      .sort((a, b) => (a.time as number) - (b.time as number));
    s.setMarkers(markers);
    c.timeScale().fitContent();
  }, [series, news, window, up, highlighted, reference]);

  // Live price: extend or update the latest bar while the market trades.
  useEffect(() => {
    const s = area.current;
    if (!s || !live || window !== "1d") return;
    const bar = Math.floor(live.t / 1000 / BAR_SECONDS[window]) * BAR_SECONDS[window];
    if (bar < lastTime.current || bar - lastTime.current > 3600) return; // stale or a different session
    s.update({ time: bar as UTCTimestamp, value: live.price });
    lastTime.current = bar;
  }, [live, window]);

  return <div className="chart" ref={box} />;
}
