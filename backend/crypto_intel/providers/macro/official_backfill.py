"""Backfill the official series' history, with their publication times.

The live providers fetch a few weeks; a backtest needs years. Every source below
publishes its archive without a key. Each point is stored exactly as the live
collection stores it - same metric, same ``available_at`` - so the
point-in-time view treats history and today identically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ...core.models import Observation
from ...db import repo
from .official_us import (
    NYFED_RRP_URL,
    TGA_URL,
    TREASURY_CURVE_URL,
    NewYorkFedProvider,
    TreasuryGeneralAccountProvider,
    TreasuryYieldsProvider,
    _observation,
    parse_effr,
    parse_rrp,
    parse_tga,
    parse_treasury_curve,
)

NYFED_EFFR_SEARCH = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
STABLECOIN_HISTORY = "https://stablecoins.llama.fi/stablecoincharts/all"
HEADERS = {"User-Agent": "crypto-intel/1.0 (research; contact via repository)"}


def _get(client: httpx.Client, url: str, **params: Any) -> httpx.Response:
    response = client.get(url, params=params or None, timeout=60)
    response.raise_for_status()
    return response


def backfill(since_year: int = 2019) -> dict[str, int]:
    """Fetch and store every series from ``since_year``; returns rows written."""

    written: dict[str, int] = {}
    now = datetime.now(UTC)
    yields = TreasuryYieldsProvider()
    tga_provider = TreasuryGeneralAccountProvider()
    nyfed = NewYorkFedProvider()

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        # Treasury nominal and real curves, one CSV per year.
        points: list[tuple[str, datetime, float]] = []
        for year in range(since_year, now.year + 1):
            for kind, columns in (
                ("daily_treasury_yield_curve", yields.NOMINAL),
                ("daily_treasury_real_yield_curve", yields.REAL),
            ):
                text = _get(client, TREASURY_CURVE_URL.format(year=year, kind=kind)).text
                points.extend(parse_treasury_curve(text, columns))
        by_day: dict[datetime, dict[str, float]] = {}
        for metric, day, value in points:
            by_day.setdefault(day, {})[metric] = value
        for day, values in by_day.items():
            if "macro.us10y" in values and "macro.us2y" in values:
                points.append(("macro.yield_curve_10y2y", day, values["macro.us10y"] - values["macro.us2y"]))
        obs = [
            _observation(
                yields, metric=metric, value=value, unit=yields.LABELS[metric][0],
                observed=day, url=yields.source_url, label=yields.LABELS[metric][1],
            )
            for metric, day, value in points
        ]
        written["treasury_curves"] = repo.save_observations(obs)

        # Treasury General Account, paginated.
        tga_rows: list[tuple[datetime, float]] = []
        page = 1
        while True:
            payload = _get(
                client, TGA_URL,
                **{
                    "filter": f"record_date:gte:{since_year}-01-01",
                    "page[size]": "5000",
                    "page[number]": str(page),
                    "sort": "record_date",
                },
            ).json()
            tga_rows.extend(parse_tga(payload))
            total_pages = int((payload.get("meta") or {}).get("total-pages") or 1)
            if page >= total_pages:
                break
            page += 1
        written["tga"] = repo.save_observations([
            _observation(
                tga_provider, metric="liquidity.tga", value=value, unit="musd", observed=day,
                url=tga_provider.source_url, label="Compte du Trésor à la Fed (TGA)",
            )
            for day, value in tga_rows
        ])

        # New York Fed: reverse repo and EFFR, by year.
        rrp: list[Observation] = []
        effr: list[Observation] = []
        for year in range(since_year, now.year + 1):
            start, end = f"{year}-01-01", f"{year}-12-31"
            for day, value in parse_rrp(_get(client, NYFED_RRP_URL, startDate=start, endDate=end).json()):
                rrp.append(_observation(
                    nyfed, metric="liquidity.rrp", value=value / 1e6, unit="musd",
                    observed=day, url=nyfed.source_url,
                    label="Prises en pension inversées de la Fed (RRP)",
                ))
            for day, value in parse_effr(_get(client, NYFED_EFFR_SEARCH, startDate=start, endDate=end).json()):
                effr.append(_observation(
                    nyfed, metric="macro.fed_funds_rate", value=value, unit="pct",
                    observed=day, url=nyfed.source_url,
                    label="Taux effectif des fonds fédéraux (EFFR)",
                ))
        written["rrp"] = repo.save_observations(rrp)
        written["effr"] = repo.save_observations(effr)

        # Stablecoin supply: every pegged currency, in dollars, per day.
        from ...core.enums import DataQuality
        from ...core.freshness import compute_freshness
        from ...core.models import Provenance

        stable: list[Observation] = []
        cutoff = datetime(since_year, 1, 1, tzinfo=UTC)
        for row in _get(client, STABLECOIN_HISTORY).json():
            day = datetime.fromtimestamp(int(row["date"]), UTC)
            if day < cutoff:
                continue
            total = sum(float(v) for v in (row.get("totalCirculatingUSD") or {}).values())
            available = day + timedelta(days=1)
            stable.append(Observation(
                metric="stablecoin.supply.total", value=total, unit="USD", timestamp=day,
                provenance=Provenance(
                    source="DeFiLlama Stablecoins (historique)",
                    provider="defillama_stables",
                    source_url="https://defillama.com/stablecoins",
                ),
                freshness=compute_freshness(available, "macro"),
                confidence=85.0, quality=DataQuality.MEASURED,
                meta={"available_at": available.isoformat(), "source_tier": "AGGREGATOR"},
            ))
        written["stablecoins"] = repo.save_observations(stable)
    return written
