"""NewsEngine: aggregation, deduplication and clustering by event.

The requirement that shapes this module: a story republished by 30 outlets is
ONE signal, not 30. So items are clustered by title similarity, and each
cluster is weighted by its most credible member - an official statement and an
anonymous blog do not carry the same weight, structurally.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from ..config_loader import providers_config, threshold
from ..core.enums import Asset, Direction, Freshness
from ..core.freshness import compute_freshness
from ..core.models import NewsCluster, NewsItem
from .regulation import detect_assets

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "as",
    "at", "by", "with", "from", "its", "it", "that", "this", "be", "will", "has",
    "have", "after", "over", "into", "amid", "says", "said", "new", "up", "down",
}

_OPINION = re.compile(
    r"\b(opinion|analysis|why |how |what |should |could |might |may |here'?s|"
    r"explained|guide|prediction|forecast|outlook|column|editorial|op-ed|"
    r"we think|i think)\b", re.I)

_OFFICIAL_SOURCES = {"SEC", "FED", "CFTC", "TREASURY", "WHITE_HOUSE"}

# Headline noise that carries no topical meaning.
_NOISE_TOKENS = {"breaking", "exclusive", "update", "just", "report", "watch", "live"}


def _stem(word: str) -> str:
    """Very light suffix stripping.

    Outlets rewrite the same event as approves/approved/approval; without this
    those become different tokens and the same story splits into two clusters.
    Deliberately crude - a real stemmer is a dependency we do not need here.
    """
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > 5 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def normalize_title(title: str) -> set[str]:
    """Token set used for similarity: lower-cased, punctuation stripped,
    stopwords and headline noise removed, lightly stemmed."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {
        _stem(w) for w in words
        if w not in _STOPWORDS and w not in _NOISE_TOKENS and len(w) > 2
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class NewsAnalysis(BaseModel):
    available: bool = True
    unavailable_reason: str | None = None
    clusters: list[NewsCluster] = Field(default_factory=list)
    total_items: int = 0
    unique_events: int = 0
    duplicates_removed: int = 0
    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    findings: list[str] = Field(default_factory=list)


class NewsEngine:
    name = "news_engine"

    def __init__(self) -> None:
        self.t = threshold("news", default={}) or {}
        tiers = providers_config().get("source_tiers", {}) or {}
        self.tier_weights = {
            int(k): float(v.get("weight", 0.25)) for k, v in tiers.items()
        } or {1: 1.0, 2: 0.8, 3: 0.55, 4: 0.25}

    def build_items(self, raw_items: list[dict], now: datetime | None = None) -> list[NewsItem]:
        now = now or datetime.now(UTC)
        max_age = timedelta(hours=float(self.t.get("max_cluster_age_hours", 48)))
        items: list[NewsItem] = []

        for raw in raw_items:
            published = raw.get("published_at")
            if not isinstance(published, datetime):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            if now - published > max_age:
                continue
            title = str(raw.get("title", "")).strip()
            if not title:
                continue
            summary = str(raw.get("summary", ""))[:500]
            institution = str(raw.get("institution") or "")
            items.append(NewsItem(
                title=title,
                url=str(raw.get("url", "")),
                source=str(raw.get("source", "unknown")),
                tier=int(raw.get("tier", 4)),
                published_at=published,
                summary=summary,
                assets=detect_assets(f"{title}. {summary}"),
                is_opinion=bool(_OPINION.search(title)),
                is_official=institution.upper() in _OFFICIAL_SOURCES or int(raw.get("tier", 4)) == 1,
            ))
        return items

    def cluster(self, items: list[NewsItem]) -> list[NewsCluster]:
        """Greedy clustering on title similarity.

        Greedy is the right trade-off here: the input is tens of items, not
        thousands, and the behaviour is easy to reason about and to test.
        """
        threshold_sim = float(self.t.get("cluster_similarity", 0.62))
        buckets: list[list[NewsItem]] = []
        bucket_tokens: list[list[set[str]]] = []

        for item in sorted(items, key=lambda i: (i.tier, -i.published_at.timestamp())):
            tokens = normalize_title(item.title)
            placed = False
            for idx, members in enumerate(bucket_tokens):
                # Single linkage: match against the closest MEMBER, not against
                # the union of the cluster. Unioning inflates the denominator,
                # so a growing cluster would progressively reject new members
                # reporting the very same story.
                if max((jaccard(tokens, m) for m in members), default=0.0) >= threshold_sim:
                    buckets[idx].append(item)
                    members.append(tokens)
                    placed = True
                    break
            if not placed:
                buckets.append([item])
                bucket_tokens.append([tokens])

        clusters: list[NewsCluster] = []
        for bucket in buckets:
            # Best tier wins; ties broken by earliest publication (the original source).
            best = min(bucket, key=lambda i: (i.tier, i.published_at))
            assets = sorted({a for i in bucket for a in i.assets}, key=lambda a: a.value)
            clusters.append(NewsCluster(
                event_title=best.title,
                items=bucket,
                primary_source=best.source,
                best_tier=best.tier,
                published_at=min(i.published_at for i in bucket),
                assets=assets,
                importance=self._importance(best, len(bucket)),
                duplicate_count=len(bucket) - 1,
            ))
        clusters.sort(key=lambda c: c.importance, reverse=True)
        return clusters

    def _importance(self, best: NewsItem, cluster_size: int) -> float:
        base = self.tier_weights.get(best.tier, 0.25) * 70.0
        if best.is_official:
            base += 20.0
        if best.is_opinion:
            # Opinion is not information; it should not drive a score.
            base *= 0.4
        # Broad pickup is weak evidence of importance, capped so it cannot
        # let a heavily-syndicated trivial story outrank an official release.
        base += min(cluster_size - 1, 8) * 1.6
        age_hours = (datetime.now(UTC) - best.published_at).total_seconds() / 3600.0
        decay = float(self.t.get("importance_decay_hours", 24))
        base *= max(0.3, 1.0 - age_hours / (decay * 3))
        return min(100.0, base)

    def analyze(
        self,
        raw_items: list[dict],
        asset: Asset | None = None,
        unavailable_reason: str | None = None,
    ) -> NewsAnalysis:
        if unavailable_reason or not raw_items:
            return NewsAnalysis(
                available=False,
                unavailable_reason=unavailable_reason or "UNAVAILABLE - no news feed data",
            )

        items = self.build_items(raw_items)
        if not items:
            return NewsAnalysis(
                available=False, total_items=len(raw_items),
                unavailable_reason="No news items within the freshness window",
            )

        clusters = self.cluster(items)
        if asset:
            clusters = [c for c in clusters if not c.assets or asset in c.assets]

        duplicates = sum(c.duplicate_count for c in clusters)
        findings: list[str] = []
        for c in clusters[:6]:
            dup = f" (+{c.duplicate_count} republications)" if c.duplicate_count else ""
            findings.append(f"[T{c.best_tier} {c.primary_source}] {c.event_title[:110]}{dup}")
        if duplicates:
            findings.append(
                f"{duplicates} duplicate republications collapsed into "
                f"{len(clusters)} distinct events"
            )

        newest = max((c.published_at for c in clusters), default=None)
        return NewsAnalysis(
            available=True, clusters=clusters[:20], total_items=len(items),
            unique_events=len(clusters), duplicates_removed=duplicates,
            # News direction is intentionally left to the LLM/news analyst:
            # keyword sentiment on headlines is unreliable enough that a
            # numeric score here would be false precision.
            direction=Direction.NEUTRAL if clusters else Direction.INCONCLUSIVE,
            strength=0.0,
            freshness=compute_freshness(newest, "news"),
            findings=findings,
        )
