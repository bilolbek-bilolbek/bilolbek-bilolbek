"""News from Finnhub (needs a free key) and Google News / Yahoo RSS (no key).

Each stock gets five "buckets" of news: the company itself, its peers and
supply chain, its sector, the economy (macro) and geopolitics.
"""

import asyncio
import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ..models import Bucket, NewsItem, Window
from ..universe import Profile

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; kairo/0.1)"}
LOOKBACK = {"1d": timedelta(days=2), "5d": timedelta(days=7), "1mo": timedelta(days=31)}
GOOGLE_WHEN = {"1d": "2d", "5d": "7d", "1mo": "30d"}
PER_BUCKET = {"company": 12, "peers_supply_chain": 6, "sector": 6, "macro": 6, "geopolitics": 6}

_TAG = re.compile(r"<[^>]+>")

# Well-known financial and news outlets get priority when a group has too many headlines.
TRUSTED = {
    "reuters", "bloomberg", "cnbc", "the wall street journal", "wsj", "financial times",
    "barron's", "marketwatch", "yahoo finance", "associated press", "ap news", "the new york times",
    "axios", "business insider", "fortune", "forbes", "nikkei asia", "the information",
    "investor's business daily", "benzinga", "seeking alpha", "the economist", "bbc", "cnn",
    "fox business", "politico", "the washington post", "techcrunch", "the verge", "finnhub",
}


def is_trusted(source: str) -> bool:
    return source.strip().lower() in TRUSTED


def mentions(p: Profile, text: str) -> bool:
    """Does this text talk about the company itself?"""
    names = {p.name} | ({p.name.split()[0]} if len(p.name.split()[0]) > 3 else set())
    if any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in names):
        return True
    return re.search(rf"\b\$?{re.escape(p.ticker)}\b", text) is not None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _key(headline: str) -> str:
    return re.sub(r"[^a-z0-9]", "", headline.lower())[:80]


def _item(headline: str, source: str, published: datetime, bucket: Bucket,
          url: str | None = None, summary: str = "") -> NewsItem:
    digest = hashlib.sha1(f"{headline}|{source}".encode()).hexdigest()[:10]
    return NewsItem(id=digest, headline=_clean(headline), summary=_clean(summary)[:400],
                    source=source, url=url, published_at=published, bucket=bucket)


def _or(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' if " " in t else t for t in terms)


def build_queries(p: Profile) -> list[tuple[Bucket, str]]:
    """Google News searches for everything around the company."""
    queries: list[tuple[Bucket, str]] = []
    related = p.peers + p.supply_chain
    if related:
        queries.append(("peers_supply_chain", _or(related)))
    if p.sector_terms:
        queries.append(("sector", _or(p.sector_terms)))
    if p.macro_terms:
        queries.append(("macro", _or(p.macro_terms)))
    if p.geo_terms:
        queries.append(("geopolitics", _or(p.geo_terms)))
    return queries


async def finnhub_company(client: httpx.AsyncClient, ticker: str, window: Window,
                          token: str) -> list[NewsItem]:
    today = datetime.now(timezone.utc).date()
    start = today - LOOKBACK[window]
    r = await client.get("https://finnhub.io/api/v1/company-news", headers={"X-Finnhub-Token": token},
                         params={"symbol": ticker, "from": start.isoformat(), "to": today.isoformat()})
    r.raise_for_status()
    return [
        _item(a["headline"], a.get("source", "Finnhub"),
              datetime.fromtimestamp(a["datetime"], tz=timezone.utc), "company",
              a.get("url"), a.get("summary", ""))
        for a in r.json() if a.get("headline") and a.get("datetime")
    ]


async def finnhub_general(client: httpx.AsyncClient, window: Window, token: str) -> list[NewsItem]:
    r = await client.get("https://finnhub.io/api/v1/news", headers={"X-Finnhub-Token": token},
                         params={"category": "general"})
    r.raise_for_status()
    cutoff = datetime.now(timezone.utc) - LOOKBACK[window]
    items = []
    for a in r.json():
        if not a.get("headline") or not a.get("datetime"):
            continue
        published = datetime.fromtimestamp(a["datetime"], tz=timezone.utc)
        if published >= cutoff:
            items.append(_item(a["headline"], a.get("source", "Finnhub"), published, "macro",
                               a.get("url"), a.get("summary", "")))
    return items


def _parse_rss(text: str, bucket: Bucket, default_source: str) -> list[NewsItem]:
    feed = feedparser.parse(text)
    items = []
    for e in feed.entries:
        title = e.get("title", "")
        if not title:
            continue
        source = (e.get("source") or {}).get("title") or default_source
        # Google News appends " - Source" to every title.
        if title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            published = parsedate_to_datetime(e.get("published", ""))
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        items.append(_item(title, source, published, bucket, e.get("link"), e.get("summary", "")))
    return items


async def google_news(client: httpx.AsyncClient, query: str, bucket: Bucket,
                      window: Window) -> list[NewsItem]:
    r = await client.get("https://news.google.com/rss/search", headers=HEADERS, params={
        "q": f"{query} when:{GOOGLE_WHEN[window]}", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    r.raise_for_status()
    return _parse_rss(r.text, bucket, "Google News")


async def yahoo_rss(client: httpx.AsyncClient, ticker: str) -> list[NewsItem]:
    r = await client.get("https://feeds.finance.yahoo.com/rss/2.0/headline", headers=HEADERS,
                         params={"s": ticker, "region": "US", "lang": "en-US"})
    r.raise_for_status()
    return _parse_rss(r.text, "company", "Yahoo Finance")


async def gather_news(client: httpx.AsyncClient, p: Profile, window: Window,
                      finnhub_token: str) -> tuple[list[NewsItem], list[str], list[str]]:
    """Fetch every bucket at once. Returns (items, sources used, warnings)."""
    jobs: list[tuple[str, asyncio.Future]] = []
    company_query = f'"{p.name}" stock' if p.name != p.ticker else f"{p.ticker} stock"
    if finnhub_token:
        jobs.append(("Finnhub company news", finnhub_company(client, p.ticker, window, finnhub_token)))
        jobs.append(("Finnhub market news", finnhub_general(client, window, finnhub_token)))
    jobs.append(("Yahoo Finance RSS", yahoo_rss(client, p.ticker)))
    jobs.append(("Google News", google_news(client, company_query, "company", window)))
    for bucket, q in build_queries(p):
        jobs.append(("Google News", google_news(client, q, bucket, window)))

    results = await asyncio.gather(*(j for _, j in jobs), return_exceptions=True)
    sources, warnings, collected = set(), [], []
    for (name, _), res in zip(jobs, results):
        if isinstance(res, Exception):
            warnings.append(f"{name} unavailable ({type(res).__name__})")
            continue
        sources.add(name)
        collected.extend(res)

    cutoff = datetime.now(timezone.utc) - LOOKBACK[window]
    # Feeds sometimes mix in unrelated stories; company news must mention the company.
    collected = [it for it in collected
                 if it.bucket != "company" or mentions(p, f"{it.headline} {it.summary}")]
    # Prefer trusted outlets: treat their stories as if they were 6 hours newer when choosing.
    boost = timedelta(hours=6)
    ranked = sorted(collected, reverse=True,
                    key=lambda x: x.published_at + (boost if is_trusted(x.source) else timedelta(0)))
    seen, per_bucket, items = set(), {b: 0 for b in PER_BUCKET}, []
    for it in ranked:
        k = _key(it.headline)
        if it.published_at < cutoff or k in seen or per_bucket[it.bucket] >= PER_BUCKET[it.bucket]:
            continue
        seen.add(k)
        per_bucket[it.bucket] += 1
        items.append(it)
    items.sort(key=lambda x: x.published_at, reverse=True)
    return items, sorted(sources), sorted(set(warnings))
