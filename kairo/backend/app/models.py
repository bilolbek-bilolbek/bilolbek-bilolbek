from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Where a piece of news sits relative to the stock.
Bucket = Literal["company", "peers_supply_chain", "sector", "macro", "geopolitics"]
# What kind of reason a driver is. "market_flow" = the whole market moved.
Category = Literal["company", "peers_supply_chain", "sector", "macro", "geopolitics", "market_flow"]
Window = Literal["1d", "5d", "1mo"]


class PricePoint(BaseModel):
    t: datetime
    price: float


class PriceMove(BaseModel):
    symbol: str
    last: float
    reference: float  # previous close (1d) or first price in the window
    change_pct: float
    high: float
    low: float


class NewsItem(BaseModel):
    id: str
    headline: str
    summary: str = ""
    source: str
    url: str | None = None
    published_at: datetime
    bucket: Bucket
    # When the story was first seen by a data provider (Tiingo's crawlDate), if known.
    # This is when traders could actually have known it.
    available_at: datetime | None = None
    # Stock % move from just before this headline to shortly after it (None if off-chart).
    reaction_pct: float | None = None


class MarketContext(BaseModel):
    ticker: str
    company: str
    sector: str
    window: Window
    stock: PriceMove
    benchmark: PriceMove | None = None  # SPY
    sector_etf: PriceMove | None = None
    excess_vs_market_pct: float | None = None
    excess_vs_sector_pct: float | None = None
    series: list[PricePoint]
    news: list[NewsItem]
    is_sample: bool = False
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime


class Driver(BaseModel):
    title: str
    explanation: str
    category: Category
    direction: Literal["up", "down"]
    likelihood: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class Analysis(BaseModel):
    ticker: str
    summary: str
    drivers: list[Driver]
    unexplained: float = Field(ge=0, le=1)
    confidence: Literal["low", "medium", "high"]
    watch_next: list[str] = Field(default_factory=list)
    engine: str
    latency_ms: int = 0  # how long the AI took when this answer was made
    analyzed_at: datetime | None = None
    from_cache: bool = False  # True when served instantly from a pre-computed answer
    served_ms: float = 0  # how long this request took on the server
    warnings: list[str] = Field(default_factory=list)
