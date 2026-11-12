import type { Analysis, Health, MarketContext, Window } from "./types";

/**
 * Talks to the backend. In a static demo build (VITE_STATIC=1) there is no
 * backend: answers come from pre-exported sample files in ./demo/.
 */
export const STATIC = import.meta.env.VITE_STATIC === "1";

export interface Universe {
  watchlist: string[];
  tickers: { ticker: string; name: string; sector: string }[];
}

interface Handlers {
  onContext: (c: MarketContext) => void;
  onAnalysis: (a: Analysis) => void;
  onError: (msg: string) => void;
}

export async function loadUniverse(): Promise<Universe> {
  const r = await fetch(STATIC ? "demo/universe.json" : "/api/universe");
  return r.json();
}

export async function loadHealth(): Promise<Health> {
  if (STATIC) return { ok: true, data_mode: "sample", ai: "demo", finnhub: false };
  const r = await fetch("/api/health");
  return r.json();
}

const DAY = 86_400_000;

/** Move a saved sample forward by whole days so "2h ago" stays true and charts keep market hours. */
function rebase(ctx: MarketContext): MarketContext {
  const shift = Math.max(0, Math.floor((Date.now() - Date.parse(ctx.generated_at)) / DAY)) * DAY;
  if (!shift) return ctx;
  const move = (iso: string) => new Date(Date.parse(iso) + shift).toISOString();
  return {
    ...ctx,
    generated_at: move(ctx.generated_at),
    series: ctx.series.map((p) => ({ ...p, t: move(p.t) })),
    news: ctx.news.map((n) => ({ ...n, published_at: move(n.published_at) })),
  };
}

/** Prices + headlines first, then the analysis. Returns a function that cancels. */
export function streamExplain(ticker: string, window: Window, h: Handlers): () => void {
  if (STATIC) {
    let cancelled = false;
    const timers: number[] = [];
    fetch(`demo/${ticker}-${window}.json`)
      .then((r) => {
        if (!r.ok) throw new Error("missing");
        return r.json();
      })
      .then((d: { context: MarketContext; analysis: Analysis }) => {
        if (cancelled) return;
        // Pace it like the live app: data first, then the answer.
        timers.push(window_setTimeout(() => !cancelled && h.onContext(rebase(d.context)), 120));
        timers.push(window_setTimeout(() => !cancelled && h.onAnalysis(d.analysis), 900));
      })
      .catch(() => !cancelled && h.onError(`${ticker} isn't in this demo. Try one from the watchlist.`));
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }

  const es = new EventSource(`/api/stream/${encodeURIComponent(ticker)}?window=${window}`);
  es.addEventListener("context", (e) => h.onContext(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("analysis", (e) => h.onAnalysis(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("error", (e) => {
    const data = (e as MessageEvent).data;
    if (data) h.onError(JSON.parse(data).message);
    else if (es.readyState !== EventSource.CLOSED) h.onError("Lost connection to the server.");
    es.close();
  });
  es.addEventListener("done", () => es.close());
  return () => es.close();
}

const window_setTimeout = (fn: () => void, ms: number) => globalThis.setTimeout(fn, ms) as unknown as number;
