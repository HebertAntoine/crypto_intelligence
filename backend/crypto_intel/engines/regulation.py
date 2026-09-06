"""RegulationAndPoliticsAnalyzer.

The single most important rule here: a proposal must never be presented as
enacted law. Every item is classified into an explicit legal status, and when
the wording does not clearly support a classification the answer is UNCERTAIN
rather than a guess.

Classification is lexical and conservative. It runs on the feed's own title and
summary - no article scraping, no paywall circumvention.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from ..core.enums import Asset, Direction, Freshness, LegalStatus
from ..core.models import RegulatoryEvent

# Ordered by specificity: the first pattern that matches wins, so
# "signed into law" beats the generic "bill" pattern.
_STATUS_PATTERNS: list[tuple[LegalStatus, re.Pattern[str]]] = [
    (LegalStatus.ADOPTED, re.compile(
        r"\b(sign(?:s|ed)?\b[^.]{0,40}\binto law|enacted|became law|is now law|"
        r"adopts? final rule|final rule (?:was )?adopted|passed both chambers|"
        r"signed by the president)\b", re.I)),
    (LegalStatus.REGULATORY_DECISION, re.compile(
        r"\b(approves?|approved|grants? (?:the )?application|authoriz(?:es|ed)|"
        r"denies?|denied|rejects?|rejected|order (?:granting|denying)|"
        r"declares? effective)\b", re.I)),
    (LegalStatus.ENFORCEMENT, re.compile(
        r"\b(charges?|charged|sues?|sued|enforcement action|settles?|settled|"
        r"fines?|fined|penalt(?:y|ies)|indict(?:s|ed|ment)|cease and desist)\b", re.I)),
    (LegalStatus.VOTE_HELD, re.compile(
        # Both word orders occur in headlines: "passed the Senate" and
        # "Senate passed the bill".
        r"\b(voted|vote (?:was )?held|passed the (?:house|senate|committee)|"
        r"(?:house|senate|committee)\s+(?:has\s+)?passed|committee approved|"
        r"cleared the (?:house|senate|committee))\b", re.I)),
    (LegalStatus.VOTE_SCHEDULED, re.compile(
        r"\b(vote (?:is )?scheduled|will vote|to vote on|markup scheduled|"
        r"scheduled for a vote|schedules? a vote|sets? a vote|"
        r"vote (?:expected|planned))\b", re.I)),
    (LegalStatus.CONSULTATION, re.compile(
        r"\b(requests? (?:for )?(?:public )?comment|seeks? (?:public )?comment|"
        r"consultation|proposed rulemaking|comment period|"
        r"requests? for information|invites? comment)\b", re.I)),
    (LegalStatus.PROPOSED, re.compile(
        r"\b(propos(?:es|ed|al)|introduce[sd]?|bill|draft (?:rule|legislation)|"
        r"legislation would|would require|plans? to)\b", re.I)),
    (LegalStatus.RUMOR, re.compile(
        r"\b(report(?:edly)?|sources? say|rumou?r|allegedly|is said to|"
        r"people familiar|unconfirmed)\b", re.I)),
    (LegalStatus.POLITICAL_STATEMENT, re.compile(
        r"\b(says?|said|statement|remarks|testimony|speech|comments? on|"
        r"told (?:reporters|congress)|urges?)\b", re.I)),
]

_ASSET_PATTERNS: dict[Asset, re.Pattern[str]] = {
    Asset.BTC: re.compile(r"\b(bitcoin|btc)\b", re.I),
    Asset.ETH: re.compile(r"\b(ethereum|ether\b|eth\b)\b", re.I),
    Asset.SOL: re.compile(r"\b(solana|sol\b)\b", re.I),
}

_CRYPTO_RELEVANT = re.compile(
    r"\b(crypto|digital asset|virtual currency|blockchain|stablecoin|bitcoin|ethereum|"
    r"solana|token|exchange-traded (?:fund|product)|etf|custody|market structure|"
    r"securities|commodit(?:y|ies)|defi|spot (?:bitcoin|ether))\b", re.I)

_TOPIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "etf": re.compile(r"\b(etf|exchange-traded|spot (?:bitcoin|ether)|trust)\b", re.I),
    "stablecoin": re.compile(r"\b(stablecoin|payment stablecoin|reserve[- ]backed)\b", re.I),
    "classification": re.compile(r"\b(securit(?:y|ies)|commodit(?:y|ies)|howey|investment contract)\b", re.I),
    "tax": re.compile(r"\b(tax|irs|reporting requirement|1099|basis reporting)\b", re.I),
    "banking": re.compile(r"\b(bank|custody|custodian|sab 121|capital requirement)\b", re.I),
    "market_structure": re.compile(r"\b(market structure|clarity act|exchange registration|broker-dealer)\b", re.I),
    "enforcement": re.compile(r"\b(fraud|enforcement|violation|manipulation)\b", re.I),
}

_POSITIVE = re.compile(
    r"\b(approv|authoriz|grant|clarity|framework|guidance|permit|allow|expand access|"
    r"green ?light|favorable|support)\b", re.I)
_NEGATIVE = re.compile(
    r"\b(den(?:y|ies|ied)|reject|ban|prohibit|restrict|crackdown|charge|sue|fine|penalt|"
    r"fraud|halt|suspend|warn)\b", re.I)


def classify_legal_status(title: str, summary: str = "") -> tuple[LegalStatus, float]:
    """Classify an item, returning (status, uncertainty 0-100).

    Falls back to UNCERTAIN with high uncertainty rather than guessing, because
    mislabelling a proposal as law is the worst error this module could make.
    """
    text = f"{title}. {summary}"
    for status, pattern in _STATUS_PATTERNS:
        if pattern.search(text):
            # Regulatory decisions and enacted law are the least ambiguous.
            uncertainty = {
                LegalStatus.ADOPTED: 15.0,
                LegalStatus.REGULATORY_DECISION: 20.0,
                LegalStatus.ENFORCEMENT: 20.0,
                LegalStatus.VOTE_HELD: 30.0,
                LegalStatus.VOTE_SCHEDULED: 35.0,
                LegalStatus.CONSULTATION: 30.0,
                LegalStatus.PROPOSED: 40.0,
                LegalStatus.RUMOR: 80.0,
                LegalStatus.POLITICAL_STATEMENT: 55.0,
            }.get(status, 50.0)
            return status, uncertainty
    return LegalStatus.UNCERTAIN, 85.0


def detect_assets(text: str) -> list[Asset]:
    return [a for a, p in _ASSET_PATTERNS.items() if p.search(text)]


def detect_topics(text: str) -> list[str]:
    return [t for t, p in _TOPIC_PATTERNS.items() if p.search(text)]


def is_crypto_relevant(text: str) -> bool:
    return bool(_CRYPTO_RELEVANT.search(text))


class RegulationAnalysis(BaseModel):
    available: bool = True
    unavailable_reason: str | None = None
    events: list[RegulatoryEvent] = Field(default_factory=list)
    by_status: dict[str, int] = Field(default_factory=dict)
    binding_count: int = 0
    proposal_count: int = 0
    direction: Direction = Direction.INCONCLUSIVE
    strength: float = 0.0
    freshness: Freshness = Freshness.UNAVAILABLE
    findings: list[str] = Field(default_factory=list)


class RegulationAndPoliticsAnalyzer:
    name = "regulation_analyzer"

    def analyze(
        self,
        raw_items: list[dict],
        asset: Asset | None = None,
        now: datetime | None = None,
        unavailable_reason: str | None = None,
        lookback_days: int = 21,
    ) -> RegulationAnalysis:
        now = now or datetime.now(UTC)
        if unavailable_reason or not raw_items:
            return RegulationAnalysis(
                available=False,
                unavailable_reason=unavailable_reason
                or "UNAVAILABLE - no regulatory feed data",
            )

        cutoff = now - timedelta(days=lookback_days)
        events: list[RegulatoryEvent] = []

        for item in raw_items:
            published = item.get("published_at")
            if not isinstance(published, datetime):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            if published < cutoff:
                continue

            title = str(item.get("title", "")).strip()
            summary = str(item.get("summary", ""))[:600]
            text = f"{title}. {summary}"
            if not title or not is_crypto_relevant(text):
                continue

            status, uncertainty = classify_legal_status(title, summary)
            assets = detect_assets(text)
            topics = detect_topics(text)

            pos = len(_POSITIVE.findall(text))
            neg = len(_NEGATIVE.findall(text))
            sentiment = (
                Direction.BULLISH if pos > neg
                else Direction.BEARISH if neg > pos
                else Direction.NEUTRAL
            )

            tier = int(item.get("tier", 4))
            importance = self._importance(status, tier, topics, published, now)

            events.append(RegulatoryEvent(
                title=title, institution=str(item.get("institution") or item.get("source", "")),
                legal_status=status, published_at=published,
                summary=summary, assets_concerned=assets,
                importance=importance, sentiment=sentiment, uncertainty=uncertainty,
                source_url=str(item.get("url", "")), source_name=str(item.get("source", "")),
                tier=tier,
            ))

        if asset:
            events = [e for e in events if not e.assets_concerned or asset in e.assets_concerned]

        events.sort(key=lambda e: (e.importance, e.published_at), reverse=True)
        events = events[:25]

        by_status: dict[str, int] = {}
        for e in events:
            by_status[e.legal_status.value] = by_status.get(e.legal_status.value, 0) + 1

        binding = sum(1 for e in events if e.legal_status.is_binding)
        proposals = sum(1 for e in events if e.legal_status is LegalStatus.PROPOSED)

        score = 0.0
        findings: list[str] = []
        for e in events[:10]:
            # Binding decisions move markets; proposals and statements much less.
            weight = {
                LegalStatus.ADOPTED: 1.0, LegalStatus.REGULATORY_DECISION: 0.9,
                LegalStatus.ENFORCEMENT: 0.8, LegalStatus.VOTE_HELD: 0.6,
                LegalStatus.VOTE_SCHEDULED: 0.35, LegalStatus.CONSULTATION: 0.3,
                LegalStatus.PROPOSED: 0.25, LegalStatus.POLITICAL_STATEMENT: 0.15,
                LegalStatus.RUMOR: 0.05, LegalStatus.UNCERTAIN: 0.1,
            }[e.legal_status]
            impact = e.importance / 100.0 * 40.0 * weight
            if e.sentiment is Direction.BULLISH:
                score += impact
            elif e.sentiment is Direction.BEARISH:
                score -= impact

        for e in events[:5]:
            findings.append(
                f"[{e.legal_status.value}] {e.institution}: {e.title[:120]} "
                f"({e.published_at:%Y-%m-%d})"
            )
        if proposals:
            findings.append(
                f"{proposals} item(s) are PROPOSALS, not adopted law - they change nothing "
                "legally until enacted"
            )

        direction = (
            Direction.BULLISH if score > 10
            else Direction.BEARISH if score < -10
            else Direction.NEUTRAL if events else Direction.INCONCLUSIVE
        )
        newest = max((e.published_at for e in events), default=None)
        from ..core.freshness import compute_freshness

        return RegulationAnalysis(
            available=bool(events),
            unavailable_reason=None if events else "No crypto-relevant regulatory items in window",
            events=events, by_status=by_status,
            binding_count=binding, proposal_count=proposals,
            direction=direction, strength=round(max(-100.0, min(100.0, score)), 1),
            freshness=compute_freshness(newest, "regulation"),
            findings=findings,
        )

    def _importance(
        self, status: LegalStatus, tier: int, topics: list[str], published: datetime, now: datetime
    ) -> float:
        base = {
            LegalStatus.ADOPTED: 90.0, LegalStatus.REGULATORY_DECISION: 85.0,
            LegalStatus.ENFORCEMENT: 70.0, LegalStatus.VOTE_HELD: 65.0,
            LegalStatus.VOTE_SCHEDULED: 55.0, LegalStatus.CONSULTATION: 45.0,
            LegalStatus.PROPOSED: 45.0, LegalStatus.POLITICAL_STATEMENT: 30.0,
            LegalStatus.RUMOR: 15.0, LegalStatus.UNCERTAIN: 25.0,
        }[status]
        base *= {1: 1.0, 2: 0.85, 3: 0.65, 4: 0.4}.get(tier, 0.4)
        if {"etf", "market_structure", "classification"} & set(topics):
            base *= 1.15
        age_days = (now - published).total_seconds() / 86400.0
        base *= max(0.35, 1.0 - age_days / 30.0)
        return min(100.0, base)
