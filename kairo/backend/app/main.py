import asyncio
import contextlib
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import alerts, service
from .analyzer import chat
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
    tasks = []
    if service.warming_enabled():
        tasks.append(asyncio.create_task(service.warm_forever()))
    if settings.data_mode != "sample":
        tasks.append(asyncio.create_task(alerts.watch_watchlist()))
    yield
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t


app = FastAPI(title="Kairo", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

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


@app.post("/api/ask/{ticker}")
async def ask(ticker: str, window: Window = Query("1d"),
              question: str = Body(..., embed=True, min_length=1, max_length=1000),
              history: list[dict] = Body(default_factory=list, embed=True)):
    """Ask Kairo a follow-up question about one stock. Streams the answer as plain text."""
    ctx = await _context(_ticker(ticker), window)
    stored = service.cached(ctx.ticker, window)
    return StreamingResponse(chat.ask(ctx, stored.analysis if stored else None, question, history),
                             media_type="text/plain; charset=utf-8", headers=SSE_HEADERS)


@app.get("/api/alerts")
async def alert_stream():
    """Alerts for sharp moves on the watchlist, as Server-Sent Events."""
    return StreamingResponse(alerts.alert_events(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/api/alerts/test")
async def test_alert(ticker: str = Query("NVDA")):
    """Sends a clearly labelled test alert using the stock's current move (for demos)."""
    ctx = await _context(_ticker(ticker), "1d")
    a = alerts.center.raise_alert("test", ctx.ticker, f"Test alert: {ctx.ticker} {ctx.stock.change_pct:+.1f}% today",
                                  ctx.stock.change_pct, ctx.stock.last)
    return a.to_json()


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
