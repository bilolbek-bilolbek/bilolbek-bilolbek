"""The main analyzer: asks an OpenAI model to rank the likely reasons for a move."""

import json
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from ..models import Analysis, Category, Driver, MarketContext

SYSTEM = """You are a sell-side market analyst explaining stock moves to a trader in real time.

You get a US stock's price move, how the S&P 500 (SPY) and its sector ETF moved, and recent
headlines tagged by bucket: company, peers_supply_chain, sector, macro, geopolitics.

Your job: rank the most likely reasons the stock moved the way it did.
Rules:
- Explain the move that happened. Do not predict future prices or give buy/sell advice.
- Only use the headlines given. Cite them by id in evidence_ids. Never invent news.
- Separate stock-specific news from market-wide moves. If the stock moved about as much as
  SPY or its sector ETF, a large share belongs to category "market_flow" or "sector".
- A headline only explains the move if its timing and direction fit. Ignore noise.
  price_reaction_pct is how much the stock moved right after that headline (about 30 min
  for 1d, 1h for 5d, 1 day for 1mo; null if it came out before the chart starts). A big
  reaction in the same direction as the move is strong evidence.
- likelihood = your probability that this driver is the main reason for the move.
  Likelihoods plus "unexplained" must add up to 1. Use "unexplained" honestly when the news
  doesn't account for the move.
- 1 to 4 drivers. Short, concrete titles (max 8 words). Explanations: 1-2 sentences, plain
  English, mention the mechanism (e.g. "a supplier delay means fewer units shipped").
- watch_next: 2-3 concrete things that would confirm or weaken the explanation.
"""


class _LLMDriver(BaseModel):
    title: str
    explanation: str
    category: Category
    direction: Literal["up", "down"]
    likelihood: float = Field(description="0 to 1")
    evidence_ids: list[str]


class _LLMAnalysis(BaseModel):
    summary: str = Field(description="One or two sentences: what moved and the most likely why.")
    drivers: list[_LLMDriver]
    unexplained: float = Field(description="0 to 1")
    confidence: Literal["low", "medium", "high"]
    watch_next: list[str]


def _prompt(ctx: MarketContext) -> str:
    def move(m):
        return None if m is None else {"symbol": m.symbol, "change_pct": m.change_pct,
                                       "last": m.last, "high": m.high, "low": m.low}

    # A few points of the intraday path so the model can line up timing with headlines.
    step = max(1, len(ctx.series) // 12)
    path = [{"t": p.t.isoformat(timespec="minutes"), "price": round(p.price, 2)}
            for p in ctx.series[::step]]
    payload = {
        "ticker": ctx.ticker, "company": ctx.company, "sector": ctx.sector, "window": ctx.window,
        "stock": move(ctx.stock), "spy": move(ctx.benchmark), "sector_etf": move(ctx.sector_etf),
        "excess_vs_market_pct": ctx.excess_vs_market_pct,
        "excess_vs_sector_pct": ctx.excess_vs_sector_pct,
        "price_path": path,
        "headlines": [{"id": n.id, "bucket": n.bucket, "time": n.published_at.isoformat(timespec="minutes"),
                       "source": n.source,
                       "first_seen": n.available_at.isoformat(timespec="minutes") if n.available_at else None,
                       "price_reaction_pct": n.reaction_pct, "headline": n.headline, "summary": n.summary[:240]}
                      for n in ctx.news],
    }
    return json.dumps(payload, ensure_ascii=False)


def normalize(drivers: list[Driver], unexplained: float) -> tuple[list[Driver], float]:
    """Make likelihoods + unexplained sum to exactly 1, whatever the model returned."""
    total = sum(max(0.0, d.likelihood) for d in drivers) + max(0.0, unexplained)
    if total <= 0:
        return drivers, 1.0
    for d in drivers:
        d.likelihood = round(max(0.0, d.likelihood) / total, 3)
    drivers.sort(key=lambda d: d.likelihood, reverse=True)
    return drivers, round(max(0.0, 1 - sum(d.likelihood for d in drivers)), 3)


_client: AsyncOpenAI | None = None


def _get_client(api_key: str) -> AsyncOpenAI:
    # Reuse one client so the HTTPS connection stays warm between requests.
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=api_key, timeout=20, max_retries=1)
    return _client


async def analyze(ctx: MarketContext, api_key: str, model: str, reasoning: str = "") -> Analysis:
    client = _get_client(api_key)
    extra = {"reasoning": {"effort": reasoning}} if reasoning else {}
    resp = await client.responses.parse(
        model=model,
        **extra,
        instructions=SYSTEM,
        input=_prompt(ctx),
        text_format=_LLMAnalysis,
    )
    out: _LLMAnalysis = resp.output_parsed
    valid_ids = {n.id for n in ctx.news}
    drivers = [
        Driver(title=d.title, explanation=d.explanation, category=d.category,
               direction=d.direction, likelihood=min(1.0, max(0.0, d.likelihood)),
               evidence_ids=[i for i in d.evidence_ids if i in valid_ids])
        for d in out.drivers[:4]
    ]
    drivers, unexplained = normalize(drivers, out.unexplained)
    return Analysis(ticker=ctx.ticker, summary=out.summary, drivers=drivers,
                    unexplained=unexplained, confidence=out.confidence,
                    watch_next=out.watch_next[:3], engine=f"openai:{model}")
