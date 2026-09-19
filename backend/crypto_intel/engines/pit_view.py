"""One door to the data, for the live decision and the backtest alike.

Every series is loaded once into a ``DataCache``. A ``PointInTimeView`` then
answers "what was known at ``as_of``": a value is visible only once its
``available_at`` has passed. The live engine is a view at *now*; the backtest
is the same view moved back in time, so both run exactly the same code.

Why this matters: a CPI for August describes August but is published in
mid-September. Reading it on 31 August would make every backtest look better
than any real use could have been.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..core.data_integrity import is_production_label
from ..core.enums import Asset, Timeframe

#: A daily bar from the market-data history is stamped at the session's start;
#: its close is only known a day later.
DAILY_BAR_DELAY = timedelta(days=1)

TIMEFRAME_SPAN = {
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}


@dataclass(frozen=True, slots=True)
class Point:
    timestamp: datetime
    available_at: datetime
    value: float
    source: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _Series:
    """Parallel arrays sorted by timestamp; filtering is a vector comparison."""

    timestamps: np.ndarray
    available: np.ndarray
    values: np.ndarray
    sources: list[str]
    metas: list[dict[str, Any]]

    @classmethod
    def build(cls, points: list[Point]) -> _Series:
        points = sorted(points, key=lambda item: item.timestamp)
        return cls(
            timestamps=np.array([p.timestamp.timestamp() for p in points], dtype=float),
            available=np.array([p.available_at.timestamp() for p in points], dtype=float),
            values=np.array([p.value for p in points], dtype=float),
            sources=[p.source for p in points],
            metas=[p.meta for p in points],
        )

    def known(self, as_of: datetime) -> list[Point]:
        mask = self.available <= as_of.timestamp()
        return [
            Point(
                timestamp=datetime.fromtimestamp(self.timestamps[i], UTC),
                available_at=datetime.fromtimestamp(self.available[i], UTC),
                value=float(self.values[i]),
                source=self.sources[i],
                meta=self.metas[i],
            )
            for i in np.nonzero(mask)[0]
        ]


def _utc(value: Any) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime().astimezone(UTC)


#: Where each metric's history comes from, beyond the observations table.
_STORE_MACRO = {
    "macro.dxy", "macro.vix", "macro.nasdaq", "macro.sp500", "macro.oil_wti",
    "macro.us10y_yahoo",
}
_STORE_DERIVATIVES = {
    "funding.rate", "oi.contracts_bybit", "dvol.index", "spot.taker_buy_ratio",
    "spot.net_taker_volume", "derivatives.long_account_share", "oi.value",
}

#: Hourly buckets (aggressive spot flow, liquidations, stream coverage): an
#: hour is complete - and usable - once it has closed.
_STORE_HOURLY_PREFIXES = ("spot.flow.", "liq.", "stream.")
_HOURLY_SOURCE = {
    "binance": "Binance spot (klines 1 h)",
    "okx": "OKX spot (taker-volume 1 h)",
    "bybit": "Bybit (flux public en direct)",
}


def _is_hourly(metric: str) -> bool:
    return metric.startswith(_STORE_HOURLY_PREFIXES)


class DataCache:
    """Everything one asset's decision can read, loaded once."""

    def __init__(self, database: Path | str | None = None) -> None:
        from ..settings import PROJECT_ROOT

        self.database = Path(database) if database else PROJECT_ROOT / "data" / "crypto_intel.db"
        self._series: dict[tuple[str, str | None], _Series] = {}
        self._candles: dict[tuple[str, str], pd.DataFrame] = {}
        self._meetings: list[tuple[str, datetime, str]] | None = None

    # -- loading ------------------------------------------------------------

    def _observation_points(self, metric: str, asset: str | None) -> list[Point]:
        if not self.database.exists():
            return []
        con = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)
        try:
            if asset is None:
                rows = con.execute(
                    "SELECT timestamp, value_num, source, meta, fetched_at FROM observations "
                    "WHERE metric = ? AND value_num IS NOT NULL",
                    (metric,),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT timestamp, value_num, source, meta, fetched_at FROM observations "
                    "WHERE metric = ? AND asset = ? AND value_num IS NOT NULL",
                    (metric, asset),
                ).fetchall()
        finally:
            con.close()
        out: list[Point] = []
        for stamp, value, source, meta_raw, fetched in rows:
            # Fixtures are never evidence, whatever table they sit in.
            if not is_production_label(source):
                continue
            meta = dict((json.loads(meta_raw) if meta_raw else None) or {})
            if fetched:
                # When this system collected it - distinct from the period the
                # value describes and from when it was published.
                meta["fetched_at"] = _utc(fetched).isoformat()
            ts = _utc(stamp)
            available = _utc(meta["available_at"]) if meta.get("available_at") else ts
            out.append(Point(ts, available, float(value), str(source), meta))
        return out

    def _store_points(self, metric: str, asset: str | None) -> list[Point]:
        from ..history import store

        if _is_hourly(metric) and asset is not None:
            series = store.load_derivatives(Asset(asset), metric)
            source = _HOURLY_SOURCE.get(metric.rsplit(".", 1)[-1], "Bybit (flux public en direct)")
            return [
                Point(_utc(stamp), _utc(stamp) + timedelta(hours=1), float(value), source)
                for stamp, value in series.items()
                if value is not None and np.isfinite(value)
            ]
        if metric in _STORE_MACRO:
            series = store.load_macro(metric)
            source = "Yahoo Finance (historique)"
        elif metric in _STORE_DERIVATIVES and asset is not None:
            series = store.load_derivatives(Asset(asset), metric)
            source = {
                "funding.rate": "Binance Futures (historique)",
                "oi.contracts_bybit": "Bybit (historique)",
                "dvol.index": "Deribit (historique)",
            }.get(metric, "Binance (historique)")
        else:
            return []
        out: list[Point] = []
        daily = metric in _STORE_MACRO or metric in {
            "oi.contracts_bybit", "dvol.index", "spot.taker_buy_ratio",
            "spot.net_taker_volume", "oi.value",
        }
        for stamp, value in series.items():
            if value is None or not np.isfinite(value):
                continue
            ts = _utc(stamp)
            out.append(Point(ts, ts + (DAILY_BAR_DELAY if daily else timedelta(0)), float(value), source))
        return out

    def _etf_points(self, asset: str) -> list[Point]:
        """Daily net flow of every spot ETF of the asset, summed per session.

        Farside publishes a session the next morning; a flow is therefore
        treated as known one day after its date.
        """

        if not self.database.exists():
            return []
        con = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT date, SUM(flow_musd), COUNT(*), GROUP_CONCAT(DISTINCT import_source) "
                "FROM etf_flows WHERE asset = ? GROUP BY date",
                (asset,),
            ).fetchall()
        finally:
            con.close()
        out: list[Point] = []
        for stamp, total, funds, sources in rows:
            if total is None:
                continue
            ts = _utc(stamp)
            source = "Farside Investors" if "farside" in str(sources) else "Import ETF"
            out.append(Point(ts, ts + timedelta(days=1), float(total), source, {"funds": funds}))
        return out

    def series(self, metric: str, asset: str | None = None) -> _Series:
        key = (metric, asset)
        if key not in self._series:
            if metric == "etf.net_flow":
                points = self._etf_points(asset or "")
            else:
                points = self._observation_points(metric, asset) + self._store_points(metric, asset)
                # Two sources for the same moment: keep the observation (it
                # carries provenance and publication time).
                seen: set[float] = set()
                unique: list[Point] = []
                for point in sorted(points, key=lambda p: (p.timestamp, not p.meta)):
                    stamp = point.timestamp.replace(second=0, microsecond=0).timestamp()
                    if stamp in seen:
                        continue
                    seen.add(stamp)
                    unique.append(point)
                points = unique
            self._series[key] = _Series.build(points)
        return self._series[key]

    def meetings(self) -> list[tuple[str, datetime, str]]:
        """Scheduled central-bank decisions: (source, time, title), all dates.

        A meeting date is public long before it happens, so the whole
        calendar is visible to every view.
        """

        if getattr(self, "_meetings", None) is None:
            rows: list[tuple[str, datetime, str]] = []
            if self.database.exists():
                con = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)
                try:
                    for source, stamp, title in con.execute(
                        "SELECT source, scheduled_at, title FROM future_events "
                        "WHERE category = 'MONETARY_POLICY' AND scheduled_at IS NOT NULL"
                    ).fetchall():
                        rows.append((str(source), _utc(stamp), str(title)))
                except sqlite3.Error:
                    rows = []
                finally:
                    con.close()
            self._meetings = sorted(rows, key=lambda r: r[1])
        return self._meetings

    def candles(self, asset: str, timeframe: Timeframe) -> pd.DataFrame:
        key = (asset, timeframe.value)
        if key not in self._candles:
            from ..history import store

            self._candles[key] = store.load_candles(Asset(asset), timeframe)
        return self._candles[key]


class PointInTimeView:
    """What was knowable at ``as_of`` - nothing later."""

    def __init__(self, cache: DataCache, as_of: datetime) -> None:
        self.cache = cache
        self.as_of = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)

    def points(self, metric: str, asset: str | None = None) -> list[Point]:
        return self.cache.series(metric, asset).known(self.as_of)

    def latest(self, metric: str, asset: str | None = None) -> Point | None:
        known = self.points(metric, asset)
        return known[-1] if known else None

    def value_before(
        self, metric: str, moment: datetime, asset: str | None = None
    ) -> Point | None:
        """The last value describing a moment at or before ``moment``."""

        known = [p for p in self.points(metric, asset) if p.timestamp <= moment]
        return known[-1] if known else None

    def candles(self, asset: str, timeframe: Timeframe) -> pd.DataFrame:
        """Only bars that had closed by ``as_of``."""

        frame = self.cache.candles(asset, timeframe)
        if frame.empty:
            return frame
        span = TIMEFRAME_SPAN.get(timeframe, timedelta(0))
        cutoff = pd.Timestamp(self.as_of - span)
        index = frame.index
        if index.tz is None:
            cutoff = cutoff.tz_localize(None)
        return frame[index <= cutoff]
