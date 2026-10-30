"""Licensed market and inter-market daily series from Twelve Data.

This adapter is deliberately opt-in twice: an API key is required and the
operator must explicitly confirm that the subscribed plan authorises the
application's intended display/redistribution.  A key alone is not evidence
of those rights.

Daily bars are timestamped in the exchange timezone by Twelve Data.  The
response identifies the *opening* of the bar, not an exact publication time;
we therefore expose the observation timestamp and a conservative
``available_at`` (next local midnight) separately, while leaving
``publication_time`` null.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...core.enums import DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation, Provenance
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult, ProviderStatus
from ..http import get_http


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    metric: str
    unit: str
    label: str
    market_calendar: str


# Symbols are provider identifiers, never aliases for ETFs.  Access is still
# checked per response because the exact index universe depends on the plan.
INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("SPX", "macro.sp500", "index", "S&P 500", "US_EQUITIES"),
    Instrument("IXIC", "macro.nasdaq", "index", "Nasdaq Composite", "US_EQUITIES"),
    Instrument("NDX", "macro.nasdaq100", "index", "Nasdaq-100", "US_EQUITIES"),
    Instrument("DJI", "macro.dow", "index", "Dow Jones Industrial Average", "US_EQUITIES"),
    Instrument("RUT", "macro.russell2000", "index", "Russell 2000", "US_EQUITIES"),
    Instrument("N225", "macro.nikkei225", "index", "Nikkei 225", "JP_EQUITIES"),
    Instrument(
        "STOXX50E", "macro.eurostoxx50", "index", "Euro Stoxx 50", "EU_EQUITIES"
    ),
    Instrument("VIX", "macro.vix", "index", "CBOE Volatility Index", "US_EQUITIES"),
    Instrument("EUR/USD", "macro.eurusd", "ratio", "EUR/USD", "FX_24H"),
    Instrument("USD/JPY", "macro.usdjpy", "ratio", "USD/JPY", "FX_24H"),
)

BY_SYMBOL = {item.symbol: item for item in INSTRUMENTS}


def _timezone(name: object) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "UTC"))
    except (ValueError, ZoneInfoNotFoundError):
        return ZoneInfo("UTC")


def _parse_local_datetime(raw: object, zone: ZoneInfo) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(UTC)


def _conservative_daily_availability(raw: str, zone: ZoneInfo) -> datetime | None:
    """First instant after the represented local day, never a fake close time."""

    try:
        local_day = date.fromisoformat(raw.strip().split(" ", maxsplit=1)[0])
    except (AttributeError, ValueError):
        return None
    return datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)


def parse_time_series(
    payload: Any,
    instrument: Instrument,
    *,
    fetched_at: datetime | None = None,
) -> list[Observation]:
    """Validate and normalize one ``/time_series`` response.

    Null, non-numeric and non-finite closes are holes.  They are skipped and
    never carried forward or converted to zero.
    """

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return []
    meta = payload.get("meta")
    rows = payload.get("values")
    if not isinstance(meta, dict) or not isinstance(rows, list):
        return []

    returned_symbol = str(meta.get("symbol") or "").upper()
    if returned_symbol != instrument.symbol.upper():
        return []

    zone_name = str(meta.get("exchange_timezone") or "UTC")
    zone = _timezone(zone_name)
    retrieved_at = fetched_at or datetime.now(UTC)
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    else:
        retrieved_at = retrieved_at.astimezone(UTC)

    provenance = Provenance(
        source="Twelve Data",
        provider="twelve_data",
        source_url=f"https://twelvedata.com/markets/{instrument.symbol}",
        fetched_at=retrieved_at,
        license_note=(
            "Use enabled only after operator confirmation that the subscribed Twelve Data "
            "plan permits this application's intended display and redistribution."
        ),
    )
    observations: list[Observation] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_close = row.get("close")
        if raw_close in (None, "", "null"):
            continue
        try:
            close = float(raw_close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(close):
            continue

        raw_datetime = row.get("datetime")
        observed_at = _parse_local_datetime(raw_datetime, zone)
        available_at = _conservative_daily_availability(str(raw_datetime or ""), zone)
        if observed_at is None or available_at is None:
            continue
        # `/time_series` may expose the row for the local trading day before
        # that daily bar is complete.  Metadata alone is not a guard if a
        # caller analyses the provider result directly, so unfinished rows are
        # not returned at all.
        if available_at > retrieved_at:
            continue

        observations.append(
            Observation(
                metric=instrument.metric,
                value=close,
                unit=str(meta.get("currency") or instrument.unit),
                timestamp=observed_at,
                provenance=provenance,
                freshness=compute_freshness(available_at, "macro"),
                confidence=90.0,
                quality=DataQuality.MEASURED,
                meta={
                    "indicator_id": instrument.metric,
                    "source_id": "twelve_data",
                    "canonical_source_url": "https://api.twelvedata.com/time_series",
                    "source_document_id": instrument.symbol,
                    "symbol": instrument.symbol,
                    "label": instrument.label,
                    "original_value": str(raw_close),
                    "normalized_value": close,
                    "currency": meta.get("currency"),
                    "frequency": "1day",
                    "observation_time": observed_at.isoformat(),
                    # Twelve Data documents the bar timestamp but does not
                    # return a distinct publication timestamp for daily bars.
                    "publication_time": None,
                    "available_at": available_at.isoformat(),
                    "retrieved_at": retrieved_at.isoformat(),
                    "validated_at": retrieved_at.isoformat(),
                    "revision_number": 0,
                    "vintage_time": None,
                    "market_calendar": instrument.market_calendar,
                    "timezone": zone_name,
                    "exchange": meta.get("exchange"),
                    "mic_code": meta.get("mic_code"),
                    "instrument_type": meta.get("type"),
                    "data_status": "VALID",
                    "license_status": "OPERATOR_CONFIRMED",
                    "validation_status": "VALID",
                    "quality_flags": ["DAILY_AVAILABILITY_CONSERVATIVE"],
                },
            )
        )
    return observations


class TwelveDataProvider(BaseProvider):
    name = "twelve_data"
    source = "Twelve Data"
    category = ProviderCategory.MACRO
    capabilities = ("macro.indices",)
    requires_key = "TWELVE_DATA_API_KEY"
    source_url = "https://twelvedata.com/docs"
    base_confidence = 90.0

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url = str(self.config.get("base_url", "https://api.twelvedata.com"))
        self.ttl = int((self.config.get("cache_ttl") or {}).get("default", 3600))
        self.rate_limit = int(self.config.get("rate_limit_per_min", 8))

    async def available(self) -> ProviderStatus:
        status = await super().available()
        if not status.available:
            return status
        if not get_settings().twelve_data_redistribution_authorized:
            return ProviderStatus(
                name=self.name,
                available=False,
                reason=(
                    "UNAVAILABLE - Twelve Data licence not confirmed; set "
                    "TWELVE_DATA_REDISTRIBUTION_AUTHORIZED=true only after checking the plan"
                ),
                requires_key=self.requires_key,
                configured=False,
            )
        return status

    async def fetch(self, request: FetchRequest) -> FetchResult:
        settings = get_settings()
        status = await self.available()
        if not status.available:
            return FetchResult.failure(FetchStatus.NOT_CONFIGURED, self.name, status.reason)

        requested = request.params.get("symbols")
        symbols = [str(item).upper() for item in requested] if requested else list(BY_SYMBOL)
        instruments = [BY_SYMBOL[symbol] for symbol in symbols if symbol in BY_SYMBOL]
        if not instruments:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name, "No configured Twelve Data symbol requested"
            )

        out: list[Observation] = []
        failures: list[dict[str, Any]] = []
        http = get_http()
        fetched_at = datetime.now(UTC)
        outputsize = max(2, min(int(request.limit), 5000))
        for instrument in instruments:
            response = await http.get_json(
                f"{self.base_url}/time_series",
                provider=self.name,
                params={
                    "symbol": instrument.symbol,
                    "interval": "1day",
                    "outputsize": outputsize,
                    "format": "JSON",
                },
                headers={"Authorization": f"apikey {settings.twelve_data_api_key}"},
                cache_ttl=self.ttl,
                rate_limit_per_min=self.rate_limit,
                retries=2,
            )
            if not response.ok:
                failures.append(
                    {
                        "symbol": instrument.symbol,
                        "status": response.status.value,
                        "message": response.message,
                    }
                )
                continue
            parsed = parse_time_series(response.data, instrument, fetched_at=fetched_at)
            if not parsed:
                body = response.data if isinstance(response.data, dict) else {}
                failures.append(
                    {
                        "symbol": instrument.symbol,
                        "status": str(body.get("status") or "NO_DATA"),
                        "code": body.get("code"),
                        "message": str(body.get("message") or "No valid daily close"),
                    }
                )
                continue
            out.extend(parsed)

        if out:
            return FetchResult.success(
                out,
                self.name,
                raw={"requested_symbols": symbols, "failures": failures},
            )
        if any(item.get("status") == FetchStatus.RATE_LIMITED.value for item in failures):
            return FetchResult.failure(
                FetchStatus.RATE_LIMITED, self.name, "Twelve Data rate limit reached"
            )
        return FetchResult.failure(
            FetchStatus.NO_DATA,
            self.name,
            "No authorised configured symbol returned valid data",
        )
