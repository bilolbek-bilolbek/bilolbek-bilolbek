import { useMemo, useState } from "react";
import type { UniverseTicker } from "../types";

/** Ticker search with suggestions by symbol or company name. */
export default function Search({ tickers, onPick }: { tickers: UniverseTicker[]; onPick: (s: string) => void }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    return tickers
      .filter((t) => t.ticker.toLowerCase().startsWith(s) || t.name.toLowerCase().includes(s))
      .slice(0, 6);
  }, [q, tickers]);

  function pick(s: string) {
    onPick(s.toUpperCase());
    setQ("");
    setOpen(false);
  }

  return (
    <form className="search" role="search" onSubmit={(e) => {
      e.preventDefault();
      const s = q.trim();
      if (s) pick(matches[0]?.ticker ?? s);
    }}>
      <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" className="search-icon">
        <circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="M13.5 13.5 L18 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <input id="ticker-search" value={q} placeholder="Search a stock — NVDA, Tesla…" aria-label="Search a stock"
             autoComplete="off" onChange={(e) => { setQ(e.target.value); setOpen(true); }}
             onBlur={() => setTimeout(() => setOpen(false), 150)} onFocus={() => setOpen(true)} />
      {open && matches.length > 0 && (
        <ul className="suggest">
          {matches.map((m) => (
            <li key={m.ticker}>
              <button type="button" onMouseDown={() => pick(m.ticker)}>
                <b>{m.ticker}</b> <span>{m.name}</span> <em>{m.sector}</em>
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
