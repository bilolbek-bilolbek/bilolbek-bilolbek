"""Picks the analyzer: OpenAI when a key is set, otherwise the offline fallback."""

import time

from ..config import settings
from ..models import Analysis, MarketContext
from . import heuristic, openai_analyzer


async def explain(ctx: MarketContext) -> Analysis:
    start = time.perf_counter()
    warnings: list[str] = []
    result: Analysis | None = None
    if settings.openai_api_key:
        try:
            result = await openai_analyzer.analyze(ctx, settings.openai_api_key, settings.openai_model)
        except Exception as e:  # any API problem: fall back rather than show nothing
            warnings.append(f"OpenAI analysis failed ({type(e).__name__}: {str(e)[:120]}); "
                            "used offline analyzer")
    if result is None:
        result = heuristic.analyze(ctx)
    result.latency_ms = int((time.perf_counter() - start) * 1000)
    result.warnings = warnings + result.warnings
    return result
