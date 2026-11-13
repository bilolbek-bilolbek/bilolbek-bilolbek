"""Export answers for every listed ticker, for the static demo build.

Usage (from backend/):
  ../.venv/bin/python scripts/export_static_demo.py OUT_DIR          # synthetic sample data
  ../.venv/bin/python scripts/export_static_demo.py OUT_DIR --live   # snapshot of real data now
Writes OUT_DIR/universe.json and OUT_DIR/{TICKER}-{window}.json.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

LIVE = "--live" in sys.argv
AI_1D_ONLY = "--ai-1d-only" in sys.argv
os.environ["DATA_MODE"] = "live" if LIVE else "sample"
os.environ["WARM_WATCHLIST"] = "false"
if not LIVE:
    os.environ["OPENAI_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone  # noqa: E402

import time  # noqa: E402

from app.analyzer import engine, heuristic  # noqa: E402
from app.analyzer.engine import explain  # noqa: E402
from app.context import build_context  # noqa: E402
from app.universe import PROFILES, WATCHLIST  # noqa: E402


async def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    universe = {"watchlist": WATCHLIST,
                "snapshot_at": datetime.now(timezone.utc).isoformat() if LIVE else None,
                "tickers": [{"ticker": p.ticker, "name": p.name, "sector": p.sector}
                            for p in PROFILES.values()]}
    (out / "universe.json").write_text(json.dumps(universe))
    for ticker in PROFILES:
        for window in ("1d", "5d", "1mo"):
            ctx = await build_context(ticker, window)
            # --ai-1d-only: spend AI requests on the main view only (free OpenAI plans have small limits).
            if AI_1D_ONLY and window != "1d":
                analysis = heuristic.analyze(ctx)
            else:
                analysis = await explain(ctx)
                # Free OpenAI plans cap requests per minute: wait out a short pause and retry.
                for _ in range(3):
                    wait = engine._paused_until - time.time()
                    if analysis.engine.startswith("openai") or wait <= 0 or wait > 120:
                        break
                    print(f"  {ticker}: OpenAI busy, waiting {wait:.0f}s")
                    await asyncio.sleep(wait + 1)
                    analysis = await explain(ctx)
                print(f"  {ticker} {window}: {analysis.engine}")
            data = {"context": ctx.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")}
            (out / f"{ticker}-{window}.json").write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {len(PROFILES) * 3 + 1} files to {out}")


if __name__ == "__main__":
    asyncio.run(main(Path([a for a in sys.argv[1:] if not a.startswith("--")][0])))
