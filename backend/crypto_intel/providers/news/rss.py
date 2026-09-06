"""RSS aggregation for news and regulatory feeds.

Public RSS only. No article scraping, no paywall circumvention: we read the
feed's own title/summary/link, which is exactly what a feed is published for.

The SEC requires a descriptive User-Agent for its feeds - that is the source's
own documented policy, so honouring it is compliance, not evasion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...config_loader import providers_config
from ...core.enums import FetchStatus, ProviderCategory
from ...logging_setup import get_logger
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

log = get_logger("providers.rss")


def _parse_entry_time(entry: Any) -> datetime | None:
    import time as _time

    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None) or (entry.get(field) if hasattr(entry, "get") else None)
        if parsed:
            try:
                return datetime.fromtimestamp(_time.mktime(parsed), tz=UTC)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


class _RSSBase(BaseProvider):
    feed_key = "news"
    category = ProviderCategory.NEWS

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._feeds: list[dict[str, Any]] = (
            providers_config().get("feeds", {}).get(self.feed_key, []) or []
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        import feedparser

        settings = get_settings()
        http = get_http()
        items: list[dict[str, Any]] = []
        failures: list[str] = []

        for feed in self._feeds:
            url = feed.get("url")
            if not url:
                continue
            headers = {}
            # SEC's published policy: identify yourself on their feeds.
            if "sec.gov" in url:
                headers["User-Agent"] = settings.sec_user_agent

            res = await http.get_text(
                url, provider=self.name, headers=headers or None,
                cache_ttl=900, rate_limit_per_min=30, retries=1,
            )
            if not res.ok:
                failures.append(f"{feed.get('name', url)}: {res.status.value}")
                continue

            try:
                parsed = feedparser.parse(res.data)
            except Exception as exc:
                failures.append(f"{feed.get('name', url)}: parse error {exc}")
                continue

            for entry in parsed.entries[:40]:
                published = _parse_entry_time(entry)
                if published is None:
                    continue
                items.append({
                    "title": (entry.get("title") or "").strip(),
                    "url": entry.get("link") or "",
                    "summary": (entry.get("summary") or entry.get("description") or "").strip(),
                    "published_at": published,
                    "source": feed.get("name", "unknown"),
                    "tier": int(feed.get("tier", 4)),
                    "institution": feed.get("institution"),
                })

        if not items:
            return FetchResult.failure(
                FetchStatus.NO_DATA, self.name,
                "; ".join(failures) if failures else "No feed entries retrieved",
            )
        items.sort(key=lambda i: i["published_at"], reverse=True)
        return FetchResult(
            status=FetchStatus.OK, observations=[], raw={"items": items, "failures": failures},
            provider=self.name,
        )


class RSSNewsProvider(_RSSBase):
    name = "rss_news"
    source = "RSS news aggregation"
    feed_key = "news"
    capabilities = ("news.feed",)
    category = ProviderCategory.NEWS
    source_url = "multiple"


class RSSRegulationProvider(_RSSBase):
    name = "rss_regulation"
    source = "Official regulator RSS feeds"
    feed_key = "regulation"
    capabilities = ("regulation.feed",)
    category = ProviderCategory.REGULATION
    source_url = "multiple"
    base_confidence = 95.0
