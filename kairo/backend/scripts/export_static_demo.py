"""Export sample-data answers for every listed ticker, for the static demo build.

Usage (from backend/):  ../.venv/bin/python scripts/export_static_demo.py OUT_DIR
Writes OUT_DIR/universe.json and OUT_DIR/{TICKER}-{window}.json.
Everything exported is synthetic sample data, never live market data.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["DATA_MODE"] = "sample"
os.environ["OPENAI_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analyzer.engine import explain  # noqa: E402
from app.context import build_context  # noqa: E402
from app.universe import PROFILES, WATCHLIST  # noqa: E402


async def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    universe = {"watchlist": WATCHLIST,
                "tickers": [{"ticker": p.ticker, "name": p.name, "sector": p.sector}
                            for p in PROFILES.values()]}
    (out / "universe.json").write_text(json.dumps(universe))
    for ticker in PROFILES:
        for window in ("1d", "5d", "1mo"):
            ctx = await build_context(ticker, window)
            analysis = await explain(ctx)
            data = {"context": ctx.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")}
            (out / f"{ticker}-{window}.json").write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {len(PROFILES) * 3 + 1} files to {out}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
