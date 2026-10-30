"""Bridge stored point-in-time market data into claim verification.

The verifier itself never performs I/O.  This module is the explicit adapter:
it reads only observations/bars already stored by authorised providers and
converts them into the common point-in-time contract.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from ..core.enums import Asset, Timeframe
from ..core.pointintime import Availability, PointInTimeValue
from .claim_verification import DEFAULT_ENTITY_CATALOG, Claim, ClaimVerificationEngine
from .pit_view import DataCache, PointInTimeView


def _utc(value: object) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime().astimezone(UTC)


def stored_claim_evidence(
    as_of: datetime,
    *,
    database: Path | str | None = None,
) -> list[PointInTimeValue]:
    """Return only values that the existing point-in-time view exposes at ``as_of``."""

    cutoff = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
    view = PointInTimeView(DataCache(database), cutoff)
    out: list[PointInTimeValue] = []

    macro_metrics = {
        definition.metrics[0]
        for definition in DEFAULT_ENTITY_CATALOG
        if definition.metrics and definition.metrics[0].startswith("macro.")
    }
    for metric in sorted(macro_metrics):
        for point in view.points(metric):
            if not math.isfinite(point.value):
                continue
            out.append(
                PointInTimeValue(
                    metric=metric,
                    value=point.value,
                    observation_time=point.timestamp,
                    release_time=point.available_at,
                    availability=Availability.POINT_IN_TIME,
                    source=point.source,
                    meta={
                        **point.meta,
                        "unit": point.meta.get("unit") or "index",
                        "source_url": point.meta.get("source_url")
                        or point.meta.get("canonical_source_url"),
                    },
                )
            )

    for asset in Asset.tradables():
        frame = view.candles(asset.value, Timeframe.D1)
        if frame.empty or "close" not in frame.columns:
            continue
        metric = f"price.{asset.value.lower()}.close"
        for stamp, value in frame["close"].items():
            try:
                close = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(close):
                continue
            observed_at = _utc(stamp)
            out.append(
                PointInTimeValue(
                    metric=metric,
                    value=close,
                    observation_time=observed_at,
                    release_time=observed_at + timedelta(days=1),
                    availability=Availability.POINT_IN_TIME,
                    source="stored_ohlcv",
                    meta={"unit": "USD", "market_calendar": "CRYPTO_24_7"},
                )
            )
    return out


def verify_claim_against_store(
    text: str,
    *,
    source_timestamp: datetime,
    as_of: datetime | None = None,
    database: Path | str | None = None,
) -> Claim:
    """Verify a claim without network access and without post-claim leakage."""

    source_time = source_timestamp if source_timestamp.tzinfo else source_timestamp.replace(tzinfo=UTC)
    # With no explicit replay date the endpoint answers whether the dated
    # claim is reusable *now*.  Evidence is still cut at source_time below, so
    # this cannot leak later observations into the historical recalculation.
    replay_time = as_of if as_of is not None else datetime.now(UTC)
    replay_time = replay_time if replay_time.tzinfo else replay_time.replace(tzinfo=UTC)
    cutoff = min(source_time.astimezone(UTC), replay_time.astimezone(UTC))
    observations = stored_claim_evidence(cutoff, database=database)
    return ClaimVerificationEngine().verify(
        text,
        observations=observations,
        source_timestamp=source_time,
        as_of=replay_time,
    )
