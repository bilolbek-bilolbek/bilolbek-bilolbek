import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi, type UTCTimestamp, type SeriesMarker, type Time } from "lightweight-charts";
import type { NewsItem, PricePoint, Window } from "../types";

const nyTime = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
const nyDate = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });

function css(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

interface Props {
  series: PricePoint[];
  news: NewsItem[];
  window: Window;
  up: boolean;
  highlighted: string[];
}

/** Price chart with a dot on the chart wherever a company headline landed. */
export default function PriceChart({ series, news, window, up, highlighted }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const area = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!box.current) return;
    const c = createChart(box.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: css("--muted"), fontFamily: "Inter, sans-serif" },
      grid: { vertLines: { visible: false }, horzLines: { color: css("--grid") } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true },
      crosshair: { horzLine: { labelBackgroundColor: css("--panel-2") }, vertLine: { labelBackgroundColor: css("--panel-2") } },
      handleScroll: false,
      handleScale: false,
    });
    chart.current = c;
    area.current = c.addAreaSeries({ lineWidth: 2, priceLineVisible: false });
    return () => c.remove();
  }, []);

  useEffect(() => {
    const c = chart.current, s = area.current;
    if (!c || !s || !series.length) return;
    const intraday = window !== "1mo";
    const fmt = (t: number) => (intraday && window === "1d" ? nyTime : nyDate).format(new Date(t * 1000));
    c.applyOptions({
      timeScale: { tickMarkFormatter: (t: Time) => fmt(t as number) },
      localization: { timeFormatter: (t: Time) => `${nyDate.format(new Date((t as number) * 1000))} ${nyTime.format(new Date((t as number) * 1000))} ET` },
    });
    const color = up ? css("--up") : css("--down");
    s.applyOptions({ lineColor: color, topColor: color + "55", bottomColor: color + "00" });

    const data = series.map((p) => ({ time: Math.floor(Date.parse(p.t) / 1000) as UTCTimestamp, value: p.price }));
    s.setData(data);

    // Snap each headline to the nearest bar so the marker sits on the line.
    const first = data[0].time, last = data[data.length - 1].time;
    const markers: SeriesMarker<Time>[] = news
      .filter((n) => n.bucket === "company" || highlighted.includes(n.id))
      .map((n) => ({ n, t: Math.floor(Date.parse(n.published_at) / 1000) }))
      .filter(({ t }) => t >= first && t <= last)
      .map(({ n, t }) => {
        const bar = data.reduce((a, b) => (Math.abs(b.time - t) < Math.abs(a.time - t) ? b : a));
        const hot = highlighted.includes(n.id);
        return { time: bar.time, position: "aboveBar" as const, shape: "circle" as const,
                 color: hot ? css("--accent") : css("--muted"), size: hot ? 1.4 : 0.8 };
      })
      .sort((a, b) => (a.time as number) - (b.time as number));
    s.setMarkers(markers);
    c.timeScale().fitContent();
  }, [series, news, window, up, highlighted]);

  return <div className="chart" ref={box} />;
}
