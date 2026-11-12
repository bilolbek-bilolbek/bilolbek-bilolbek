import type { Alert, Analysis, Health, MarketContext, Tick, TickStatus, UniverseTicker, Window } from "./types";

/**
 * Talks to the backend. In a static demo build (VITE_STATIC=1) there is no
 * backend: answers come from pre-exported sample files in ./demo/.
 */
export const STATIC = import.meta.env.VITE_STATIC === "1";

export interface Universe {
  watchlist: string[];
  tickers: UniverseTicker[];
  /** Static builds made from real data carry the time the snapshot was taken. */
  snapshot_at?: string | null;
}

let snapshotAt: string | null = null;
export const getSnapshotAt = () => snapshotAt;

interface Handlers {
  onContext: (c: MarketContext) => void;
  onAnalysis: (a: Analysis) => void;
  onError: (msg: string) => void;
}

export async function loadUniverse(): Promise<Universe> {
  const r = await fetch(STATIC ? "demo/universe.json" : "/api/universe");
  const u: Universe = await r.json();
  snapshotAt = u.snapshot_at ?? null;
  return u;
}

export async function loadHealth(): Promise<Health> {
  if (STATIC) return { ok: true, data_mode: "sample", ai: "demo", finnhub: false };
  const r = await fetch("/api/health");
  return r.json();
}

const DAY = 86_400_000;

/** Move a saved sample forward by whole days so "2h ago" stays true and charts keep market hours. */
function rebase(ctx: MarketContext): MarketContext {
  if (!ctx.is_sample) return ctx; // real snapshots keep their real times
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

/** Live prices. Returns a function that stops the feed. */
export function subscribeTicks(symbols: string[], onTick: (t: Tick) => void,
                               onStatus: (s: TickStatus) => void): () => void {
  if (!symbols.length) return () => {};
  if (STATIC) return simulateTicks(symbols, onTick, onStatus);
  const es = new EventSource(`/api/ticks?symbols=${symbols.map(encodeURIComponent).join(",")}`);
  es.addEventListener("tick", (e) => onTick(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("status", (e) => onStatus(JSON.parse((e as MessageEvent).data)));
  return () => es.close();
}

/** Demo build only: gentle random moves around the sample's last price. */
function simulateTicks(symbols: string[], onTick: (t: Tick) => void, onStatus: (s: TickStatus) => void) {
  if (snapshotAt) return snapshotTicks(symbols, onTick, onStatus);
  onStatus({ source: "sample", market: "sample" });
  const state: Record<string, { p: number; pc: number }> = {};
  let stopped = false;
  Promise.all(symbols.map((s) => fetch(`demo/${s}-1d.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
    .then((rows) => rows.forEach((d, i) => {
      if (d) state[symbols[i]] = { p: d.context.stock.last, pc: d.context.stock.reference };
    }));
  const timer = globalThis.setInterval(() => {
    if (stopped) return;
    for (const [s, v] of Object.entries(state)) {
      if (Math.random() < 0.5) continue;
      v.p = +(v.p * (1 + (Math.random() - 0.5) * 0.0012)).toFixed(2);
      onTick({ s, p: v.p, t: Date.now(), pc: v.pc, dp: +((v.p / v.pc - 1) * 100).toFixed(3) });
    }
  }, 1200);
  return () => { stopped = true; globalThis.clearInterval(timer); };
}

/** Real-data snapshot: show each saved price once. Never invent movement. */
function snapshotTicks(symbols: string[], onTick: (t: Tick) => void, onStatus: (s: TickStatus) => void) {
  onStatus({ source: "snapshot", market: "snapshot" });
  let stopped = false;
  symbols.forEach((s) =>
    fetch(`demo/${s}-1d.json`).then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d || stopped) return;
      const st = d.context.stock;
      onTick({ s, p: st.last, t: Date.parse(d.context.series.at(-1)?.t ?? d.context.generated_at),
               pc: st.reference, dp: st.change_pct });
    }).catch(() => {}));
  return () => { stopped = true; };
}

export interface ChatTurn { role: "user" | "assistant"; content: string }

/** Ask Kairo a question; calls onText with the answer so far as it streams in. */
export async function askKairo(ticker: string, window: Window, question: string, history: ChatTurn[],
                               onText: (soFar: string) => void, signal?: AbortSignal): Promise<string> {
  if (STATIC) {
    const msg = "Ask Kairo needs the live Kairo server. This page is a snapshot, so chat is off here.";
    onText(msg);
    return msg;
  }
  const r = await fetch(`/api/ask/${encodeURIComponent(ticker)}?window=${window}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, history }),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`Server error ${r.status}`);
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    text += decoder.decode(value, { stream: true });
    onText(text);
  }
  return text;
}

/** Alerts for sharp moves. The same alert id can arrive twice: the second carries a fresher reason. */
export function subscribeAlerts(onAlert: (a: Alert) => void): () => void {
  if (STATIC) return () => {};
  const es = new EventSource("/api/alerts");
  es.addEventListener("alert", (e) => onAlert(JSON.parse((e as MessageEvent).data)));
  return () => es.close();
}
