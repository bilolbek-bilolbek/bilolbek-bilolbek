"""Price data from Yahoo Finance's public chart endpoint (no API key needed)."""

from datetime import datetime, timezone

import httpx

from ..models import PriceMove, PricePoint, Window

# Yahoo range + bar size for each window we support.
WINDOW_PARAMS: dict[str, tuple[str, str]] = {
    "1d": ("1d", "5m"),
    "5d": ("5d", "30m"),
    "1mo": ("1mo", "1d"),
}

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; kairo/0.1)"}


class PriceUnavailable(Exception):
    pass


def summarize(symbol: str, points: list[PricePoint], reference: float | None = None,
              last: float | None = None) -> PriceMove:
    prices = [p.price for p in points]
    ref = reference if reference else prices[0]
    last_price = last if last else prices[-1]
    return PriceMove(
        symbol=symbol,
        last=round(last_price, 4),
        reference=round(ref, 4),
        change_pct=round((last_price / ref - 1) * 100, 3),
        high=round(max(prices), 4),
        low=round(min(prices), 4),
    )


async def fetch_yahoo(client: httpx.AsyncClient, symbol: str,
                      window: Window) -> tuple[list[PricePoint], PriceMove]:
    rng, interval = WINDOW_PARAMS[window]
    try:
        r = await client.get(
            YAHOO_CHART.format(symbol=symbol),
            params={"range": rng, "interval": interval, "includePrePost": "false"},
            headers=HEADERS,
        )
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
        raise PriceUnavailable(f"{symbol}: {e}") from e

    timestamps = result.get("timestamp") or []
    closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    points = [
        PricePoint(t=datetime.fromtimestamp(ts, tz=timezone.utc), price=c)
        for ts, c in zip(timestamps, closes)
        if c is not None
    ]
    if not points:
        raise PriceUnavailable(f"{symbol}: no price data")

    meta = result.get("meta", {})
    reference = None
    if window == "1d":
        # Daily move is measured against yesterday's close, like trading apps do.
        reference = meta.get("chartPreviousClose") or meta.get("previousClose")
    return points, summarize(symbol, points, reference, meta.get("regularMarketPrice"))
