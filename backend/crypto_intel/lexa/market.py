"""Market data for Lexa plans: one source, stated, for every asset.

    source      Binance spot, pair {ASSET}USDT (the exchange the app's candles
                already come from)
    candles     1h / 4h / 1d / 1w klines; a candle is CLOSED only once its
                close time has passed - the forming candle is flagged
    closes      00:00 UTC daily, every 4 h from 00:00 UTC, on the hour, and
                Monday 00:00 UTC weekly: Binance's own schedule, not a guess
    price       last trade price (ticker)
    €/$         Binance EURUSDT, used only to turn euros into a quantity

Nothing is ever filled in: a missing pair or an unreachable API returns None
and the plan says « prix indisponible ».
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx

from ..logging_setup import get_logger

log = get_logger(__name__)

BINANCE = "https://api.binance.com/api/v3"
PARIS = ZoneInfo("Europe/Paris")
INTERVALS = {"1H": ("1h", timedelta(hours=1)), "4H": ("4h", timedelta(hours=4)),
             "1D": ("1d", timedelta(days=1)), "1W": ("1w", timedelta(weeks=1))}
TIMEFRAME_FR = {"1H": "1 h", "4H": "4 h", "1D": "journalière", "1W": "hebdomadaire"}
SOURCE_FR = "Binance spot, paire {asset}USDT — clôtures à heure fixe UTC"


@dataclass(slots=True)
class Bar:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    closed: bool


def bar_start(moment: datetime, timeframe: str) -> datetime:
    """Start of the Binance candle containing `moment` (UTC)."""

    moment = moment.astimezone(UTC)
    if timeframe == "1H":
        return moment.replace(minute=0, second=0, microsecond=0)
    if timeframe == "4H":
        return moment.replace(hour=moment.hour - moment.hour % 4, minute=0, second=0, microsecond=0)
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if timeframe == "1D":
        return day
    return day - timedelta(days=day.weekday())  # Binance weeks open on Monday


def next_close(moment: datetime, timeframe: str) -> datetime:
    return bar_start(moment, timeframe) + INTERVALS[timeframe][1]


def paris(moment: datetime) -> str:
    """« 22 septembre — 02:00 heure de Paris »"""

    local = moment.astimezone(PARIS)
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre"]
    return f"{local.day} {months[local.month - 1]} — {local:%H:%M} heure de Paris"


def countdown(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} j {hours} h"
    if hours:
        return f"{hours} h {minutes:02d}"
    return f"{minutes} min"


class MarketData(Protocol):
    def bars(self, asset: str, timeframe: str, since: datetime) -> list[Bar] | None: ...
    def price(self, asset: str) -> float | None: ...
    def eurusd(self) -> float | None: ...
    def now(self) -> datetime: ...


class BinanceMarket:
    """Public endpoints only. Cached briefly so a page refresh is cheap."""

    def __init__(self, ttl_bars: float = 60, ttl_price: float = 15) -> None:
        self._cache: dict[tuple, tuple[float, object]] = {}
        self.ttl_bars, self.ttl_price = ttl_bars, ttl_price

    def now(self) -> datetime:
        return datetime.now(UTC)

    def _cached(self, key: tuple, ttl: float, fetch):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        try:
            value = fetch()
        except Exception as exc:  # shown as unavailable, never invented
            log.warning("lexa_market_unavailable", key=str(key), error=str(exc))
            value = None
        self._cache[key] = (time.time(), value)
        return value

    def bars(self, asset: str, timeframe: str, since: datetime) -> list[Bar] | None:
        start = bar_start(since, timeframe)
        return self._cached(("bars", asset, timeframe, start.isoformat()), self.ttl_bars,
                            lambda: self._fetch_bars(asset, timeframe, start))

    def _fetch_bars(self, asset: str, timeframe: str, start: datetime) -> list[Bar] | None:
        interval = INTERVALS[timeframe][0]
        rows: list[list] = []
        cursor = int(start.timestamp() * 1000)
        with httpx.Client(timeout=20) as client:
            for _ in range(15):
                response = client.get(f"{BINANCE}/klines", params={
                    "symbol": f"{asset}USDT", "interval": interval,
                    "startTime": cursor, "limit": 1000})
                if response.status_code == 400:
                    return None  # no such pair on Binance
                response.raise_for_status()
                batch = response.json()
                rows.extend(batch)
                if len(batch) < 1000:
                    break
                cursor = int(batch[-1][0]) + 1
        now = datetime.now(UTC)
        out = []
        for r in rows:
            opened = datetime.fromtimestamp(int(r[0]) / 1000, UTC)
            closes = opened + INTERVALS[timeframe][1]
            out.append(Bar(opened, closes, float(r[1]), float(r[2]), float(r[3]), float(r[4]),
                           closed=closes <= now))
        return out

    def price(self, asset: str) -> float | None:
        def fetch():
            response = httpx.get(f"{BINANCE}/ticker/price", params={"symbol": f"{asset}USDT"},
                                 timeout=10)
            if response.status_code == 400:
                return None
            response.raise_for_status()
            return float(response.json()["price"])
        return self._cached(("price", asset), self.ttl_price, fetch)

    def eurusd(self) -> float | None:
        def fetch():
            response = httpx.get(f"{BINANCE}/ticker/price", params={"symbol": "EURUSDT"},
                                 timeout=10)
            response.raise_for_status()
            return float(response.json()["price"])
        return self._cached(("eurusd",), 300, fetch)


_DEFAULT: BinanceMarket | None = None


def default_market() -> BinanceMarket:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = BinanceMarket()
    return _DEFAULT
