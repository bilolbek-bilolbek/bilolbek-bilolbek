"""Answers ready before the trader asks.

The AI takes a few seconds per stock, so Kairo works ahead: a background loop
keeps prices, news and an analysis fresh for every watchlist stock. A click
then returns a stored answer in milliseconds. The AI is only asked again when
something changed: a new headline, or the price moved noticeably.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from .analyzer.engine import ai_available, explain
from .config import settings
from .context import build_context
from .models import Analysis, MarketContext, Window
from .universe import PROFILES

log = logging.getLogger("kairo.service")

REANALYZE_MOVE_PCT = 0.4   # re-run the AI if the move changed this much (percentage points)
MAX_AGE_SECONDS = 15 * 60  # ...or if the answer is older than this
WARM_EVERY_SECONDS = 60


@dataclass
class Stored:
    analysis: Analysis
    news_ids: frozenset[str]
    change_pct: float
    at: float


_store: dict[tuple[str, str], Stored] = {}
_locks: dict[tuple[str, str], asyncio.Lock] = {}


def _still_valid(s: Stored, ctx: MarketContext) -> bool:
    # A fallback answer is only a stand-in: replace it as soon as the AI is back.
    if not s.analysis.engine.startswith("openai") and ai_available():
        return False
    return (
        time.time() - s.at < MAX_AGE_SECONDS
        and abs(ctx.stock.change_pct - s.change_pct) < REANALYZE_MOVE_PCT
        # A new company or peer headline is worth a fresh look; churn in the
        # broader economy/sector feeds isn't, on its own.
        and not any(n.id not in s.news_ids for n in ctx.news
                    if n.bucket in ("company", "peers_supply_chain"))
    )


def cached(ticker: str, window: Window) -> Stored | None:
    return _store.get((ticker, window))


async def get_analysis(ctx: MarketContext) -> tuple[Analysis, bool]:
    """Returns (analysis, came_from_cache)."""
    key = (ctx.ticker, ctx.window)
    hit = _store.get(key)
    if hit and _still_valid(hit, ctx):
        return hit.analysis, True
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:  # if the warmer is already on it, wait for its answer
        hit = _store.get(key)
        if hit and _still_valid(hit, ctx):
            return hit.analysis, True
        analysis = await explain(ctx)
        _store[key] = Stored(analysis, frozenset(n.id for n in ctx.news), ctx.stock.change_pct, time.time())
        return analysis, False


async def explain_ticker(ticker: str, window: Window) -> tuple[MarketContext, Analysis, bool]:
    ctx = await build_context(ticker, window)
    analysis, hit = await get_analysis(ctx)
    return ctx, analysis, hit


async def warm_forever() -> None:
    """Keep answers fresh for every stock Kairo has a profile for."""
    sem = asyncio.Semaphore(4)

    async def one(t: str):
        async with sem:
            try:
                await explain_ticker(t, "1d")
            except Exception as e:
                log.warning("warm %s failed: %s", t, e)

    while True:
        start = time.monotonic()
        await asyncio.gather(*(one(t) for t in PROFILES))
        log.info("warmed %d tickers in %.1fs", len(PROFILES), time.monotonic() - start)
        await asyncio.sleep(max(5, WARM_EVERY_SECONDS - (time.monotonic() - start)))


def warming_enabled() -> bool:
    return settings.warm_watchlist and settings.data_mode != "sample"
