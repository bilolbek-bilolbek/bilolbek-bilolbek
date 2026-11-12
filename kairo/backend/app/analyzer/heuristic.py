"""Offline fallback analyzer: rule-based, no AI model needed.

It scores each headline by how close it is to the company (bucket), how recent
it is, and whether its tone matches the price move. Headlines are grouped into
themes and the scores are turned into likelihoods. It is much simpler than the
AI path and exists so the app still works with no OpenAI key.
"""

import math
import re
from collections import defaultdict
from datetime import datetime, timezone

from ..models import Analysis, Driver, MarketContext, NewsItem

BUCKET_WEIGHT = {"company": 1.0, "peers_supply_chain": 0.6, "sector": 0.55,
                 "macro": 0.4, "geopolitics": 0.45}

POSITIVE = ["beat", "beats", "surge", "jump", "jumps", "soar", "rally", "upgrade", "upgrades",
            "raise", "raises", "record", "strong", "approval", "approves", "wins", "deal",
            "growth", "lifting", "rises", "gains", "easing", "progress", "buyback", "outperform"]
NEGATIVE = ["resigns", "resign", "ousted", "tumbles", "tumble", "selloff", "sell-off", "slump", "sinks",
            "miss", "misses", "cut", "cuts", "slide", "slides", "fall", "falls", "plunge",
            "drop", "drops", "downgrade", "downgrades", "probe", "lawsuit", "recall", "weak",
            "weaker", "warns", "warning", "delay", "delays", "ban", "tariff", "tariffs",
            "sanctions", "fine", "investigation", "review", "uncertainty", "worries", "rattles",
            "layoffs", "slowing", "weighing", "underperform"]

THEMES = [
    ("Leadership change", r"\b(ceo|chief executive|resign\w*|steps? down|stepping down|appoint\w*|successor|ousted|fired)\b"),
    ("Earnings & guidance", r"\b(earnings?|revenue|guidance|outlook|quarter(ly)?|profits?|estimates|results)\b"),
    ("Analyst rating change", r"\b(analysts?|upgrades?|downgrades?|price target|rating)\b"),
    ("Regulation & legal", r"\b(regulat\w*|probe|antitrust|lawsuit|fine[ds]?|court|ftc|sec|review)\b"),
    ("Trade & geopolitics", r"\b(tariffs?|sanctions?|exports?|china|taiwan|trade|geopolitic\w*|war|tensions?)\b"),
    ("Rates & the economy", r"\b(fed|federal reserve|inflation|yields?|interest rates?|jobs|economy|cpi)\b"),
    ("Products & demand", r"\b(products?|launch\w*|demand|orders|sales|deliveries|subscribers)\b"),
    ("Supply chain", r"\b(suppliers?|supply|production|shortages?|factor(y|ies))\b"),
]

CATEGORY_LABEL = {"company": "Company news", "peers_supply_chain": "Competitors & supply chain",
                  "sector": "Sector moves", "macro": "Economy", "geopolitics": "Geopolitics"}


def tone(text: str) -> int:
    words = re.findall(r"[a-z]+", text.lower())
    return sum(w in POSITIVE for w in words) - sum(w in NEGATIVE for w in words)


def theme(item: NewsItem) -> str:
    text = item.headline.lower()
    for name, pattern in THEMES:
        if re.search(pattern, text):
            return name
    return CATEGORY_LABEL[item.bucket]


def _score(item: NewsItem, move_pct: float, now: datetime) -> float:
    sign = 1 if move_pct >= 0 else -1
    hours = max(0.0, (now - item.published_at).total_seconds() / 3600)
    recency = math.exp(-hours / 24)
    t = tone(item.headline + " " + item.summary)
    # Headlines whose tone matches the move explain it better.
    alignment = 1.0 + 0.8 * (1 if t * sign > 0 else -0.6 if t * sign < 0 else 0)
    # Did the price actually react right after the headline, in the same direction?
    timing = 1.0
    if item.reaction_pct is not None and abs(move_pct) > 0.05:
        share = item.reaction_pct / move_pct  # >0 means same direction
        timing = 1.0 + 2.0 * min(1.0, share) if share > 0 else 0.6
    return BUCKET_WEIGHT[item.bucket] * (0.3 + recency) * max(alignment, 0.1) * timing


def analyze(ctx: MarketContext) -> Analysis:
    move = ctx.stock.change_pct
    sign = 1 if move >= 0 else -1
    now = datetime.now(timezone.utc)
    direction = "up" if sign > 0 else "down"

    groups: dict[str, list[tuple[float, NewsItem]]] = defaultdict(list)
    for it in ctx.news:
        t = tone(it.headline + " " + it.summary)
        if t * sign < 0:
            continue  # pushes the other way; not an explanation for this move
        groups[theme(it)].append((_score(it, move, now), it))

    candidates = []
    for name, scored in groups.items():
        scored.sort(key=lambda x: x[0], reverse=True)
        total = scored[0][0] + 0.3 * sum(s for s, _ in scored[1:])
        candidates.append((total, name, scored[0][1].bucket, [it for _, it in scored[:3]]))
    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:3]

    # How much of the move is just the whole market moving.
    market_share = 0.0
    if ctx.benchmark and abs(move) > 0.05:
        same_way = ctx.benchmark.change_pct * sign > 0
        market_share = min(0.6, abs(ctx.benchmark.change_pct) / abs(move)) if same_way else 0.0

    news_mass = sum(c[0] for c in candidates)
    unexplained = 0.15 if candidates else 0.6
    news_share = max(0.0, 1 - unexplained - market_share)
    drivers = []
    for total, name, bucket, items in candidates:
        lead = items[0]
        reaction = (f" The stock moved {lead.reaction_pct:+.2f}% right after it."
                    if lead.reaction_pct is not None else "")
        drivers.append(Driver(
            title=name,
            explanation=f"Lead headline: \"{lead.headline}\" ({lead.source}).{reaction}"
                        + (f" Plus {len(items) - 1} related." if len(items) > 1 else ""),
            category=bucket, direction=direction,
            likelihood=round(news_share * total / news_mass, 3) if news_mass else 0.0,
            evidence_ids=[it.id for it in items],
        ))
    if market_share >= 0.05 and ctx.benchmark:
        drivers.append(Driver(
            title="Whole-market move",
            explanation=f"The S&P 500 (SPY) moved {ctx.benchmark.change_pct:+.2f}% in the same "
                        f"direction, so part of this move is market-wide.",
            category="market_flow", direction=direction, likelihood=round(market_share, 3)))
    drivers.sort(key=lambda d: d.likelihood, reverse=True)
    unexplained = round(max(0.0, 1 - sum(d.likelihood for d in drivers)), 3)

    top = drivers[0].title.lower() if drivers else "no clear catalyst"
    summary = (f"{ctx.company} is {direction} {abs(move):.2f}% "
               f"({ctx.excess_vs_market_pct:+.2f}% vs the market). " if ctx.excess_vs_market_pct
               is not None else f"{ctx.company} is {direction} {abs(move):.2f}%. ")
    summary += f"Most likely driver: {top}." if drivers else "No news clearly explains the move."
    confidence = "medium" if drivers and drivers[0].likelihood > 0.35 else "low"
    return Analysis(
        ticker=ctx.ticker, summary=summary, drivers=drivers, unexplained=unexplained,
        confidence=confidence, engine="heuristic (offline)",
        watch_next=["Follow-up headlines on the top driver",
                    "Whether the move holds into the close",
                    "Moves in peers and the sector ETF"],
    )
