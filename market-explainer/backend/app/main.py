import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analyzer.engine import explain
from .config import settings
from .context import build_context
from .models import Analysis, MarketContext, Window
from .providers.prices import PriceUnavailable
from .universe import PROFILES, WATCHLIST

app = FastAPI(title="Market Explainer", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _ticker(raw: str) -> str:
    t = raw.strip().upper()
    if not TICKER.match(t):
        raise HTTPException(400, "Invalid ticker")
    return t


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "data_mode": settings.data_mode,
        "ai": f"openai:{settings.openai_model}" if settings.openai_api_key else "heuristic (offline)",
        "finnhub": bool(settings.finnhub_api_key),
    }


@app.get("/api/universe")
def universe():
    return {
        "watchlist": WATCHLIST,
        "tickers": [{"ticker": p.ticker, "name": p.name, "sector": p.sector} for p in PROFILES.values()],
    }


async def _context(ticker: str, window: Window) -> MarketContext:
    try:
        return await build_context(ticker, window)
    except PriceUnavailable as e:
        raise HTTPException(502, f"Price data unavailable: {e}") from e


@app.get("/api/context/{ticker}", response_model=MarketContext)
async def context(ticker: str, window: Window = Query("1d")):
    return await _context(_ticker(ticker), window)


@app.get("/api/explain/{ticker}", response_model=Analysis)
async def explain_once(ticker: str, window: Window = Query("1d")):
    return await explain(await _context(_ticker(ticker), window))


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.get("/api/stream/{ticker}")
async def stream(ticker: str, window: Window = Query("1d")):
    """Sends prices + headlines first (fast), then the AI analysis when it's ready."""
    t = _ticker(ticker)

    async def events():
        try:
            ctx = await build_context(t, window)
        except Exception as e:
            yield _sse("error", {"message": f"Could not load market data: {e}"})
            return
        yield _sse("context", ctx.model_dump(mode="json"))
        analysis = await explain(ctx)
        yield _sse("analysis", analysis.model_dump(mode="json"))
        yield _sse("done", {})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Serve the built frontend (frontend/dist) from the same server, if it exists.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        return FileResponse(DIST / "index.html")
