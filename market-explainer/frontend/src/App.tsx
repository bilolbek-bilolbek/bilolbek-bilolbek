import { useEffect, useMemo, useState } from "react";
import PriceChart from "./components/PriceChart";
import WhyPanel from "./components/WhyPanel";
import NewsFeed from "./components/NewsFeed";
import type { Analysis, Health, MarketContext, Window } from "./types";

const WINDOWS: { id: Window; label: string }[] = [
  { id: "1d", label: "1D" },
  { id: "5d", label: "5D" },
  { id: "1mo", label: "1M" },
];

function signed(x: number | null | undefined, digits = 2) {
  if (x === null || x === undefined) return "—";
  return `${x >= 0 ? "+" : ""}${x.toFixed(digits)}%`;
}

export default function App() {
  const [ticker, setTicker] = useState(() => new URLSearchParams(location.search).get("t")?.toUpperCase() || "NVDA");
  const [query, setQuery] = useState("");
  const [window, setWindow] = useState<Window>("1d");
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [ctx, setCtx] = useState<MarketContext | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/universe").then((r) => r.json()).then((u) => setWatchlist(u.watchlist)).catch(() => {});
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => {});
  }, []);

  // Open a stream: headlines + prices arrive first, the AI's answer right after.
  useEffect(() => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setActive(null);
    history.replaceState(null, "", `?t=${ticker}`);
    const es = new EventSource(`/api/stream/${encodeURIComponent(ticker)}?window=${window}`);
    es.addEventListener("context", (e) => setCtx(JSON.parse((e as MessageEvent).data)));
    es.addEventListener("analysis", (e) => {
      setAnalysis(JSON.parse((e as MessageEvent).data));
      setLoading(false);
    });
    es.addEventListener("error", (e) => {
      const data = (e as MessageEvent).data;
      if (data) setError(JSON.parse(data).message);
      else if (es.readyState !== EventSource.CLOSED) setError("Lost connection to the server.");
      setLoading(false);
      es.close();
    });
    es.addEventListener("done", () => es.close());
    return () => es.close();
  }, [ticker, window]);

  const highlighted = useMemo(
    () => (active !== null && analysis ? analysis.drivers[active]?.evidence_ids ?? [] : []),
    [active, analysis],
  );

  const shown = ctx && ctx.ticker === ticker && ctx.window === window ? ctx : null;
  const up = (shown?.stock.change_pct ?? 0) >= 0;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const t = query.trim().toUpperCase();
    if (t) setTicker(t);
    setQuery("");
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo">◆</span> Catalyst
          <span className="tagline">Why is it moving?</span>
        </div>
        <form onSubmit={submit} className="search">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ticker, e.g. AAPL" aria-label="Ticker" />
        </form>
        <div className="status">
          {health && <span className="pill">{health.ai.startsWith("openai") ? "AI: " + health.ai.slice(7) : "AI: offline mode"}</span>}
        </div>
      </header>

      {shown?.is_sample && (
        <div className="banner">
          Sample data: these prices and headlines are synthetic, for development only.
          {shown.warnings[0] ? ` (${shown.warnings[0]})` : ""}
        </div>
      )}

      <div className="layout">
        <nav className="watchlist">
          {watchlist.map((t) => (
            <button key={t} className={t === ticker ? "on" : ""} onClick={() => setTicker(t)}>{t}</button>
          ))}
        </nav>

        <main className="main">
          <section className="panel quote">
            <div className="quote-head">
              <div>
                <h1>{ticker} <span className="muted company">{shown?.company !== ticker ? shown?.company : ""}</span></h1>
                <div className="muted small">{shown?.sector}</div>
              </div>
              <div className="windows">
                {WINDOWS.map((w) => (
                  <button key={w.id} className={w.id === window ? "on" : ""} onClick={() => setWindow(w.id)}>{w.label}</button>
                ))}
              </div>
            </div>
            {shown ? (
              <>
                <div className="price-row">
                  <span className="price mono">${shown.stock.last.toFixed(2)}</span>
                  <span className={`change mono ${up ? "up" : "down"}`}>{signed(shown.stock.change_pct)}</span>
                </div>
                <div className="compare">
                  <span>S&P 500 <b className="mono">{signed(shown.benchmark?.change_pct)}</b></span>
                  {shown.sector_etf && <span>Sector ({shown.sector_etf.symbol}) <b className="mono">{signed(shown.sector_etf.change_pct)}</b></span>}
                  <span>vs market <b className="mono">{signed(shown.excess_vs_market_pct)}</b></span>
                </div>
                <PriceChart series={shown.series} news={shown.news} window={window} up={up} highlighted={highlighted} />
              </>
            ) : (
              <div className="chart skeleton">{error ?? "Loading prices…"}</div>
            )}
          </section>
          {shown && <NewsFeed news={shown.news} highlighted={highlighted} />}
        </main>

        <aside className="side">
          {error && !shown ? (
            <section className="panel"><p className="warning">{error}</p></section>
          ) : (
            <WhyPanel analysis={analysis} loading={loading} news={shown?.news ?? []} active={active} onSelect={setActive} />
          )}
        </aside>
      </div>

      <footer className="foot muted small">
        Explains likely reasons for past price moves from public news. Likelihoods are AI estimates, not
        guarantees. Not investment advice.
      </footer>
    </div>
  );
}
