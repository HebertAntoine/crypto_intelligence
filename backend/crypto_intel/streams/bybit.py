"""Live Bybit feeds that no REST endpoint replays: spot trades and liquidations.

    spot    publicTrade.{SYMBOL}      side of the taker ("Buy" / "Sell")
    linear  allLiquidation.{SYMBOL}   every forced liquidation on USDT perps

Bybit documents the liquidation side as the side of the position liquidated:
"Buy" means a long position was liquidated, "Sell" a short one.

Trades and liquidations are summed into hourly buckets and upserted every
minute, so the hour still in progress is always on disk. The minutes the
stream was actually connected are stored per hour: an hour with a gap is
known to be incomplete and the engine discounts it rather than reading a
quiet market into a disconnection.

The process only opens outbound WebSocket connections; it listens on nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import signal
from collections import defaultdict
from datetime import UTC, datetime

from ..core.enums import Asset
from ..history import store
from ..logging_setup import get_logger

log = get_logger(__name__)

SPOT_URL = "wss://stream.bybit.com/v5/public/spot"
LINEAR_URL = "wss://stream.bybit.com/v5/public/linear"
ASSETS = (Asset.BTC, Asset.ETH, Asset.SOL)
FLUSH_SECONDS = 60
PING_SECONDS = 20

SPOT_BUY = "spot.flow.buy_usd.bybit"
SPOT_SELL = "spot.flow.sell_usd.bybit"
LIQ_LONG = "liq.long_usd.bybit"
LIQ_SHORT = "liq.short_usd.bybit"
SPOT_MINUTES = "stream.bybit_spot.minutes"
LIQ_MINUTES = "stream.bybit_liq.minutes"


def hour_of(ms: int) -> datetime:
    moment = datetime.fromtimestamp(ms / 1000, UTC)
    return moment.replace(minute=0, second=0, microsecond=0)


class Buckets:
    """(asset, metric, hour) -> value, plus the minutes each feed was live."""

    def __init__(self) -> None:
        self.values: dict[tuple[Asset, str, datetime], float] = defaultdict(float)
        self.minutes: dict[tuple[str, datetime], set[int]] = defaultdict(set)

    def add_trade(self, asset: Asset, ms: int, side: str, price: float, size: float) -> None:
        metric = SPOT_BUY if side == "Buy" else SPOT_SELL
        self.values[(asset, metric, hour_of(ms))] += price * size

    def add_liquidation(self, asset: Asset, ms: int, side: str, price: float, size: float) -> None:
        metric = LIQ_LONG if side == "Buy" else LIQ_SHORT
        self.values[(asset, metric, hour_of(ms))] += price * size

    def mark_alive(self, feed: str, now: datetime) -> None:
        self.minutes[(feed, now.replace(minute=0, second=0, microsecond=0))].add(now.minute)


def _asset(symbol: str) -> Asset | None:
    for asset in ASSETS:
        if symbol == f"{asset.value}USDT":
            return asset
    return None


def handle_message(buckets: Buckets, raw: str) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return
    topic = str(message.get("topic", ""))
    data = message.get("data")
    if not topic or not isinstance(data, list):
        return
    for item in data:
        try:
            asset = _asset(str(item["s"]))
            if asset is None:
                continue
            if topic.startswith("publicTrade."):
                buckets.add_trade(asset, int(item["T"]), str(item["S"]), float(item["p"]), float(item["v"]))
            elif topic.startswith("allLiquidation."):
                buckets.add_liquidation(asset, int(item["T"]), str(item["S"]), float(item["p"]), float(item["v"]))
        except (KeyError, TypeError, ValueError):
            continue


class BybitStream:
    def __init__(self) -> None:
        self.buckets = Buckets()
        self.lock = asyncio.Lock()
        self.stop = asyncio.Event()
        # What is on disk for the current hours, so a restart adds to it.
        self._base: dict[tuple[Asset, str, datetime], float] = {}

    async def _feed(self, url: str, topics: list[str], feed: str) -> None:
        import websockets

        backoff = 1
        while not self.stop.is_set():
            try:
                async with websockets.connect(url, ping_interval=None, open_timeout=15) as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": topics}))
                    backoff = 1
                    last_ping = asyncio.get_running_loop().time()
                    while not self.stop.is_set():
                        now_loop = asyncio.get_running_loop().time()
                        if now_loop - last_ping > PING_SECONDS:
                            await ws.send(json.dumps({"op": "ping"}))
                            last_ping = now_loop
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=PING_SECONDS)
                        except TimeoutError:
                            raw = None
                        # An open connection with no liquidation this minute
                        # is a quiet market, not a gap.
                        async with self.lock:
                            if raw is not None:
                                handle_message(self.buckets, raw)
                            self.buckets.mark_alive(feed, datetime.now(UTC))
            except Exception as exc:
                log.warning("bybit_stream_reconnect", feed=feed, error=str(exc), backoff=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _alive_ticker(self) -> None:
        while not self.stop.is_set():
            await asyncio.sleep(FLUSH_SECONDS)
            await self.flush()

    async def flush(self) -> None:
        async with self.lock:
            values = dict(self.buckets.values)
            minutes = {k: len(v) for k, v in self.buckets.minutes.items()}
            current = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
            # Closed hours are final: drop them from memory once written.
            for key in [k for k in self.buckets.values if k[2] < current]:
                self.buckets.values.pop(key, None)
            for key in [k for k in self.buckets.minutes if k[1] < current]:
                self.buckets.minutes.pop(key, None)
        try:
            for (asset, metric, hour), value in values.items():
                base = self._base.setdefault((asset, metric, hour), _stored(asset, metric, hour))
                store.upsert_derivatives(asset, metric, [(hour, base + value)],
                                         source="Bybit (flux public en direct)")
                if hour < current:
                    self._base.pop((asset, metric, hour), None)
            for (feed, hour), count in minutes.items():
                metric = SPOT_MINUTES if feed == "spot" else LIQ_MINUTES
                for asset in ASSETS:
                    store.upsert_derivatives(asset, metric, [(hour, float(min(count, 60)))],
                                             source="Bybit (couverture du flux)")
        except Exception as exc:
            log.warning("bybit_stream_flush_failed", error=str(exc))

    async def run(self) -> None:
        spot_topics = [f"publicTrade.{a.value}USDT" for a in ASSETS]
        liq_topics = [f"allLiquidation.{a.value}USDT" for a in ASSETS]
        tasks = [
            asyncio.create_task(self._feed(SPOT_URL, spot_topics, "spot")),
            asyncio.create_task(self._feed(LINEAR_URL, liq_topics, "liq")),
            asyncio.create_task(self._alive_ticker()),
        ]
        await self.stop.wait()
        await self.flush()
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def _stored(asset: Asset, metric: str, hour: datetime) -> float:
    series = store.load_derivatives(asset, metric, start=hour)
    if series.empty:
        return 0.0
    first = series.index[0]
    return float(series.iloc[0]) if first.to_pydatetime() == hour else 0.0


def main() -> None:
    from ..db.session import init_db

    init_db()
    stream = BybitStream()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stream.stop.set)
    loop.run_until_complete(stream.run())


if __name__ == "__main__":
    main()
