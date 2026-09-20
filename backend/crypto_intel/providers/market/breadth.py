"""Who is actually participating in the move, beyond the three assets we trade.

A rise in Bitcoin says nothing about the rest of the market. This collector
measures participation across the top of the market with CoinGecko's public
API: how many coins beat Bitcoin over 90, 30, 7 days and 24 hours, how many
are simply positive, how the performances are spread, and the capitalisation
of the market with and without BTC and ETH (TOTAL, TOTAL2, TOTAL3).

The share of the top 100 beating Bitcoin over 90 days is the published
definition behind the "altcoin season" reading. It is recomputed here from
raw prices rather than read from an index: CoinMarketCap's own index needs a
licensed API key, and an index nobody can audit is a poor foundation for a
decision. The value is therefore labelled as our own computation.

Stablecoins, wrapped tokens and liquid-staking derivatives are excluded: they
track something else by construction and would flatter or depress the count.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

CG = "https://api.coingecko.com/api/v3"
#: Excluded from every count: they do not express a market opinion.
EXCLUDED_CATEGORIES = ("stablecoins", "wrapped-tokens", "liquid-staked-sol")
#: The published "altcoin season" method looks at the top 100 over 90 days.
UNIVERSE_SIZE = 100
WINDOWS = {
    "24h": "price_change_percentage_24h_in_currency",
    "7d": "price_change_percentage_7d_in_currency",
    "30d": "price_change_percentage_30d_in_currency",
    "90d": "price_change_percentage_90d_in_currency",
}


def _pct(values: list[float], predicate) -> float | None:
    if not values:
        return None
    return round(100 * sum(1 for v in values if predicate(v)) / len(values), 1)


def compute_breadth(rows: list[dict[str, Any]], excluded: set[str]) -> dict[str, Any]:
    """Participation of the universe, window by window, Bitcoin as the yardstick."""

    btc = next((r for r in rows if r.get("id") == "bitcoin"), None)
    universe = [
        r for r in rows
        if r.get("id") not in excluded and r.get("id") != "bitcoin"
    ][: UNIVERSE_SIZE - 1]
    out: dict[str, Any] = {"sample_size": len(universe)}
    if btc is None or not universe:
        return out
    for label, key in WINDOWS.items():
        reference = btc.get(key)
        moves = [float(r[key]) for r in universe if isinstance(r.get(key), int | float)]
        out[f"positive_{label}_pct"] = _pct(moves, lambda v: v > 0)
        if isinstance(reference, int | float):
            out[f"outperform_btc_{label}_pct"] = _pct(moves, lambda v, b=float(reference): v > b)
            out[f"btc_change_{label}_pct"] = round(float(reference), 2)
        if label == "30d" and len(moves) > 5:
            mean = sum(moves) / len(moves)
            variance = sum((m - mean) ** 2 for m in moves) / (len(moves) - 1)
            out["dispersion_30d"] = round(variance ** 0.5, 1)
    alt_volume = sum(float(r.get("total_volume") or 0) for r in universe)
    btc_volume = float(btc.get("total_volume") or 0)
    if alt_volume + btc_volume > 0:
        out["alt_volume_share_pct"] = round(100 * alt_volume / (alt_volume + btc_volume), 1)
    return out


class MarketBreadthProvider(BaseProvider):
    name = "coingecko_breadth"
    source = "CoinGecko"
    category = ProviderCategory.MARKET
    capabilities = ("market.breadth",)
    source_url = "https://www.coingecko.com"
    base_confidence = 85.0

    def _observation(self, metric: str, value: float, unit: str, label: str,
                     now: datetime, extra: dict[str, Any] | None = None) -> Observation:
        return Observation(
            asset=Asset.GLOBAL,
            metric=metric,
            value=value,
            unit=unit,
            timestamp=now,
            provenance=self.provenance(f"{CG}/coins/markets"),
            freshness=compute_freshness(now, "market"),
            confidence=self.base_confidence,
            quality=DataQuality.MEASURED,
            meta={
                "label": label,
                "source_tier": "AGGREGATOR",
                "endpoint": f"{CG}/coins/markets",
                "computed_by": "crypto_intel.providers.market.breadth",
                **(extra or {}),
            },
        )

    async def _excluded_ids(self) -> set[str]:
        http = get_http()
        excluded: set[str] = set()
        for category in EXCLUDED_CATEGORIES:
            res = await http.get_json(
                f"{CG}/coins/markets", provider=self.name,
                params={"vs_currency": "usd", "category": category, "per_page": 100, "page": 1},
                cache_ttl=86_400, rate_limit_per_min=8, retries=1,
            )
            if res.ok and isinstance(res.data, list):
                excluded.update(str(row.get("id")) for row in res.data if row.get("id"))
        return excluded

    async def fetch(self, request: FetchRequest) -> FetchResult:
        http = get_http()
        res = await http.get_json(
            f"{CG}/coins/markets", provider=self.name,
            params={
                "vs_currency": "usd", "order": "market_cap_desc",
                "per_page": 150, "page": 1,
                "price_change_percentage": "24h,7d,30d,90d",
            },
            cache_ttl=1800, rate_limit_per_min=8, retries=2,
        )
        if not res.ok or not isinstance(res.data, list):
            return FetchResult.failure(res.status, self.name, res.message)
        rows = res.data
        excluded = await self._excluded_ids()
        breadth = compute_breadth(rows, excluded)
        if breadth.get("sample_size", 0) < 20:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "univers trop petit")

        now = datetime.now(UTC)
        labels = {
            "outperform_btc_90d_pct": "Part du top 100 qui surperforme BTC sur 90 jours",
            "outperform_btc_30d_pct": "Part du top 100 qui surperforme BTC sur 30 jours",
            "outperform_btc_7d_pct": "Part du top 100 qui surperforme BTC sur 7 jours",
            "outperform_btc_24h_pct": "Part du top 100 qui surperforme BTC sur 24 h",
            "positive_24h_pct": "Part du top 100 en hausse sur 24 h",
            "positive_7d_pct": "Part du top 100 en hausse sur 7 jours",
            "positive_30d_pct": "Part du top 100 en hausse sur 30 jours",
            "dispersion_30d": "Dispersion des performances sur 30 jours",
            "alt_volume_share_pct": "Part des volumes hors BTC",
        }
        out: list[Observation] = [
            self._observation(
                f"breadth.{key}", float(value), "pct" if key.endswith("pct") else "",
                labels[key], now,
                {"sample_size": breadth["sample_size"],
                 "method": "calcul interne sur les prix du top 100 (hors stablecoins, "
                           "jetons enveloppés et dérivés de staking)"},
            )
            for key, value in breadth.items()
            if key in labels and value is not None
        ]

        # TOTAL, TOTAL2, TOTAL3 - the market with, without BTC, without BTC and ETH.
        total = sum(float(r.get("market_cap") or 0) for r in rows)
        btc_cap = float(next((r for r in rows if r.get("id") == "bitcoin"), {}).get("market_cap") or 0)
        eth_cap = float(next((r for r in rows if r.get("id") == "ethereum"), {}).get("market_cap") or 0)
        if total > 0:
            out.append(self._observation("market.total_top150", total, "USD",
                                         "Capitalisation du top 150", now))
            out.append(self._observation("market.total2", total - btc_cap, "USD",
                                         "Capitalisation hors Bitcoin (TOTAL2)", now))
            out.append(self._observation("market.total3", total - btc_cap - eth_cap, "USD",
                                         "Capitalisation hors Bitcoin et Ethereum (TOTAL3)", now))
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success(out, self.name)
