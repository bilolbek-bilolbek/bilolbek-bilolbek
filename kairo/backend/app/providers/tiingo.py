"""Tiingo (tiingo.com): licensed prices, and news with crawlDate.

- Prices: a backup when Yahoo fails. The free plan has low request limits, so
  Tiingo is not used for second-by-second polling.
- News: needs Tiingo's News API add-on. Each story carries crawlDate, the time
  Tiingo first saw it. That is when a trader could actually have known, so Kairo
  uses it for timing; publishedDate can be earlier, or backfilled.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from ..models import NewsItem, PricePoint, PriceMove, Window
from .prices import PriceUnavailable, summarize

API = "https://api.tiingo.com"
NY = ZoneInfo("America/New_York")
LOOKBACK_DAYS = {"1d": 2, "5d": 7, "1mo": 31}


class NewsNotInPlan(Exception):
    """The Tiingo account doesn't include the News API."""


def _headers(token: str) -> dict:
    return {"Authorization": f"Token {token}"}


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _ny_day(t: datetime) -> date:
    return t.astimezone(NY).date()


async def _get(client: httpx.AsyncClient, path: str, token: str, **params):
    r = await client.get(API + path, headers=_headers(token), params=params)
    if r.status_code in (401, 403) and "news" in path:
        raise NewsNotInPlan(r.text[:120])
    r.raise_for_status()
    return r.json()


async def fetch_prices(client: httpx.AsyncClient, symbol: str, window: Window,
                       token: str) -> tuple[list[PricePoint], PriceMove]:
    today = datetime.now(timezone.utc).date()
    try:
        if window == "1mo":
            rows = await _get(client, f"/tiingo/daily/{symbol}/prices", token,
                              startDate=(today - timedelta(days=35)).isoformat())
            points = [PricePoint(t=_ts(r["date"]), price=r["close"]) for r in rows if r.get("close")]
            points = points[-22:]
            if not points:
                raise PriceUnavailable(f"{symbol}: no Tiingo data")
            return points, summarize(symbol, points)

        rows = await _get(client, f"/iex/{symbol}/prices", token,
                          startDate=(today - timedelta(days=4 if window == "1d" else 10)).isoformat(),
                          resampleFreq="5min" if window == "1d" else "30min", columns="close")
        points = [PricePoint(t=_ts(r["date"]), price=r["close"]) for r in rows if r.get("close")]
        if not points:
            raise PriceUnavailable(f"{symbol}: no Tiingo data")
        days = sorted({_ny_day(p.t) for p in points})
        keep = set(days[-1:] if window == "1d" else days[-5:])
        points = [p for p in points if _ny_day(p.t) in keep]

        reference = None
        if window == "1d":
            quote = await _get(client, "/iex/", token, tickers=symbol)
            reference = (quote[0] if quote else {}).get("prevClose")
        return points, summarize(symbol, points, reference)
    except httpx.HTTPError as e:
        raise PriceUnavailable(f"{symbol} (Tiingo): {e}") from e
    except (KeyError, TypeError, ValueError) as e:
        raise PriceUnavailable(f"{symbol} (Tiingo): bad data {e}") from e


def parse_news(rows: list[dict], make_item) -> list[NewsItem]:
    items = []
    for a in rows:
        if not a.get("title") or not a.get("publishedDate"):
            continue
        item = make_item(a["title"], a.get("source") or "Tiingo", _ts(a["publishedDate"]), "company",
                         a.get("url"), a.get("description") or "")
        if a.get("crawlDate"):
            item.available_at = _ts(a["crawlDate"])
        items.append(item)
    return items


async def company_news(client: httpx.AsyncClient, ticker: str, window: Window, token: str,
                       make_item) -> list[NewsItem]:
    start = datetime.now(timezone.utc).date() - timedelta(days=LOOKBACK_DAYS[window])
    rows = await _get(client, "/tiingo/news", token, tickers=ticker.lower(),
                      startDate=start.isoformat(), limit=50, sortBy="crawlDate")
    return parse_news(rows, make_item)
