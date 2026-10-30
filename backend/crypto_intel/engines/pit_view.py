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
from ..core.source_rights import source_is_admissible as _source_is_admissible

#: A daily bar from the market-data history is stamped at the session's start;
#: its close is only known a day later.
DAILY_BAR_DELAY = timedelta(days=1)

TIMEFRAME_SPAN = {
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(weeks=1),
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
        points = sorted(points, key=lambda item: (item.timestamp, item.available_at))
        return cls(
            timestamps=np.array([p.timestamp.timestamp() for p in points], dtype=float),
            available=np.array([p.available_at.timestamp() for p in points], dtype=float),
            values=np.array([p.value for p in points], dtype=float),
            sources=[p.source for p in points],
            metas=[p.meta for p in points],
        )

    def known(self, as_of: datetime) -> list[Point]:
        mask = self.available <= as_of.timestamp()
        # Multiple versions of one observation may exist after a revision.
        # Sorting by (observation, availability) above means assigning by
        # timestamp retains the last version that was actually knowable at
        # ``as_of`` without projecting a later revision backwards.
        by_observation: dict[float, Point] = {}
        for i in np.nonzero(mask)[0]:
            point = Point(
                timestamp=datetime.fromtimestamp(self.timestamps[i], UTC),
                available_at=datetime.fromtimestamp(self.available[i], UTC),
                value=float(self.values[i]),
                source=self.sources[i],
                meta=self.metas[i],
            )
            by_observation[self.timestamps[i]] = point
        return [by_observation[key] for key in sorted(by_observation)]


def _utc(value: Any) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime().astimezone(UTC)


#: Where each metric's history comes from, beyond the observations table.
_STORE_MACRO = {
    "macro.fed_funds_rate", "macro.fed_funds_monthly",
    "macro.us2y", "macro.us10y", "macro.us30y", "macro.yield_curve_10y2y",
    "macro.cpi", "macro.core_cpi", "macro.pce", "macro.core_pce",
    "macro.unemployment", "macro.nonfarm_payrolls", "macro.jobless_claims", "macro.ppi",
    "macro.dxy", "macro.dxy_broad", "macro.vix",
    "macro.nasdaq", "macro.nasdaq100", "macro.sp500", "macro.dow", "macro.russell2000",
    "macro.nikkei225", "macro.eurostoxx50", "macro.eurusd", "macro.usdjpy",
    "macro.brent", "macro.wti", "macro.oil_wti", "macro.hy_spread", "macro.ig_spread",
    "macro.stlfsi4", "macro.nfci", "liquidity.fed_total_assets", "macro.us10y_yahoo",
}
_STORE_DERIVATIVES = {
    "funding.rate", "oi.contracts_bybit", "dvol.index", "spot.taker_buy_ratio",
    "spot.net_taker_volume", "derivatives.long_account_share", "oi.value",
}

_MARKET_DAILY_MACRO = frozenset({
    "macro.dxy", "macro.vix", "macro.nasdaq", "macro.nasdaq100", "macro.sp500",
    "macro.dow", "macro.russell2000", "macro.nikkei225", "macro.eurostoxx50",
    "macro.eurusd", "macro.usdjpy", "macro.brent", "macro.wti", "macro.oil_wti",
    "macro.us10y_yahoo",
})

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
                    "SELECT timestamp, value_num, source, provider, meta, fetched_at, unit, source_url "
                    "FROM observations "
                    "WHERE metric = ? AND value_num IS NOT NULL",
                    (metric,),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT timestamp, value_num, source, provider, meta, fetched_at, unit, source_url "
                    "FROM observations "
                    "WHERE metric = ? AND asset = ? AND value_num IS NOT NULL",
                    (metric, asset),
                ).fetchall()
        finally:
            con.close()
        out: list[Point] = []
        for stamp, value, source, provider, meta_raw, fetched, unit, source_url in rows:
            # Fixtures are never evidence, whatever table they sit in.
            if not is_production_label(source):
                continue
            meta = dict((json.loads(meta_raw) if meta_raw else None) or {})
            if not _source_is_admissible(
                metric,
                source=str(source),
                provider=str(provider or ""),
                source_url=str(source_url or "") or None,
                meta=meta,
            ):
                continue
            if provider and not meta.get("provider"):
                meta["provider"] = str(provider)
            if fetched:
                # When this system collected it - distinct from the period the
                # value describes and from when it was published.
                meta["fetched_at"] = _utc(fetched).isoformat()
            if unit and not meta.get("unit"):
                meta["unit"] = str(unit)
            if source_url and not meta.get("source_url"):
                meta["source_url"] = str(source_url)
            ts = _utc(stamp)
            if meta.get("available_at"):
                available = _utc(meta["available_at"])
                meta.setdefault("availability_basis", "provider_publication_time")
            elif fetched:
                # ``fetched_at`` is not a publication timestamp.  It is only a
                # conservative lower bound: the system demonstrably could not
                # have used this value before it collected it.  Keeping the
                # basis explicit prevents the UI/reporting layer from
                # presenting ingestion as an official release time.
                available = _utc(fetched)
                meta["availability_basis"] = "fetched_at_fallback"
            else:
                # Legacy rows should normally never enter this branch because
                # ``fetched_at`` is non-null in the canonical schema.  Preserve
                # compatibility without relabelling the observation timestamp
                # as a verified publication time.
                available = ts
                meta["availability_basis"] = "observation_time_legacy_fallback"
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
            records = store.load_macro_records(metric)
            out: list[Point] = []
            for record in records:
                source = str(record.get("source") or "")
                provider = str(record.get("provider") or source)
                if not _source_is_admissible(
                    metric,
                    source=source,
                    provider=provider,
                    source_url=str(record.get("source_url") or "") or None,
                    meta=record,
                ):
                    continue
                ts = _utc(record["timestamp"])
                release = record.get("release_time")
                ingested = record.get("ingested_at")
                if release:
                    available = _utc(release)
                elif ingested:
                    available = _utc(ingested)
                elif metric in _MARKET_DAILY_MACRO:
                    available = ts + DAILY_BAR_DELAY
                else:
                    # A legacy macroeconomic value with neither publication nor
                    # ingestion time cannot be placed safely on a historical
                    # timeline.  Keep it in storage, but not in a decision view.
                    continue
                record_meta = dict(record.get("meta") or {})
                out.append(Point(
                    ts,
                    available,
                    float(record["value"]),
                    source or "Historique de marché",
                    {
                        **record_meta,
                        "availability": record.get("availability") or "UNKNOWN",
                        "available_at": available.isoformat(),
                        "provider": provider,
                        "series_id": record.get("series_id"),
                        "unit": record.get("unit"),
                        "source_url": record.get("source_url"),
                        "license_status": record.get("license_status"),
                        "revision_time": (
                            _utc(record["revision_time"]).isoformat()
                            if record.get("revision_time") else None
                        ),
                        "revision_number": int(record.get("revision_number") or 0),
                        "is_first_print": bool(record.get("is_first_print", True)),
                    },
                ))
            return out
        elif metric in _STORE_DERIVATIVES and asset is not None:
            series = store.load_derivatives(Asset(asset), metric)
            source = {
                "funding.rate": "Binance Futures (historique)",
                "oi.contracts_bybit": "Bybit (historique)",
                "dvol.index": "Deribit (historique)",
            }.get(metric, "Binance (historique)")
        else:
            return []
        out = []
        daily = metric in {
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
        cache_key = (metric, asset)
        if cache_key not in self._series:
            if metric == "etf.net_flow":
                points = self._etf_points(asset or "")
            else:
                points = self._observation_points(metric, asset) + self._store_points(metric, asset)
                # Exact duplicates are collapsed, while later vintages of the
                # same observation remain. ``_Series.known`` selects the latest
                # revision that was available at the requested as-of time.
                seen: set[tuple[float, float]] = set()
                unique: list[Point] = []
                for point in sorted(
                    points, key=lambda p: (p.timestamp, p.available_at, not p.meta)
                ):
                    version_key = (
                        point.timestamp.replace(second=0, microsecond=0).timestamp(),
                        point.available_at.replace(second=0, microsecond=0).timestamp(),
                    )
                    if version_key in seen:
                        continue
                    seen.add(version_key)
                    unique.append(point)
                points = unique
            self._series[cache_key] = _Series.build(points)
        return self._series[cache_key]

    def meetings(self) -> list[tuple[str, datetime, str]]:
        """Scheduled central-bank decisions: (source, time, title), all dates.

        A meeting date is public long before it happens, so the whole
        calendar is visible to every view.
        """

        if self._meetings is None:
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
        self.as_of = _utc(as_of)

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
        # Indexing is fail-closed: a future timeframe must declare its duration
        # before any bar from it can enter an analysis.
        span = TIMEFRAME_SPAN[timeframe]
        cutoff = pd.Timestamp(self.as_of - span)
        index = frame.index
        if index.tz is None:
            cutoff = cutoff.tz_localize(None)
        return frame[index <= cutoff]
