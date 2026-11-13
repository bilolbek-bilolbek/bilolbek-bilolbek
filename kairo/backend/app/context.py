"""Builds everything the AI needs to explain a move: prices and news, fetched in parallel."""

import asyncio
import bisect
import time
from datetime import datetime, timezone

import httpx

from .config import settings
from .models import MarketContext, NewsItem, PriceMove, PricePoint, Window
from .providers import news as news_provider
from .providers import prices as price_provider
from .providers import sample, tiingo
from .providers.prices import summarize
from .universe import Profile, get_profile

BENCHMARK = "SPY"
# How many bars after a headline to measure the price reaction: ~30m, ~1h, 1 day.
REACTION_BARS = {"1d": 6, "5d": 2, "1mo": 1}


def add_reactions(series: list[PricePoint], news: list[NewsItem], window: Window) -> None:
    """Event-study style: how much did the stock move right after each headline?"""
    times = [p.t for p in series]
    k = REACTION_BARS[window]
    for n in news:
        known = max(n.published_at, n.available_at) if n.available_at else n.published_at
        i = bisect.bisect_left(times, known)
        if i == 0 or i >= len(series):
            n.reaction_pct = None  # before the chart starts or after it ends
            continue
        before, after = series[i - 1].price, series[min(i - 1 + k, len(series) - 1)].price
        n.reaction_pct = round((after / before - 1) * 100, 3)


class TTLCache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._data: dict = {}

    def get(self, key):
        hit = self._data.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        return None

    def set(self, key, value):
        self._data[key] = (time.monotonic(), value)


_cache = TTLCache(settings.cache_ttl)


def _excess(a: PriceMove | None, b: PriceMove | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a.change_pct - b.change_pct, 3)


def _assemble(p: Profile, window: Window, stock_pts: list[PricePoint], stock: PriceMove,
              spy: PriceMove | None, sector: PriceMove | None, news, is_sample: bool,
              sources: list[str], warnings: list[str]) -> MarketContext:
    add_reactions(stock_pts, news, window)
    return MarketContext(
        ticker=p.ticker, company=p.name, sector=p.sector, window=window,
        stock=stock, benchmark=spy, sector_etf=sector,
        excess_vs_market_pct=_excess(stock, spy), excess_vs_sector_pct=_excess(stock, sector),
        series=stock_pts, news=news, is_sample=is_sample, sources=sources,
        warnings=warnings, generated_at=datetime.now(timezone.utc),
    )


def sample_context(p: Profile, window: Window, warnings: list[str] | None = None) -> MarketContext:
    stock_pts, spy_pts, sector_pts, items = sample.sample_market(p, window)
    return _assemble(
        p, window, stock_pts, summarize(p.ticker, stock_pts),
        summarize(BENCHMARK, spy_pts),
        summarize(p.sector_etf, sector_pts) if sector_pts and p.sector_etf else None,
        items, True, [sample.SAMPLE_SOURCE], warnings or [],
    )


async def _fetch_price(client: httpx.AsyncClient, symbol: str, window: Window):
    """Yahoo first (no request limits); Tiingo as the backup when Yahoo fails."""
    try:
        return await price_provider.fetch_yahoo(client, symbol, window)
    except price_provider.PriceUnavailable:
        if not settings.tiingo_api_key:
            raise
        return await tiingo.fetch_prices(client, symbol, window, settings.tiingo_api_key)


async def live_context(p: Profile, window: Window) -> MarketContext:
    async with httpx.AsyncClient(timeout=settings.timeout, follow_redirects=True) as client:
        symbols = [p.ticker, BENCHMARK] + ([p.sector_etf] if p.sector_etf else [])
        price_jobs = [_fetch_price(client, s, window) for s in symbols]
        news_job = news_provider.gather_news(client, p, window, settings.finnhub_api_key,
                                              settings.tiingo_api_key)
        *price_results, news_result = await asyncio.gather(
            *price_jobs, news_job, return_exceptions=True)

    if isinstance(news_result, Exception):
        items, sources, warnings = [], [], [f"News unavailable ({type(news_result).__name__})"]
    else:
        items, sources, warnings = news_result

    if isinstance(price_results[0], Exception):
        raise price_results[0]
    stock_pts, stock = price_results[0]
    others = []
    for sym, res in zip(symbols[1:], price_results[1:]):
        if isinstance(res, Exception):
            warnings.append(f"{sym} price unavailable")
            others.append(None)
        else:
            others.append(res[1])
    spy = others[0]
    sector = others[1] if len(others) > 1 else None
    if not items:
        warnings.append("No recent news found from any source")
    return _assemble(p, window, stock_pts, stock, spy, sector, items, False,
                     ["Yahoo Finance prices"] + sources, warnings)


async def build_context(ticker: str, window: Window) -> MarketContext:
    p = get_profile(ticker)
    key = (p.ticker, window, settings.data_mode)
    if cached := _cache.get(key):
        return cached

    if settings.data_mode == "sample":
        ctx = sample_context(p, window)
    else:
        try:
            ctx = await live_context(p, window)
        except price_provider.PriceUnavailable as e:
            if settings.data_mode == "live":
                raise
            ctx = sample_context(p, window, [f"Live prices unreachable ({e}); showing sample data"])
    _cache.set(key, ctx)
    return ctx
