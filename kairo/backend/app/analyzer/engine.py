"""Picks the analyzer: OpenAI when a key is set, otherwise the offline fallback."""

import time
from datetime import datetime, timezone

import openai

from ..config import settings
from ..models import Analysis, MarketContext
from . import heuristic, openai_analyzer

# After OpenAI says "rate limited" we stop asking for a while instead of
# wasting a request (and a few seconds) on every click.
_paused_until = 0.0
_pause_reason = ""


def ai_available() -> bool:
    return bool(settings.openai_api_key) and time.time() >= _paused_until


def ai_status() -> str:
    if not settings.openai_api_key:
        return "off"
    if time.time() < _paused_until:
        return f"paused: {_pause_reason}"
    return "on"


def is_rate_limit(e: Exception) -> bool:
    """OpenAI reports limits as RateLimitError, or as a plain APIError mid-stream."""
    return isinstance(e, openai.RateLimitError) or "rate limit" in str(e).lower()


def _pause(e: Exception) -> None:
    global _paused_until, _pause_reason
    msg = str(e)
    if "credits" in msg or "per day" in msg or "quota" in msg or "(RPD)" in msg:
        _paused_until, _pause_reason = time.time() + 30 * 60, "OpenAI daily limit or no credits"
    else:
        _paused_until, _pause_reason = time.time() + 60, "OpenAI rate limit"


async def explain(ctx: MarketContext) -> Analysis:
    start = time.perf_counter()
    warnings: list[str] = []
    result: Analysis | None = None
    if settings.openai_api_key and not ai_available():
        warnings.append(f"AI {ai_status()}; showing the offline analyzer")
    elif settings.openai_api_key:
        try:
            result = await openai_analyzer.analyze(
                ctx, settings.openai_api_key, settings.openai_model, settings.openai_reasoning)
        except Exception as e:  # any API problem: fall back rather than show nothing
            if is_rate_limit(e):
                _pause(e)
                warnings.append(f"AI {ai_status()}; showing the offline analyzer")
            else:
                warnings.append(f"OpenAI analysis failed ({type(e).__name__}: {str(e)[:120]}); "
                            "used offline analyzer")
    if result is None:
        result = heuristic.analyze(ctx)
    result.latency_ms = int((time.perf_counter() - start) * 1000)
    result.analyzed_at = datetime.now(timezone.utc)
    result.warnings = warnings + result.warnings
    return result
