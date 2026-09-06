"""MOCK_MODE provider: serves every capability from fixtures/.

The point is to run the entire application - collection, analysis, scoring,
report, frontend - with no network and no API key, so the whole UI can be
verified immediately.

Fixture data is clearly synthetic and is ONLY ever used when MOCK_MODE=true.
Outside mock mode this provider is never registered, so no fabricated number
can leak into a real report.
"""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..core.enums import (
    Asset,
    DataQuality,
    FetchStatus,
    ProviderCategory,
    Timeframe,
)
from ..core.freshness import compute_freshness
from ..core.models import Candle, Observation, OHLCVSeries
from ..settings import get_settings
from .base import BaseProvider, FetchRequest, FetchResult

# Rough anchors so mock charts look plausible rather than random noise.
_ANCHOR_PRICE = {Asset.BTC: 64000.0, Asset.ETH: 3100.0, Asset.SOL: 145.0}
_ANCHOR_MCAP = {Asset.BTC: 1_260_000_000_000.0, Asset.ETH: 373_000_000_000.0, Asset.SOL: 68_000_000_000.0}


class FixtureProvider(BaseProvider):
    """Single provider standing in for every real one, in mock mode."""

    name = "fixtures"
    source = "MOCK FIXTURES (synthetic data - MOCK_MODE only)"
    category = ProviderCategory.MARKET
    capabilities = (
        "market.ohlcv", "market.ticker", "market.marketcap", "market.global",
        "derivatives.funding", "derivatives.oi", "derivatives.ratio",
        "etf.flows", "onchain.btc", "onchain.eth", "onchain.sol",
        "defi.tvl", "defi.dex", "defi.fees", "defi.rwa", "stablecoins.supply",
        "macro.series", "macro.indices", "news.feed", "regulation.feed",
    )
    source_url = "local://fixtures"
    base_confidence = 60.0   # deliberately lower: this is not real data

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.dir: Path = get_settings().fixtures_dir

    def _load(self, relative: str) -> Any | None:
        p = self.dir / relative
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    async def fetch(self, request: FetchRequest) -> FetchResult:
        cap = request.capability
        if cap == "market.ohlcv":
            return self._ohlcv(request)
        if cap == "market.ticker":
            return self._ticker(request)
        if cap == "market.marketcap":
            return self._marketcap(request)
        if cap == "market.global":
            return self._from_file("market/global.json", None)
        if cap.startswith("derivatives."):
            # No capability filter here: the metrics are named funding.* / oi.* /
            # long_short.*, not derivatives.*, so filtering by prefix would
            # silently drop all of them.
            asset = request.asset or Asset.BTC
            return self._from_file(f"derivatives/{asset.value.lower()}.json", asset)
        if cap == "etf.flows":
            return self._etf(request)
        if cap.startswith("onchain."):
            return self._from_file(f"onchain/{cap.split('.')[1]}.json", request.asset)

        if cap.startswith("defi.") or cap.startswith("stablecoins."):
            fname = {"defi.tvl": "tvl.json", "defi.dex": "dex.json", "defi.fees": "fees.json",
                     "defi.rwa": "rwa.json", "stablecoins.supply": "stablecoins.json"}.get(cap)
            sub = "stablecoins" if cap.startswith("stablecoins") else "defi"
            return self._from_file(f"{sub}/{fname}", request.asset)
        if cap.startswith("macro."):
            return self._from_file(f"macro/{cap.split('.')[1]}.json", None)
        if cap == "news.feed":
            return self._raw_file("news/news.json")
        if cap == "regulation.feed":
            return self._raw_file("regulation/regulation.json")
        return FetchResult.failure(FetchStatus.NO_DATA, self.name, f"no fixture for {cap}")

    # --- synthesized series ----------------------------------------------

    def _ohlcv(self, request: FetchRequest) -> FetchResult:
        """Deterministic pseudo-random walk. Seeded per asset+timeframe so the
        same fixture chart appears on every run - tests need stability."""
        asset = request.asset or Asset.BTC
        tf = request.timeframe or Timeframe.H1
        n = min(request.limit, 400)

        rng = random.Random(f"{asset.value}{tf.value}")
        anchor = _ANCHOR_PRICE.get(asset, 100.0)
        vol = {Timeframe.M15: 0.0035, Timeframe.H1: 0.007, Timeframe.H4: 0.014,
               Timeframe.D1: 0.028, Timeframe.W1: 0.06}[tf]

        now = datetime.now(UTC).replace(second=0, microsecond=0)
        step = timedelta(minutes=tf.minutes)
        start_time = now - step * n

        price = anchor * 0.88
        candles: list[Candle] = []
        for i in range(n):
            # gentle uptrend + cycle, so indicators produce meaningful values
            drift = 0.0006 + 0.0015 * math.sin(i / 22.0)
            price *= 1.0 + drift + rng.gauss(0, vol)
            price = max(price, anchor * 0.35)
            o = price * (1 + rng.gauss(0, vol * 0.25))
            c = price
            h = max(o, c) * (1 + abs(rng.gauss(0, vol * 0.5)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, vol * 0.5)))
            v = abs(rng.gauss(1.0, 0.35)) * (1_000 if asset == Asset.BTC else 25_000)
            candles.append(
                Candle(timestamp=start_time + step * i, open=round(o, 2), high=round(h, 2),
                       low=round(lo, 2), close=round(c, 2), volume=round(v, 2))
            )

        series = OHLCVSeries(
            asset=asset, timeframe=tf, candles=candles,
            provenance=self.provenance(), freshness=compute_freshness(candles[-1].timestamp, "price", interval_minutes=tf.minutes),
        )
        obs = Observation(
            asset=asset, metric="price.close", value=candles[-1].close, unit="USD", timeframe=tf,
            timestamp=candles[-1].timestamp, provenance=self.provenance(),
            freshness=series.freshness, confidence=self.base_confidence,
            quality=DataQuality.ESTIMATED, meta={"mock": True, "bars": len(candles)},
        )
        return FetchResult.success([obs], self.name, raw=series)

    def _ticker(self, request: FetchRequest) -> FetchResult:
        asset = request.asset or Asset.BTC
        r = self._ohlcv(FetchRequest(capability="market.ohlcv", asset=asset,
                                     timeframe=Timeframe.H1, limit=30))
        if not r.ok:
            return r
        series: OHLCVSeries = r.raw
        last = series.candles[-1]
        prev24 = series.candles[-25] if len(series.candles) > 25 else series.candles[0]
        change = (last.close - prev24.close) / prev24.close * 100.0
        now = datetime.now(UTC)
        prov = self.provenance()
        f = compute_freshness(now, "price")

        def o(metric: str, value: float, unit: str) -> Observation:
            return Observation(asset=asset, metric=metric, value=value, unit=unit, timestamp=now,
                               provenance=prov, freshness=f, confidence=self.base_confidence,
                               quality=DataQuality.ESTIMATED, meta={"mock": True})

        highs = [c.high for c in series.candles[-24:]]
        lows = [c.low for c in series.candles[-24:]]
        return FetchResult.success(
            [
                o("price.last", last.close, "USD"),
                o("price.change_24h_pct", round(change, 2), "pct"),
                o("price.high_24h", max(highs), "USD"),
                o("price.low_24h", min(lows), "USD"),
                o("price.volume_24h_quote", sum(c.volume * c.close for c in series.candles[-24:]), "USD"),
            ],
            self.name,
        )

    def _marketcap(self, request: FetchRequest) -> FetchResult:
        asset = request.asset or Asset.BTC
        now = datetime.now(UTC)
        prov = self.provenance()
        f = compute_freshness(now, "market")
        mcap = _ANCHOR_MCAP.get(asset, 1e9)
        rng = random.Random(asset.value + "mcap")
        out = [
            Observation(asset=asset, metric="market.cap", value=mcap, unit="USD", timestamp=now,
                        provenance=prov, freshness=f, confidence=self.base_confidence,
                        quality=DataQuality.ESTIMATED, meta={"mock": True}),
            Observation(asset=asset, metric="market.change_7d_pct", value=round(rng.uniform(-8, 12), 2),
                        unit="pct", timestamp=now, provenance=prov, freshness=f,
                        confidence=self.base_confidence, quality=DataQuality.ESTIMATED, meta={"mock": True}),
            Observation(asset=asset, metric="market.change_1h_pct", value=round(rng.uniform(-1.2, 1.2), 2),
                        unit="pct", timestamp=now, provenance=prov, freshness=f,
                        confidence=self.base_confidence, quality=DataQuality.ESTIMATED, meta={"mock": True}),
        ]
        return FetchResult.success(out, self.name)

    def _etf(self, request: FetchRequest) -> FetchResult:
        data = self._load("etf/flows.json")
        if not data:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "no etf fixture")
        asset = request.asset or Asset.BTC
        rows = [r for r in data.get("rows", []) if r["asset"] == asset.value]
        if not rows:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, f"no mock ETF rows for {asset.value}")
        out = []
        prov = self.provenance()
        for r in rows:
            ts = datetime.fromisoformat(r["date"]).replace(tzinfo=UTC)
            out.append(
                Observation(
                    asset=asset, metric="etf.flow", value=float(r["flow_musd"]), unit="USD_M",
                    timestamp=ts, provenance=prov, freshness=compute_freshness(ts, "etf"),
                    confidence=self.base_confidence, quality=DataQuality.ESTIMATED,
                    meta={"ticker": r["ticker"], "mock": True},
                )
            )
        return FetchResult.success(out, self.name, raw=rows)

    def _from_file(self, relative: str, asset: Asset | None, capability: str = "") -> FetchResult:
        data = self._load(relative)
        if not data:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, f"missing fixture {relative}")
        now = datetime.now(UTC)
        prov = self.provenance()
        out: list[Observation] = []
        for metric, value in (data.get("metrics") or {}).items():
            if capability and not metric.startswith(capability.split(".")[0]):
                continue
            unit = (data.get("units") or {}).get(metric, "")
            out.append(
                Observation(
                    asset=asset, metric=metric, value=value, unit=unit, timestamp=now,
                    provenance=prov, freshness=compute_freshness(now, metric),
                    confidence=self.base_confidence, quality=DataQuality.ESTIMATED,
                    meta={"mock": True},
                )
            )
        if not out:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, f"fixture {relative} had no metrics")
        return FetchResult.success(out, self.name, raw=data)

    def _raw_file(self, relative: str) -> FetchResult:
        """Feed-shaped fixtures (news, regulation).

        `published_at` is stored as an ISO string in JSON but every downstream
        engine expects a real datetime, so it is parsed here rather than making
        each engine defensive about types.
        """
        data = self._load(relative)
        if data is None:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, f"missing fixture {relative}")

        items = data.get("items") if isinstance(data, dict) else None
        if items:
            for item in items:
                raw_date = item.get("published_at")
                if isinstance(raw_date, str):
                    try:
                        parsed = datetime.fromisoformat(raw_date)
                        item["published_at"] = (
                            parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
                        )
                    except ValueError:
                        item["published_at"] = None
        return FetchResult(status=FetchStatus.OK, observations=[], raw=data, provider=self.name)
