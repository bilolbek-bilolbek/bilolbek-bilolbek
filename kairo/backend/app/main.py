import asyncio
import contextlib
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import service
from .analyzer.engine import ai_status
from .config import settings
from .context import build_context
from .live import hub, market_status, tick_events
from .models import Analysis, MarketContext, Window
from .providers.prices import PriceUnavailable
from .universe import PROFILES, WATCHLIST

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    warmer = asyncio.create_task(service.warm_forever()) if service.warming_enabled() else None
    yield
    if warmer:
        warmer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await warmer


app = FastAPI(title="Kairo", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


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
        "prices": hub.source,
        "market": market_status(),
        "warming": service.warming_enabled(),
        "ai_status": ai_status(),
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
    start = time.perf_counter()
    analysis, hit = await service.get_analysis(await _context(_ticker(ticker), window))
    return analysis.model_copy(update={"from_cache": hit,
                                       "served_ms": round((time.perf_counter() - start) * 1000, 1)})


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.get("/api/stream/{ticker}")
async def stream(ticker: str, window: Window = Query("1d")):
    """Prices + headlines first, then the analysis (instant when pre-computed)."""
    t = _ticker(ticker)

    async def events():
        start = time.perf_counter()
        try:
            ctx = await build_context(t, window)
        except Exception as e:
            yield _sse("error", {"message": f"Could not load market data: {e}"})
            return
        yield _sse("context", ctx.model_dump(mode="json"))
        analysis, hit = await service.get_analysis(ctx)
        out = analysis.model_copy(update={"from_cache": hit,
                                          "served_ms": round((time.perf_counter() - start) * 1000, 1)})
        yield _sse("analysis", out.model_dump(mode="json"))
        yield _sse("done", {})

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/ticks")
async def ticks(symbols: str = Query(..., description="Comma-separated, e.g. NVDA,AAPL")):
    """Live prices as Server-Sent Events."""
    syms = list(dict.fromkeys(_ticker(s) for s in symbols.split(",") if s.strip()))[:30]
    if not syms:
        raise HTTPException(400, "No symbols")
    return StreamingResponse(tick_events(syms), media_type="text/event-stream", headers=SSE_HEADERS)


# Serve the built frontend (frontend/dist) from the same server, if it exists.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        return FileResponse(DIST / "index.html")
