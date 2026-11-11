"""Synthetic sample data, so the app runs with no internet and no API keys.

Everything here is made up and is always labelled as sample data in the API
and the UI. It is for development and offline demos only. The same ticker on
the same day always gives the same sample, so the screen doesn't jump around.
"""

import hashlib
import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..models import NewsItem, PricePoint, Window
from ..universe import Profile

SAMPLE_SOURCE = "Sample feed (synthetic)"
BARS = {"1d": (78, timedelta(minutes=5)), "5d": (65, timedelta(minutes=30)), "1mo": (22, timedelta(days=1))}

UP = {
    "company": ["{name} shares jump after quarterly revenue beats analyst estimates",
                "Analyst upgrades {name} to Buy and raises price target",
                "{name} says early demand for its new products is strong"],
    "peers_supply_chain": ["{peer} posts strong results, lifting shares across the group",
                           "{supplier} reports record orders, a sign of demand from customers like {name}"],
    "sector": ["Investors rotate into {sector} stocks as {term} accelerates"],
    "geopolitics": ["Officials signal progress on {geo}, easing pressure on {sector} names"],
}
DOWN = {
    "company": ["{name} shares slide after the company cuts its full-year outlook",
                "Analyst downgrades {name} to Sell, citing slowing growth",
                "Regulators open a review of {name} business practices"],
    "peers_supply_chain": ["{peer} warns of weaker demand, weighing on rivals",
                           "{supplier} flags production delays that could affect {name}"],
    "sector": ["{sector} stocks fall as worries grow over {term}"],
    "geopolitics": ["Fresh uncertainty over {geo} rattles {sector} investors"],
}
NEUTRAL_MACRO = ["Treasury yields hold steady ahead of the next Federal Reserve meeting",
                 "Inflation report comes in roughly in line with expectations",
                 "Stocks drift as investors wait for new economic data"]


NY = ZoneInfo("America/New_York")


def _last_session_open(now: datetime) -> datetime:
    """9:30 ET of the most recent weekday session that has started."""
    local = now.astimezone(NY)
    day = local.date()
    if local.time() < time(9, 30):
        day -= timedelta(days=1)
    while day.weekday() >= 5:  # skip weekends
        day -= timedelta(days=1)
    return datetime.combine(day, time(9, 30), NY).astimezone(timezone.utc)


def _rng(*parts: str) -> random.Random:
    seed = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def _path(rng: random.Random, n: int, base: float, move_pct: float, shock_at: int,
          vol: float) -> list[float]:
    """A price path that ends `move_pct` away from `base`, with a jump at `shock_at`."""
    walk, w = [], 0.0
    for _ in range(n):
        w += rng.gauss(0, 1)
        walk.append(w)
    # Pin the noise so it starts and ends at zero (a Brownian bridge).
    bridge = [walk[i] - walk[-1] * i / (n - 1) for i in range(n)]
    prices = []
    for i in range(n):
        trend = 0.35 * move_pct * i / (n - 1)
        jump = 0.65 * move_pct * min(1.0, max(0.0, (i - shock_at + 2) / 3))
        prices.append(base * (1 + (trend + jump + bridge[i] * vol) / 100))
    return prices


def sample_market(p: Profile, window: Window, now: datetime | None = None):
    """Returns (stock, spy, sector) series as lists of PricePoint, plus news items."""
    now = now or datetime.now(timezone.utc)
    rng = _rng(p.ticker, now.date().isoformat(), window)
    n, step = BARS[window]
    if window == "1d":
        # A full regular session, 9:30 to 15:55 ET, like a real intraday chart.
        start = _last_session_open(now)
        times = [start + step * i for i in range(n)]
    else:
        times = [now - step * (n - 1 - i) for i in range(n)]

    direction = rng.choice([1, -1])
    stock_move = direction * rng.uniform(1.5, 4.5)
    market_move = rng.uniform(-0.6, 0.6)
    sector_move = market_move + direction * rng.uniform(0.3, 1.2)
    shock_at = int(n * rng.uniform(0.3, 0.6))

    def series(base: float, move: float, vol: float, shock: int):
        return [PricePoint(t=t, price=round(x, 2))
                for t, x in zip(times, _path(rng, n, base, move, shock, vol))]

    stock = series(rng.uniform(40, 600), stock_move, 0.12, shock_at)
    spy = series(rng.uniform(550, 650), market_move, 0.04, n // 2)
    sector = series(rng.uniform(80, 300), sector_move, 0.07, shock_at) if p.sector_etf else None

    templates = UP if direction > 0 else DOWN
    fill = {
        "name": p.name,
        "peer": (p.peers or ["A major competitor"])[0],
        "supplier": (p.supply_chain or p.peers or ["A key supplier"])[0],
        "sector": p.sector,
        "term": (p.sector_terms or ["demand"])[0],
        "geo": (p.geo_terms or ["trade policy"])[0],
    }
    shock_time = times[shock_at]
    news: list[tuple[str, str, datetime]] = [
        ("company", templates["company"][0], shock_time - timedelta(minutes=4)),
        ("company", templates["company"][rng.randint(1, 2)], shock_time + step * 3),
        ("peers_supply_chain", rng.choice(templates["peers_supply_chain"]), shock_time - step * 6),
        ("sector", templates["sector"][0], shock_time + step * 5),
        ("geopolitics", templates["geopolitics"][0], times[max(0, shock_at - 15)]),
        ("macro", NEUTRAL_MACRO[0], times[2]),
        ("macro", NEUTRAL_MACRO[rng.randint(1, 2)], times[n // 3]),
    ]
    items = [
        NewsItem(
            id=hashlib.sha1(f"{p.ticker}{i}{h}".encode()).hexdigest()[:10],
            headline=h.format(**fill),
            summary="Synthetic example headline for offline development. Not real news.",
            source=SAMPLE_SOURCE,
            url=None,
            published_at=min(t, now),
            bucket=b,
        )
        for i, (b, h, t) in enumerate(news)
    ]
    items.sort(key=lambda x: x.published_at, reverse=True)
    return stock, spy, sector, items
