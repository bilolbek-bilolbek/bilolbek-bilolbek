import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.analyzer import heuristic
from app.analyzer.openai_analyzer import normalize
from app.main import app
from app.models import Driver
from app.providers.news import _parse_rss, build_queries
from app.universe import get_profile

client = TestClient(app)


def test_health():
    r = client.get("/api/health").json()
    assert r["ok"] and r["data_mode"] == "sample" and r["ai"].startswith("heuristic")


def test_context_sample_is_labelled_and_consistent():
    ctx = client.get("/api/context/NVDA?window=1d").json()
    assert ctx["is_sample"] is True
    assert ctx["stock"]["symbol"] == "NVDA" and ctx["benchmark"]["symbol"] == "SPY"
    assert ctx["sector_etf"]["symbol"] == "SMH"
    assert len(ctx["series"]) == 78 and ctx["news"]
    assert all(n["source"].startswith("Sample") for n in ctx["news"])


def test_explain_likelihoods_sum_to_one():
    for t in ["AAPL", "TSLA", "XOM", "ZZZZ"]:
        a = client.get(f"/api/explain/{t}").json()
        total = sum(d["likelihood"] for d in a["drivers"]) + a["unexplained"]
        assert abs(total - 1) < 0.01, (t, total)
        assert a["drivers"], t


def test_heuristic_direction_matches_move():
    ctx = client.get("/api/context/AAPL?window=5d").json()
    a = client.get("/api/explain/AAPL?window=5d").json()
    want = "up" if ctx["stock"]["change_pct"] >= 0 else "down"
    assert all(d["direction"] == want for d in a["drivers"])


def test_stream_sends_context_then_analysis():
    with client.stream("GET", "/api/stream/MSFT") as r:
        body = "".join(r.iter_text())
    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events == ["context", "analysis", "done"]
    data = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert data[1]["ticker"] == "MSFT"


def test_bad_ticker_rejected():
    assert client.get("/api/context/$$$").status_code == 400


def test_normalize():
    ds = [Driver(title="a", explanation="", category="company", direction="up", likelihood=0.9),
          Driver(title="b", explanation="", category="macro", direction="up", likelihood=0.6)]
    ds, unexplained = normalize(ds, 0.5)
    assert ds[0].title == "a" and abs(sum(d.likelihood for d in ds) + unexplained - 1) < 1e-6


def test_tone():
    assert heuristic.tone("Analyst upgrades Apple, raises price target") > 0
    assert heuristic.tone("Nvidia shares slide after export ban") < 0


def test_google_rss_parsing():
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    rss = f"""<?xml version="1.0"?><rss><channel><item>
      <title>Chip stocks rally on AI demand - Reuters</title><link>https://example.com/a</link>
      <pubDate>{now.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>
      <source url="https://reuters.com">Reuters</source></item></channel></rss>"""
    items = _parse_rss(rss, "sector", "Google News")
    assert items[0].headline == "Chip stocks rally on AI demand" and items[0].source == "Reuters"


def test_queries_cover_all_buckets():
    buckets = {b for b, _ in build_queries(get_profile("NVDA"))}
    assert buckets == {"peers_supply_chain", "sector", "macro", "geopolitics"}


def test_reaction_measures_move_after_headline():
    from app.context import add_reactions
    from app.models import NewsItem, PricePoint
    t0 = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    series = [PricePoint(t=t0 + timedelta(minutes=5 * i), price=100 + (5 if i >= 3 else 0)) for i in range(12)]
    n = NewsItem(id="x", headline="h", source="s", bucket="company",
                 published_at=t0 + timedelta(minutes=12))
    early = NewsItem(id="y", headline="h2", source="s", bucket="company",
                     published_at=t0 - timedelta(hours=1))
    add_reactions(series, [n, early], "1d")
    assert n.reaction_pct == 5.0 and early.reaction_pct is None


def test_sample_1d_is_inside_market_hours():
    from zoneinfo import ZoneInfo
    ctx = client.get("/api/context/AAPL?window=1d").json()
    first = datetime.fromisoformat(ctx["series"][0]["t"]).astimezone(ZoneInfo("America/New_York"))
    assert (first.hour, first.minute) == (9, 30) and first.weekday() < 5
