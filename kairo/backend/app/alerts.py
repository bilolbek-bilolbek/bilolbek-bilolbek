"""Alerts: tell the trader the moment a stock moves sharply, with the likely reason.

Two rules, checked on every live price:
- Fast move: the price moved FAST_PCT or more within the last FAST_MINUTES.
- Big day: the day's change crossed one of DAY_LEVELS (each level fires once per day).

An alert goes out at once with the reason Kairo already has, then again with a
fresh reason once the AI has looked at the latest news.
"""

import asyncio
import contextlib
import itertools
import json
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import service
from .live import Tick, hub
from .universe import WATCHLIST, get_profile

log = logging.getLogger("kairo.alerts")

FAST_PCT = 1.0
FAST_MINUTES = 15
DAY_LEVELS = (3.0, 5.0, 7.0, 10.0)
COOLDOWN_SECONDS = 20 * 60
KEEP = 50

_ids = itertools.count(1)


@dataclass
class Alert:
    id: int
    ticker: str
    company: str
    kind: str  # "fast" | "day" | "test"
    title: str  # e.g. "NVDA −1.4% in 12 min"
    change_pct: float
    price: float
    reason: str | None = None
    reason_likelihood: float | None = None
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict:
        return asdict(self)


def _sign(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}{abs(x):.1f}%"


class Detector:
    """Pure rule logic, kept apart from the feed so it is easy to test."""

    def __init__(self) -> None:
        self.history: dict[str, deque] = {}
        self.cooldown: dict[tuple[str, str], float] = {}
        self.day_fired: dict[str, set] = {}
        self.day_key: dict[str, str] = {}

    def check(self, tick: Tick, now: float | None = None) -> list[tuple[str, str, float]]:
        """Returns (kind, title, change_pct) for each rule this tick sets off."""
        now = now if now is not None else tick.ts
        out = []
        h = self.history.setdefault(tick.symbol, deque())
        h.append((tick.ts, tick.price))
        while h and tick.ts - h[0][0] > FAST_MINUTES * 60:
            h.popleft()

        # Fast move against the oldest price still inside the window.
        t0, p0 = h[0]
        move = (tick.price / p0 - 1) * 100
        if abs(move) >= FAST_PCT and self._ready(tick.symbol, "fast", now):
            minutes = max(1, round((tick.ts - t0) / 60))
            out.append(("fast", f"{tick.symbol} {_sign(move)} in {minutes} min", round(move, 2)))
            h.clear()
            h.append((tick.ts, tick.price))

        # Big day: crossing a level for the first time today.
        if tick.prev_close:
            day = datetime.fromtimestamp(tick.ts, tz=timezone.utc).date().isoformat()
            change = (tick.price / tick.prev_close - 1) * 100
            if self.day_key.get(tick.symbol) != day:
                # First price we see today: levels already behind us are not news.
                self.day_key[tick.symbol] = day
                self.day_fired[tick.symbol] = {lv for lv in DAY_LEVELS if abs(change) >= lv}
            crossed = [lv for lv in DAY_LEVELS if abs(change) >= lv and lv not in self.day_fired[tick.symbol]]
            if crossed:
                self.day_fired[tick.symbol].update(crossed)
                out.append(("day", f"{tick.symbol} {_sign(change)} today", round(change, 2)))
        return out

    def _ready(self, symbol: str, kind: str, now: float) -> bool:
        if now - self.cooldown.get((symbol, kind), 0) < COOLDOWN_SECONDS:
            return False
        self.cooldown[(symbol, kind)] = now
        return True


class AlertCenter:
    def __init__(self) -> None:
        self.detector = Detector()
        self.recent: deque[Alert] = deque(maxlen=KEEP)
        self.listeners: set[asyncio.Queue] = set()

    def publish(self, alert: Alert) -> None:
        if alert not in self.recent:
            self.recent.append(alert)
        for q in list(self.listeners):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(alert)

    def _attach_reason(self, alert: Alert) -> None:
        stored = service.cached(alert.ticker, "1d")
        if stored and stored.analysis.drivers:
            top = stored.analysis.drivers[0]
            alert.reason, alert.reason_likelihood = top.title, top.likelihood

    async def _refresh_reason(self, alert: Alert) -> None:
        """Re-check the news now, then send the alert again with the fresh reason."""
        try:
            _, analysis, _ = await service.explain_ticker(alert.ticker, "1d")
            if analysis.drivers:
                alert.reason, alert.reason_likelihood = analysis.drivers[0].title, analysis.drivers[0].likelihood
                self.publish(alert)
        except Exception as e:
            log.warning("alert reason for %s failed: %s", alert.ticker, e)

    def raise_alert(self, kind: str, ticker: str, title: str, change: float, price: float) -> Alert:
        alert = Alert(next(_ids), ticker, get_profile(ticker).name, kind, title, change, price)
        self._attach_reason(alert)
        self.publish(alert)
        asyncio.get_running_loop().create_task(self._refresh_reason(alert))
        log.info("alert: %s", title)
        return alert

    def on_tick(self, tick: Tick) -> None:
        for kind, title, change in self.detector.check(tick, time.time()):
            self.raise_alert(kind, tick.symbol, title, change, tick.price)

    async def watch_forever(self, symbols: list[str]) -> None:
        q = await hub.subscribe(symbols)
        try:
            while True:
                self.on_tick(await q.get())
        finally:
            await hub.unsubscribe(q, symbols)


center = AlertCenter()


async def watch_watchlist() -> None:
    await center.watch_forever(list(WATCHLIST))


async def alert_events():
    """SSE: the latest alerts, then new ones as they happen."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    center.listeners.add(q)
    try:
        for a in list(center.recent)[-10:]:
            yield _event(a)
        while True:
            try:
                yield _event(await asyncio.wait_for(q.get(), timeout=20))
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        center.listeners.discard(q)


def _event(a: Alert) -> str:
    return f"event: alert\ndata: {json.dumps(a.to_json())}\n\n"
