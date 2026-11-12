import { useEffect, useMemo, useState } from "react";
import PriceChart from "./components/PriceChart";
import Verdict from "./components/Verdict";
import NewsFeed from "./components/NewsFeed";
import TickerTape from "./components/TickerTape";
import Watchlist from "./components/Watchlist";
import Search from "./components/Search";
import Logo from "./components/Logo";
import ErrorBoundary from "./components/ErrorBoundary";
import AskKairo from "./components/AskKairo";
import Alerts from "./components/Alerts";
import type { Analysis, Health, MarketContext, UniverseTicker, Window } from "./types";
import { STATIC, getSnapshotAt, loadHealth, loadUniverse, streamExplain } from "./api";
import { useTicks } from "./useTicks";
import { money, signed } from "./format";

const WINDOWS: { id: Window; label: string }[] = [
  { id: "1d", label: "1D" },
  { id: "5d", label: "5D" },
  { id: "1mo", label: "1M" },
];

const MARKET_LABEL: Record<string, string> = {
  open: "Market open",
  "pre-market": "Pre-market",
  "after-hours": "After hours",
  closed: "Market closed",
  sample: "Sample data",
  snapshot: "Snapshot",
};

const FEED_LABEL: Record<string, string> = {
  "finnhub-stream": "Live trades · ms",
  connecting: "Connecting…",
  polling: "Live · every 2s",
  sample: "Simulated",
  snapshot: "Not live",
  starting: "Connecting…",
};

function initialTicker() {
  try {
    return new URLSearchParams(location.search).get("t")?.toUpperCase() || "NVDA";
  } catch {
    return "NVDA";
  }
}

export default function App() {
  const [ticker, setTicker] = useState(initialTicker);
  const [window, setWindow] = useState<Window>("1d");
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [universe, setUniverse] = useState<UniverseTicker[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [ctx, setCtx] = useState<MarketContext | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    loadUniverse().then((u) => { setWatchlist(u.watchlist); setUniverse(u.tickers); }).catch(() => {});
    loadHealth().then(setHealth).catch(() => {});
  }, []);

  // Prices and headlines arrive first, then the AI's answer (instant when pre-computed).
  useEffect(() => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setActive(null);
    if (!STATIC) {
      try { history.replaceState(null, "", `?t=${ticker}`); } catch { /* not allowed in some frames */ }
    }
    return streamExplain(ticker, window, {
      onContext: setCtx,
      onAnalysis: (a) => { setAnalysis(a); setLoading(false); },
      onError: (msg) => { setError(msg); setLoading(false); },
    });
  }, [ticker, window]);

  const names = useMemo(() => Object.fromEntries(universe.map((u) => [u.ticker, u])), [universe]);
  const tickSymbols = useMemo(
    () => Array.from(new Set([...watchlist, ticker])).filter(Boolean),
    [watchlist, ticker],
  );
  const { ticks, status } = useTicks(watchlist.length ? tickSymbols : []);

  const highlighted = useMemo(
    () => (active !== null && analysis ? analysis.drivers[active]?.evidence_ids ?? [] : []),
    [active, analysis],
  );

  const shown = ctx && ctx.ticker === ticker && ctx.window === window ? ctx : null;
  const live = ticks[ticker];
  // On the 1D view the headline number follows the live price; other views show the window's move.
  const price = live && window === "1d" ? live.p : shown?.stock.last;
  const change = live && window === "1d" && live.dp !== undefined ? live.dp : shown?.stock.change_pct;
  const up = (change ?? 0) >= 0;
  const market = status?.market ?? health?.market ?? "";
  const feed = status?.source ?? health?.prices ?? "";
  const pick = (s: string) => setTicker(s.toUpperCase());

  return (
    <div className="app">
      <header className="top">
        <Logo live={market === "open"} />
        <Search tickers={universe} onPick={pick} />
        <div className="status">
          <Alerts onPick={pick} />
          {market && <span className={`pill market-${market}`}><i />{MARKET_LABEL[market] ?? market}</span>}
          {feed && <span className="pill feed">{FEED_LABEL[feed] ?? feed}</span>}
        </div>
      </header>

      <TickerTape symbols={watchlist} ticks={ticks} onPick={pick} />

      {STATIC && getSnapshotAt() && (
        <div className="banner">
          Snapshot of real market data and news from {new Date(getSnapshotAt()!).toLocaleString("en-US", {
            timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ET.
          Prices don't update on this page; the full Kairo app streams them live.
        </div>
      )}
      {shown?.is_sample && (
        <div className="banner">
          Sample data: prices and headlines here are synthetic, for demos only.
          {shown.warnings[0] && !STATIC ? ` (${shown.warnings[0]})` : ""}
        </div>
      )}

      <div className="layout">
        <Watchlist symbols={watchlist} names={names} ticks={ticks} active={ticker} onPick={pick} />

        <section className="card quote">
          <div className="quote-head">
            <div className="quote-id">
              <h1>{ticker}</h1>
              <div className="quote-name">
                {shown && shown.company !== ticker && <span>{shown.company}</span>}
                {shown && <span className="chip">{shown.sector}</span>}
              </div>
            </div>
            <div className="windows" role="tablist" aria-label="Time range">
              {WINDOWS.map((w) => (
                <button key={w.id} role="tab" aria-selected={w.id === window} className={w.id === window ? "on" : ""}
                        onClick={() => setWindow(w.id)}>{w.label}</button>
              ))}
            </div>
          </div>

          {shown ? (
            <>
              <div className="price-row">
                <span key={live?.seq} className={`price mono ${live?.dir === 1 ? "flash-up" : live?.dir === -1 ? "flash-down" : ""}`}>
                  {money(price)}
                </span>
                <span className={`change mono ${up ? "up" : "down"}`}>
                  {up ? "▲" : "▼"} {signed(change)}
                </span>
                <span className="faint small">{window === "1d" ? "today" : window === "5d" ? "past 5 days" : "past month"}</span>
              </div>
              <dl className="stats">
                <div><dt>S&amp;P 500</dt><dd className={`mono ${(shown.benchmark?.change_pct ?? 0) >= 0 ? "up" : "down"}`}>{signed(shown.benchmark?.change_pct)}</dd></div>
                {shown.sector_etf && (
                  <div><dt>Sector · {shown.sector_etf.symbol}</dt><dd className={`mono ${shown.sector_etf.change_pct >= 0 ? "up" : "down"}`}>{signed(shown.sector_etf.change_pct)}</dd></div>
                )}
                <div><dt>vs market</dt><dd className="mono">{signed(shown.excess_vs_market_pct)}</dd></div>
                <div><dt>Range</dt><dd className="mono">{money(shown.stock.low)} – {money(shown.stock.high)}</dd></div>
              </dl>
              <ErrorBoundary label="The chart">
                <PriceChart series={shown.series} news={shown.news} window={window} up={up} highlighted={highlighted}
                            reference={shown.stock.reference} live={live ? { price: live.p, t: live.t } : null} />
              </ErrorBoundary>
              <p className="chart-note faint">Dots mark company headlines. Tap a reason to light up its news.</p>
            </>
          ) : (
            <div className="chart skeleton">{error ?? <span className="shimmer">Loading {ticker}…</span>}</div>
          )}
        </section>

        <aside className="side">
          {error && !shown ? (
            <section className="card"><p className="warning">{error}</p></section>
          ) : (
            <Verdict analysis={analysis} loading={loading} news={shown?.news ?? []} active={active}
                     onSelect={setActive} ticker={ticker} />
          )}
          {shown && <AskKairo ticker={ticker} window={window} news={shown.news} />}
        </aside>

        {shown && <NewsFeed news={shown.news} highlighted={highlighted} />}
      </div>

      <footer className="foot faint">
        Kairo explains likely reasons for price moves from public news. Likelihoods are AI estimates, not
        guarantees. Not investment advice.
      </footer>
    </div>
  );
}
