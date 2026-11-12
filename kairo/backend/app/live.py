"""Live prices pushed to the browser.

One shared upstream feed serves every open browser tab:
- Finnhub WebSocket (needs a real FINNHUB_API_KEY): every trade, milliseconds after it prints.
- Fallback: polls Yahoo Finance every couple of seconds (no key needed).

Browsers subscribe through /api/ticks (Server-Sent Events). Ticks are merged
per symbol and sent at most every THROTTLE seconds, which is faster than a
screen can usefully show.
"""

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import httpx

from .config import settings

log = logging.getLogger("kairo.live")
NY = ZoneInfo("America/New_York")
THROTTLE = 0.25
POLL_EVERY = 2.0
MAX_SYMBOLS = 30
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; kairo/0.1)"}


def market_status(now: datetime | None = None) -> str:
    """Regular US session, by the clock. Doesn't know about holidays."""
    local = (now or datetime.now(tz=NY)).astimezone(NY)
    if local.weekday() >= 5:
        return "closed"
    t = local.time()
    if dtime(9, 30) <= t < dtime(16, 0):
        return "open"
    if dtime(4, 0) <= t < dtime(9, 30):
        return "pre-market"
    if dtime(16, 0) <= t < dtime(20, 0):
        return "after-hours"
    return "closed"


@dataclass
class Tick:
    symbol: str
    price: float
    ts: float  # exchange time, seconds
    volume: float = 0.0
    prev_close: float | None = None
    received: float = field(default_factory=time.time)

    def to_json(self) -> dict:
        d = {"s": self.symbol, "p": round(self.price, 4), "t": int(self.ts * 1000),
             "v": self.volume, "lag_ms": max(0, int((self.received - self.ts) * 1000))}
        if self.prev_close:
            d["pc"] = self.prev_close
            d["dp"] = round((self.price / self.prev_close - 1) * 100, 3)
        return d


def parse_finnhub(message: str) -> list[Tick]:
    """Turn a Finnhub WebSocket message into ticks (last trade per symbol)."""
    msg = json.loads(message)
    if msg.get("type") != "trade":
        return []
    last: dict[str, Tick] = {}
    for tr in msg.get("data") or []:
        sym, price, ts = tr.get("s"), tr.get("p"), tr.get("t")
        if not sym or price is None or ts is None:
            continue
        tick = Tick(sym, float(price), ts / 1000, float(tr.get("v") or 0))
        if sym not in last or tick.ts >= last[sym].ts:
            last[sym] = tick
    return list(last.values())


class TickHub:
    def __init__(self) -> None:
        self.latest: dict[str, Tick] = {}
        self.prev_close: dict[str, float] = {}
        self.refs: dict[str, int] = {}
        self.listeners: set[asyncio.Queue] = set()
        self.source = "starting"
        self._task: asyncio.Task | None = None
        self._ws = None

    # ---- subscriptions -------------------------------------------------
    async def subscribe(self, symbols: list[str]) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.listeners.add(q)
        for s in symbols[:MAX_SYMBOLS]:
            self.refs[s] = self.refs.get(s, 0) + 1
            if self.refs[s] == 1:
                await self._ws_send({"type": "subscribe", "symbol": s})
        self._ensure_running()
        return q

    async def unsubscribe(self, q: asyncio.Queue, symbols: list[str]) -> None:
        self.listeners.discard(q)
        for s in symbols[:MAX_SYMBOLS]:
            self.refs[s] = self.refs.get(s, 1) - 1
            if self.refs[s] <= 0:
                self.refs.pop(s, None)
                await self._ws_send({"type": "unsubscribe", "symbol": s})

    def _publish(self, tick: Tick) -> None:
        tick.prev_close = tick.prev_close or self.prev_close.get(tick.symbol)
        self.latest[tick.symbol] = tick
        for q in list(self.listeners):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(tick)

    # ---- upstream ------------------------------------------------------
    def _ensure_running(self) -> None:
        if self.source == "starting":
            real_key = settings.finnhub_api_key and settings.finnhub_api_key != "proxy-injected"
            self.source = "connecting" if real_key else "polling"
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _ws_send(self, msg: dict) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.send(json.dumps(msg))

    async def _run(self) -> None:
        async with httpx.AsyncClient(timeout=settings.timeout) as client:
            poller = asyncio.create_task(self._poll(client))
            try:
                if settings.finnhub_api_key and settings.finnhub_api_key != "proxy-injected":
                    await self._finnhub_ws()
                await poller
            finally:
                poller.cancel()

    async def _finnhub_ws(self) -> None:
        """Stream trades from Finnhub; on repeated failure, leave polling in charge."""
        import websockets

        url = f"wss://ws.finnhub.io?token={settings.finnhub_api_key}"
        failures = 0
        while self.refs and failures < 5:
            try:
                async with websockets.connect(url, open_timeout=10, ping_interval=20) as ws:
                    self._ws, failures = ws, 0
                    self.source = "finnhub-stream"
                    for s in list(self.refs):
                        await ws.send(json.dumps({"type": "subscribe", "symbol": s}))
                    async for message in ws:
                        for tick in parse_finnhub(message):
                            self._publish(tick)
            except Exception as e:  # network blip or bad key: retry, then give up
                failures += 1
                log.warning("Finnhub stream error (%s); retry %d", e, failures)
                await asyncio.sleep(min(30, 2 ** failures))
            finally:
                self._ws = None
        self.source = "polling"

    async def _quote(self, client: httpx.AsyncClient, symbol: str) -> None:
        r = await client.get(YAHOO.format(symbol=symbol), headers=HEADERS,
                             params={"range": "1d", "interval": "1m"})
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if prev:
            self.prev_close[symbol] = prev
        price, ts = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
        if price is None or ts is None:
            return
        old = self.latest.get(symbol)
        # While the stream is live it is fresher; polling only fills gaps.
        if old and self.source == "finnhub-stream" and time.time() - old.received < 10:
            return
        if not old or old.price != price or old.ts != ts:
            self._publish(Tick(symbol, float(price), float(ts), prev_close=prev))

    async def _poll(self, client: httpx.AsyncClient) -> None:
        if self.source == "starting":
            self.source = "polling"
        while self.refs:
            symbols = list(self.refs)
            await asyncio.gather(*(self._quote(client, s) for s in symbols), return_exceptions=True)
            await asyncio.sleep(POLL_EVERY)


hub = TickHub()


async def tick_events(symbols: list[str]):
    """SSE generator: a snapshot of the latest prices, then throttled updates."""
    q = await hub.subscribe(symbols)
    try:
        yield _event("status", {"source": hub.source, "market": market_status()})
        for s in symbols:
            if s in hub.latest:
                yield _event("tick", hub.latest[s].to_json())
        pending: dict[str, Tick] = {}
        last_flush = 0.0
        last_status = time.monotonic()
        while True:
            try:
                tick = await asyncio.wait_for(q.get(), timeout=THROTTLE)
                if tick.symbol in symbols:
                    pending[tick.symbol] = tick
            except asyncio.TimeoutError:
                pass
            now = time.monotonic()
            if pending and now - last_flush >= THROTTLE:
                for t in pending.values():
                    yield _event("tick", t.to_json())
                pending.clear()
                last_flush = now
            if now - last_status > 15:
                yield _event("status", {"source": hub.source, "market": market_status()})
                last_status = now
    finally:
        await hub.unsubscribe(q, symbols)


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"
