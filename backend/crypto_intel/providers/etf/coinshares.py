"""CoinShares weekly fund flows: the global picture, beside the US ETF file.

Farside answers "what did each US spot ETF do yesterday". CoinShares answers
"where did money go across every listed crypto investment product last week,
in every region". They are complements, never substitutes, and the engine that
reads them keeps a disagreement visible instead of averaging it away.

The figures are read from the issuer's own research feed. Each weekly report
states the global flow, the flow per asset and assets under management; those
are extracted with their sign taken from the words "inflows" / "outflows" -
never guessed. What cannot be read is left out rather than approximated.

Freshness matters here more than anywhere: the report is weekly, so a reading
older than its cadence is stale by construction and is labelled as such.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from ...core.enums import Asset, DataQuality, FetchStatus, ProviderCategory
from ...core.freshness import compute_freshness
from ...core.models import Observation
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

FEED_URL = "https://researchblog.coinshares.com/feed"
#: A weekly publication: beyond two cadences the reading is old, not current.
MAX_AGE = timedelta(days=14)

_ASSET_WORDS = {
    Asset.BTC: ("bitcoin",),
    Asset.ETH: ("ethereum",),
    Asset.SOL: ("solana",),
}
#: "Bitcoin saw US$1,438m of outflows" / "inflows of US$28.4m into Solana"
_AMOUNT = re.compile(
    r"US\$(?P<value>[\d,.]+)\s*(?P<unit>bn|m|k)?\b",
    re.I,
)
_FLOW_WORD = re.compile(r"\b(inflow|outflow)s?\b", re.I)


def _to_usd(value: str, unit: str | None) -> float | None:
    try:
        amount = float(value.replace(",", ""))
    except ValueError:
        return None
    factor = {"bn": 1e9, "m": 1e6, "k": 1e3, None: 1.0, "": 1.0}.get((unit or "").lower(), 1.0)
    return amount * factor


def _strip(markup: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup or ""))
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def parse_weekly_report(text: str) -> dict[str, Any]:
    """Global flow, per-asset flows and AuM, each read from its own sentence.

    A sentence only produces a number when it carries both an amount and the
    word that gives its direction. Anything ambiguous is skipped.
    """

    out: dict[str, Any] = {"assets": {}}
    for sentence in _sentences(text):
        flow_word = _FLOW_WORD.search(sentence)
        amount = _AMOUNT.search(sentence)
        if not flow_word or not amount:
            continue
        value = _to_usd(amount.group("value"), amount.group("unit"))
        if value is None:
            continue
        signed = -value if flow_word.group(1).lower() == "outflow" else value
        lowered = sentence.lower()
        matched_asset = next(
            (asset for asset, words in _ASSET_WORDS.items() if any(w in lowered for w in words)),
            None,
        )
        if matched_asset is not None:
            out["assets"].setdefault(matched_asset.value, signed)
        elif "global" in lowered or "digital asset investment products" in lowered:
            out.setdefault("global", signed)
    aum = re.search(r"AuM has (?:fallen|risen) to US\$(?P<value>[\d,.]+)\s*(?P<unit>bn|m)?", text, re.I)
    if aum:
        out["aum"] = _to_usd(aum.group("value"), aum.group("unit"))
    return out


def parse_feed(xml: str) -> list[dict[str, Any]]:
    """Every weekly flows report in the feed, newest first."""

    import feedparser

    parsed = feedparser.parse(xml)
    reports: list[dict[str, Any]] = []
    for entry in parsed.entries:
        title = str(entry.get("title", ""))
        if "fund flows" not in title.lower():
            continue
        published = entry.get("published_parsed")
        when = (
            datetime(*published[:6], tzinfo=UTC) if published else None
        )
        content = ""
        if entry.get("content"):
            content = entry["content"][0].get("value", "")
        body = _strip(content or entry.get("summary", ""))
        figures = parse_weekly_report(body)
        if when is None or (not figures.get("assets") and figures.get("global") is None):
            continue
        reports.append({
            "title": title,
            "published_at": when,
            "url": str(entry.get("link", "")),
            "summary": body[:400],
            **figures,
        })
    return sorted(reports, key=lambda r: r["published_at"], reverse=True)


class CoinSharesFlowsProvider(BaseProvider):
    name = "coinshares_flows"
    source = "CoinShares"
    category = ProviderCategory.ETF
    capabilities = ("flows.institutional_weekly",)
    source_url = "https://coinshares.com/"
    base_confidence = 88.0

    def _observation(self, metric: str, value: float, when: datetime, label: str,
                     asset: Asset | None, url: str, extra: dict[str, Any]) -> Observation:
        # Published weekly on Monday for the week before: the value describes
        # that week, and it is knowable only once published.
        return Observation(
            asset=asset,
            metric=metric,
            value=value,
            unit="USD",
            timestamp=when,
            provenance=self.provenance(url or self.source_url),
            freshness=compute_freshness(when, "etf"),
            confidence=self.base_confidence,
            quality=DataQuality.MEASURED,
            meta={
                "label": label,
                "available_at": when.isoformat(),
                "source_tier": "INSTITUTIONAL_DATA",
                "endpoint": FEED_URL,
                "cadence": "weekly",
                "max_age_days": MAX_AGE.days,
                **extra,
            },
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        res = await get_http().get_text(
            FEED_URL, provider=self.name, cache_ttl=3600, rate_limit_per_min=10, retries=2,
        )
        if not res.ok:
            return FetchResult.failure(res.status, self.name, res.message)
        reports = parse_feed(str(res.data or ""))
        if not reports:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name,
                                       "aucun rapport hebdomadaire exploitable")
        out: list[Observation] = []
        for report in reports[:8]:
            when, url = report["published_at"], report["url"]
            extra = {"report": report["title"], "summary": report["summary"]}
            if report.get("global") is not None:
                out.append(self._observation(
                    "flows.coinshares.global", float(report["global"]), when,
                    "Flux hebdomadaires des produits d'investissement crypto (monde)",
                    None, url, extra,
                ))
            for symbol, value in (report.get("assets") or {}).items():
                out.append(self._observation(
                    "flows.coinshares.asset", float(value), when,
                    f"Flux hebdomadaires des produits {symbol}", Asset(symbol), url, extra,
                ))
            if report.get("aum") is not None:
                out.append(self._observation(
                    "flows.coinshares.aum", float(report["aum"]), when,
                    "Encours des produits d'investissement crypto", None, url, extra,
                ))
        return FetchResult.success(out, self.name)
