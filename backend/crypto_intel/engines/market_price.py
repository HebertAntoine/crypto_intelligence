"""Fast market-price snapshot for UI surfaces.

This is intentionally separate from the slower analytical engines. The phone
needs the latest price and 24h change frequently; it must not rerun research or
LLM analysis just to refresh a ticker.
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from ..core.enums import Asset, FetchStatus, Freshness
from ..core.models import Observation
from ..providers.base import BaseProvider, FetchRequest
from ..providers.registry import get_registry
from ..settings import get_settings


class ProviderQuote(BaseModel):
    provider: str
    source: str
    status: str
    unit: str = "USD"
    price: float | None = None
    change_24h_pct: float | None = None
    timestamp: datetime | None = None
    fetched_at: datetime | None = None
    freshness: str = Freshness.UNAVAILABLE.value
    quality: str = "UNAVAILABLE"
    message: str = ""


class MarketPriceSnapshot(BaseModel):
    asset: str
    status: str
    price_usd: float | None = None
    price_eur: float | None = None
    change_24h_pct: float | None = None
    timestamp: datetime | None = None
    as_of: datetime | None = None
    fetched_at: datetime
    age_seconds: float | None = None
    providers: list[ProviderQuote]
    provider_count: int = 0
    dispersion_pct: float | None = None
    quality: str = "UNAVAILABLE"
    freshness: str = Freshness.UNAVAILABLE.value
    fx_rate: float | None = None
    fx_timestamp: datetime | None = None
    fx_source: str | None = None
    method: str = ""


async def market_price_snapshot(asset: Asset) -> MarketPriceSnapshot:
    """Return current price consensus plus provenance.

    USD is a median across configured market ticker providers. EUR is taken
    from Coinbase's direct EUR spot pair when available, then documented as an
    implied FX conversion; if unavailable, the UI must display USD instead of
    manufacturing an EUR value.
    """

    registry = get_registry()
    providers = registry.chain("market.ticker")
    usd_quotes = await asyncio.gather(
        *(_provider_quote(provider, asset, "USD") for provider in providers)
    )

    eur_quote: ProviderQuote | None = None
    coinbase = registry.get("coinbase_spot")
    if coinbase is not None and not get_settings().mock_mode:
        eur_quote = await _provider_quote(coinbase, asset, "EUR")

    good_usd = [
        quote for quote in usd_quotes
        if quote.status == FetchStatus.OK.value
        and quote.price is not None
        and quote.price > 0
        and quote.unit in {"USD", "USDT"}
    ]
    good_changes = [
        quote.change_24h_pct
        for quote in good_usd
        if quote.change_24h_pct is not None
    ]
    now = datetime.now(UTC)
    if not good_usd:
        quotes = list(usd_quotes)
        if eur_quote is not None:
            quotes.append(eur_quote)
        return MarketPriceSnapshot(
            asset=asset.value,
            status="UNAVAILABLE",
            fetched_at=now,
            providers=quotes,
            method="No configured ticker provider returned a positive USD spot price.",
        )

    prices = [quote.price for quote in good_usd if quote.price is not None]
    price_usd = float(statistics.median(prices))
    dispersion = None
    if len(prices) >= 2 and price_usd > 0:
        dispersion = (max(prices) - min(prices)) / price_usd * 100
    timestamp = max(
        (quote.timestamp for quote in good_usd if quote.timestamp is not None),
        default=now,
    )
    freshness = _worst_freshness(quote.freshness for quote in good_usd)
    status = _status_from_freshness(freshness)
    if get_settings().mock_mode:
        status = "SNAPSHOT"

    price_eur = None
    fx_rate = None
    fx_timestamp = None
    fx_source = None
    if (
        eur_quote is not None
        and eur_quote.status == FetchStatus.OK.value
        and eur_quote.unit == "EUR"
        and eur_quote.price is not None
        and eur_quote.price > 0
    ):
        price_eur = eur_quote.price
        fx_rate = price_eur / price_usd if price_usd > 0 else None
        fx_timestamp = eur_quote.timestamp
        fx_source = f"{eur_quote.source} direct EUR spot pair"

    quotes = list(usd_quotes)
    if eur_quote is not None:
        quotes.append(eur_quote)
    return MarketPriceSnapshot(
        asset=asset.value,
        status=status,
        price_usd=round(price_usd, 8),
        price_eur=round(price_eur, 8) if price_eur is not None else None,
        change_24h_pct=(
            round(float(statistics.median(good_changes)), 4)
            if good_changes
            else None
        ),
        timestamp=timestamp,
        as_of=timestamp,
        fetched_at=now,
        age_seconds=max((now - timestamp).total_seconds(), 0),
        providers=quotes,
        provider_count=len(good_usd),
        dispersion_pct=round(dispersion, 4) if dispersion is not None else None,
        quality=_quality(len(good_usd), dispersion),
        freshness=freshness,
        fx_rate=round(fx_rate, 8) if fx_rate is not None else None,
        fx_timestamp=fx_timestamp,
        fx_source=fx_source,
        method=(
            "USD median across configured market.ticker providers; 24h change "
            "is the median of provider rolling-24h ticker changes when exposed."
        ),
    )


async def _provider_quote(
    provider: BaseProvider,
    asset: Asset,
    quote: str,
) -> ProviderQuote:
    try:
        result = await provider.fetch(
            FetchRequest(
                capability="market.ticker",
                asset=asset,
                params={"quote": quote},
            )
        )
    except Exception as exc:  # providers should not raise, but UI must know.
        return ProviderQuote(
            provider=provider.name,
            source=provider.source,
            status=FetchStatus.NETWORK_ERROR.value,
            unit=quote,
            message=str(exc),
        )

    if not result.ok:
        return ProviderQuote(
            provider=provider.name,
            source=provider.source,
            status=result.status.value,
            unit=quote,
            message=result.user_message,
        )

    price = _first_observation(result.observations, "price.last")
    change = _first_observation(result.observations, "price.change_24h_pct")
    timestamp = price.timestamp if price is not None else None
    fetched_at = price.provenance.fetched_at if price is not None else None
    freshness = price.freshness.value if price is not None else Freshness.UNAVAILABLE.value
    unit = price.unit if price is not None else quote
    quality = price.quality.value if price is not None else "UNAVAILABLE"
    return ProviderQuote(
        provider=provider.name,
        source=provider.source,
        status=result.status.value,
        unit=unit,
        price=price.numeric_value if price is not None else None,
        change_24h_pct=change.numeric_value if change is not None else None,
        timestamp=timestamp,
        fetched_at=fetched_at,
        freshness=freshness,
        quality=quality,
    )


def _first_observation(observations: list[Observation], metric: str) -> Observation | None:
    return next((obs for obs in observations if obs.metric == metric), None)


def _worst_freshness(values: Any) -> str:
    parsed = []
    for value in values:
        try:
            parsed.append(Freshness(value))
        except ValueError:
            parsed.append(Freshness.UNAVAILABLE)
    if not parsed:
        return Freshness.UNAVAILABLE.value
    return min(parsed, key=lambda item: item.rank).value


def _status_from_freshness(value: str) -> str:
    if value == Freshness.LIVE.value:
        return "LIVE"
    if value == Freshness.STALE.value:
        return "STALE"
    if value == Freshness.UNAVAILABLE.value:
        return "UNAVAILABLE"
    return "DELAYED"


def _quality(count: int, dispersion: float | None) -> str:
    if count <= 0:
        return "UNAVAILABLE"
    if count >= 2 and dispersion is not None and dispersion <= 1.0:
        return "HIGH"
    if count >= 2:
        return "MEDIUM"
    return "SINGLE_PROVIDER"
