"""Ask Kairo: follow-up questions about one stock, answered from its prices and headlines."""

import json
from collections.abc import AsyncIterator

from ..config import settings
from ..models import Analysis, MarketContext
from . import engine, openai_analyzer

SYSTEM = """You are Kairo, an assistant inside a trading app that explains why US stocks move.

You get one stock's market context as JSON: its price move, the S&P 500 (SPY) and sector ETF
moves, recent headlines (each with a ref like H3 and the stock's price move right after it),
and Kairo's current verdict on the likely reasons.

Answer the trader's question about this stock.
Rules:
- Base every claim on the context. Cite headlines inline as [H3]. If the context doesn't
  cover the question, say so plainly instead of guessing.
- Never tell the user to buy, sell or hold, and never give price targets. If asked, lay out
  the factors on each side and say Kairo explains moves but doesn't give investment advice.
- You may discuss what could happen next only as scenarios tied to evidence ("if X, then Y
  is likely"), never as a prediction.
- Be brief and concrete: under 120 words unless the user asks for more. Plain English, no
  headers. Numbers with units (%, $).
"""

MAX_HISTORY = 6


def context_json(ctx: MarketContext, analysis: Analysis | None) -> str:
    def move(m):
        return None if m is None else {"symbol": m.symbol, "change_pct": m.change_pct, "last": m.last}

    payload = {
        "ticker": ctx.ticker, "company": ctx.company, "sector": ctx.sector, "window": ctx.window,
        "stock": move(ctx.stock), "spy": move(ctx.benchmark), "sector_etf": move(ctx.sector_etf),
        "excess_vs_market_pct": ctx.excess_vs_market_pct,
        "headlines": [{"ref": f"H{i + 1}", "group": n.bucket, "time": n.published_at.isoformat(timespec="minutes"),
                       "source": n.source, "headline": n.headline, "summary": n.summary[:200],
                       "price_move_after_pct": n.reaction_pct}
                      for i, n in enumerate(ctx.news)],
    }
    if analysis:
        refs = {n.id: f"H{i + 1}" for i, n in enumerate(ctx.news)}
        payload["kairo_verdict"] = {
            "summary": analysis.summary,
            "reasons": [{"title": d.title, "likelihood": d.likelihood, "direction": d.direction,
                         "headlines": [refs[e] for e in d.evidence_ids if e in refs]}
                        for d in analysis.drivers],
            "not_explained": analysis.unexplained,
        }
    return json.dumps(payload, ensure_ascii=False)


async def ask(ctx: MarketContext, analysis: Analysis | None, question: str,
              history: list[dict]) -> AsyncIterator[str]:
    """Yields the answer as it is written."""
    if not settings.openai_api_key:
        yield "Ask Kairo needs an OpenAI key. Add OPENAI_API_KEY to backend/.env and restart."
        return
    if not engine.ai_available():
        yield (f"Ask Kairo is unavailable right now ({engine.ai_status().removeprefix('paused: ')}). "
               "Add credits to the OpenAI account and it comes back on its own.")
        return

    turns = [{"role": m["role"], "content": str(m["content"])[:2000]}
             for m in history[-MAX_HISTORY:] if m.get("role") in ("user", "assistant")]
    messages = [{"role": "developer", "content": "Market context:\n" + context_json(ctx, analysis)},
                *turns, {"role": "user", "content": question[:1000]}]
    extra = {"reasoning": {"effort": settings.openai_reasoning}} if settings.openai_reasoning else {}
    try:
        stream = await openai_analyzer._get_client(settings.openai_api_key).responses.create(
            model=settings.openai_model, instructions=SYSTEM, input=messages, stream=True, **extra)
        async for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta
    except Exception as e:
        if engine.is_rate_limit(e):
            engine._pause(e)
            yield "Ask Kairo hit the OpenAI usage limit. Add credits to the OpenAI account and try again."
        else:
            yield f"\n\nSorry, the AI request failed ({type(e).__name__})."
