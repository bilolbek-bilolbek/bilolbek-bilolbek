import type { LiveTick } from "../useTicks";
import { money, signed } from "../format";

interface Props { symbols: string[]; ticks: Record<string, LiveTick>; onPick: (s: string) => void }

/** Scrolling strip of live prices, like a trading floor tape. */
export default function TickerTape({ symbols, ticks, onPick }: Props) {
  const items = symbols.filter((s) => ticks[s]);
  if (!items.length) return <div className="tape tape-empty" />;
  const row = items.map((s) => {
    const t = ticks[s];
    const up = (t.dp ?? 0) >= 0;
    return (
      <button key={s} className="tape-item" onClick={() => onPick(s)}>
        <b>{s}</b>
        <span className="mono">{money(t.p)}</span>
        <span className={`mono ${up ? "up" : "down"}`}>{signed(t.dp)}</span>
      </button>
    );
  });
  return (
    <div className="tape" aria-label="Live prices">
      <div className="tape-track">
        <div className="tape-row">{row}</div>
        <div className="tape-row" aria-hidden="true">{row}</div>
      </div>
    </div>
  );
}
