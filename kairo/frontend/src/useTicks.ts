import { useEffect, useRef, useState } from "react";
import { subscribeTicks } from "./api";
import type { Tick, TickStatus } from "./types";

export interface LiveTick extends Tick {
  /** +1 if the last update went up, -1 if down; drives the flash animation. */
  dir: 1 | -1 | 0;
  /** Changes on every update so the flash can restart. */
  seq: number;
}

/** Live prices for a set of symbols, kept in one map. */
export function useTicks(symbols: string[]) {
  const [ticks, setTicks] = useState<Record<string, LiveTick>>({});
  const [status, setStatus] = useState<TickStatus | null>(null);
  const seq = useRef(0);
  const key = symbols.join(",");

  useEffect(() => {
    if (!key) return;
    return subscribeTicks(key.split(","), (t) => {
      setTicks((prev) => {
        const old = prev[t.s];
        const dir = old ? (t.p > old.p ? 1 : t.p < old.p ? -1 : old.dir) : 0;
        return { ...prev, [t.s]: { ...old, ...t, dir, seq: ++seq.current } };
      });
    }, setStatus);
  }, [key]);

  return { ticks, status };
}
