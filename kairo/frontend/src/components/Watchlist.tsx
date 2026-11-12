import type { LiveTick } from "../useTicks";
import type { UniverseTicker } from "../types";
import { money, signed } from "../format";

interface Props {
  symbols: string[];
  names: Record<string, UniverseTicker>;
  ticks: Record<string, LiveTick>;
  active: string;
  onPick: (s: string) => void;
}

export default function Watchlist({ symbols, names, ticks, active, onPick }: Props) {
  return (
    <nav className="watchlist" aria-label="Watchlist">
      <div className="eyebrow wl-head">Watchlist</div>
      {symbols.map((s) => {
        const t = ticks[s];
        const up = (t?.dp ?? 0) >= 0;
        return (
          <button key={s} className={`wl-row ${s === active ? "on" : ""}`} onClick={() => onPick(s)}>
            <span className="wl-id">
              <b>{s}</b>
              <span className="wl-name">{names[s]?.name ?? ""}</span>
            </span>
            <span className="wl-num">
              <span key={t?.seq} className={`mono wl-price ${t?.dir === 1 ? "flash-up" : t?.dir === -1 ? "flash-down" : ""}`}>
                {t ? money(t.p) : "—"}
              </span>
              <span className={`wl-chg mono ${up ? "up" : "down"}`}>{t ? signed(t.dp) : ""}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}
