"""Protocol proposals read from the repositories that own them.

    Solana   solana-foundation/solana-improvement-documents (SIMD)
    Ethereum ethereum/EIPs (EIP)

A press article may point at a proposal; the proposal itself is what is read
here. Each document carries its own ``status`` field, and that status is
mapped onto one lifecycle, because the difference between the stages is the
whole point:

    a proposal is not an approved vote,
    an approved vote is not an activation,
    and an activation is not a price effect.

The economic reading follows the same discipline. "Reduce issuance" is an
effect on future supply, stated as such; it is never turned into a bullish
signal. Direction stays NEUTRAL: what the market does with it is measured
elsewhere, against the price.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, ClassVar

from ...core.enums import Asset, FetchStatus, ProviderCategory
from ...future_events.models import (
    DecisionHorizon,
    DirectionalBias,
    EventImportance,
    EventScheduleType,
    EventSourceReference,
    ExpectedMovement,
    FutureEvent,
    FutureEventCategory,
    FutureEventSourceTier,
    FutureEventStatus,
)
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

GITHUB = "https://api.github.com"


class ProposalStage(StrEnum):
    PROPOSED = "PROPOSED"
    DISCUSSION = "DISCUSSION"
    VOTING = "VOTING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IMPLEMENTATION_PENDING = "IMPLEMENTATION_PENDING"
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


STAGE_FR = {
    ProposalStage.PROPOSED: "Proposée",
    ProposalStage.DISCUSSION: "En discussion",
    ProposalStage.VOTING: "En vote",
    ProposalStage.APPROVED: "Approuvée",
    ProposalStage.REJECTED: "Rejetée",
    ProposalStage.IMPLEMENTATION_PENDING: "Implémentation en attente",
    ProposalStage.ACTIVE: "Active",
    ProposalStage.CANCELLED: "Abandonnée",
    ProposalStage.UNKNOWN: "Statut inconnu",
}
#: What each stage does *not* mean - carried to the screen so no one reads a
#: proposal as an activation.
STAGE_CAVEAT = {
    ProposalStage.PROPOSED: "Une proposition n'est ni un vote ni une activation.",
    ProposalStage.DISCUSSION: "En discussion : rien n'est décidé.",
    ProposalStage.VOTING: "Le vote est en cours : son issue n'est pas connue.",
    ProposalStage.APPROVED: "Approuvée ne veut pas dire activée sur le réseau.",
    ProposalStage.IMPLEMENTATION_PENDING: "Le code existe ; l'activation reste à venir.",
    ProposalStage.ACTIVE: "Active sur le réseau : l'effet sur le prix reste à mesurer.",
    ProposalStage.REJECTED: "Rejetée : aucun effet attendu.",
    ProposalStage.CANCELLED: "Abandonnée : aucun effet attendu.",
    ProposalStage.UNKNOWN: "Statut non lisible dans le document.",
}

SIMD_STATUS = {
    "idea": ProposalStage.PROPOSED,
    "draft": ProposalStage.PROPOSED,
    "review": ProposalStage.DISCUSSION,
    "vote": ProposalStage.VOTING,
    "voting": ProposalStage.VOTING,
    "accepted": ProposalStage.APPROVED,
    "implemented": ProposalStage.IMPLEMENTATION_PENDING,
    "activated": ProposalStage.ACTIVE,
    "living": ProposalStage.ACTIVE,
    "withdrawn": ProposalStage.CANCELLED,
    "rejected": ProposalStage.REJECTED,
    "stagnant": ProposalStage.CANCELLED,
}
EIP_STATUS = {
    "idea": ProposalStage.PROPOSED,
    "draft": ProposalStage.PROPOSED,
    "review": ProposalStage.DISCUSSION,
    "last call": ProposalStage.VOTING,
    "final": ProposalStage.APPROVED,
    "living": ProposalStage.ACTIVE,
    "stagnant": ProposalStage.CANCELLED,
    "withdrawn": ProposalStage.CANCELLED,
}

#: Words that make a proposal economically relevant. Without one of these the
#: document is a technical change, kept at low importance.
ECONOMIC_WORDS = (
    "inflation", "issuance", "emission", "burn", "fee", "reward", "staking",
    "supply", "unlock", "buyback", "treasury", "mint",
)
_DECREASE = re.compile(r"\b(reduc\w+|decreas\w+|lower\w*|cut\w*|slow\w*|halv\w*)\b", re.I)
_INCREASE = re.compile(r"\b(increas\w+|rais\w+|higher|expand\w*|boost\w*)\b", re.I)

#: Only recent activity is turned into events: an old proposal is history.
RECENT_WINDOW = timedelta(days=120)


def parse_front_matter(text: str) -> dict[str, str]:
    """The document's own header. Nested keys (authors) are skipped."""

    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line.startswith((" ", "-", "\t")):
            continue
        key, _, value = line.partition(":")
        if value.strip():
            out[key.strip().lower()] = value.strip().strip("'\"")
    return out


def economic_effect(title: str, body: str) -> dict[str, Any]:
    """What the document changes economically - never what the price should do."""

    haystack = f"{title} {body[:1500]}".lower()
    touched = sorted({word for word in ECONOMIC_WORDS if word in haystack})
    if not touched:
        return {"economic": False, "supply_effect": "UNKNOWN", "topics": []}
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", body[:2500]) if any(w in s.lower() for w in touched)]
    window = " ".join(sentences[:3]) or title
    supply = "UNKNOWN"
    if any(w in window.lower() for w in ("issuance", "inflation", "emission", "mint", "supply")):
        if _DECREASE.search(window):
            supply = "ISSUANCE_DOWN"
        elif _INCREASE.search(window):
            supply = "ISSUANCE_UP"
    if "burn" in window.lower() and supply == "UNKNOWN":
        supply = "BURN"
    return {"economic": True, "supply_effect": supply, "topics": touched,
            "evidence": window[:280]}


def _importance(stage: ProposalStage, effect: dict[str, Any]) -> EventImportance:
    if not effect["economic"]:
        return EventImportance.LOW
    if stage in {ProposalStage.APPROVED, ProposalStage.ACTIVE, ProposalStage.VOTING}:
        return EventImportance.HIGH
    return EventImportance.MEDIUM


def build_event(
    *,
    asset: Asset,
    kind: str,
    number: str,
    title: str,
    stage: ProposalStage,
    status_raw: str,
    url: str,
    updated_at: datetime,
    body: str,
    provider: str,
    source: str,
) -> FutureEvent:
    effect = economic_effect(title, body)
    label = "SIMD" if kind == "SIMD" else "EIP"
    return FutureEvent(
        event_type=f"{label}_{stage.value}",
        category=FutureEventCategory.PROTOCOL,
        schedule_type=EventScheduleType.UNSCHEDULED,
        title=f"{label}-{number} — {title}",
        source=source,
        source_tier=FutureEventSourceTier.A,
        source_url=url,
        source_reference=f"{label}-{number}",
        source_published_at=updated_at,
        detected_at=datetime.now(UTC),
        status=FutureEventStatus.ACTIVE if stage is ProposalStage.ACTIVE else FutureEventStatus.UPCOMING,
        affected_assets=[asset],
        importance=_importance(stage, effect),
        # A protocol change has no direction of its own: the market decides.
        directional_effect=DirectionalBias.NEUTRAL,
        magnitude_effect=ExpectedMovement.NORMAL,
        time_horizon=DecisionHorizon.D30,
        confidence=0.9,
        source_references=[EventSourceReference(
            source=source, url=url, tier=FutureEventSourceTier.A,
            published_at=updated_at,
        )],
        metadata={
            "stage": stage.value,
            "stage_label": STAGE_FR[stage],
            "stage_caveat": STAGE_CAVEAT[stage],
            "status_raw": status_raw,
            "proposal": f"{label}-{number}",
            "subject": f"{label}-{number}",
            "entities": [label, asset.value],
            "economic_effect": effect,
            "source_type": "PRIMARY",
            "catalyst": True,
        },
    )


class _GithubProposalsProvider(BaseProvider):
    category = ProviderCategory.NEWS
    base_confidence = 92.0
    repo = ""
    directory = ""
    kind = ""
    asset = Asset.BTC
    status_map: ClassVar[dict[str, ProposalStage]] = {}

    def _stage(self, raw: str) -> ProposalStage:
        return self.status_map.get(raw.strip().lower(), ProposalStage.UNKNOWN)

    async def _recent_paths(self, limit: int = 12) -> list[tuple[str, datetime]]:
        res = await get_http().get_json(
            f"{GITHUB}/repos/{self.repo}/commits", provider=self.name,
            params={"path": self.directory, "per_page": limit},
            cache_ttl=6 * 3600, rate_limit_per_min=20, retries=1,
        )
        if not res.ok or not isinstance(res.data, list):
            return []
        cutoff = datetime.now(UTC) - RECENT_WINDOW
        out: list[tuple[str, datetime]] = []
        seen: set[str] = set()
        for commit in res.data:
            message = str((commit.get("commit") or {}).get("message") or "").splitlines()[0]
            when = commit.get("commit", {}).get("committer", {}).get("date")
            try:
                stamp = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if stamp < cutoff:
                continue
            match = re.search(r"(SIMD|EIP)[- ]?(\d{3,4})", message, re.I)
            if not match:
                continue
            number = match.group(2)
            if number in seen:
                continue
            seen.add(number)
            out.append((number, stamp))
        return out

    async def _document(self, number: str) -> tuple[str, str] | None:
        """(markdown, html url) for a proposal number, or None."""

        listing = await get_http().get_json(
            f"{GITHUB}/repos/{self.repo}/contents/{self.directory}", provider=self.name,
            params={"per_page": 400}, cache_ttl=12 * 3600, rate_limit_per_min=20, retries=1,
        )
        if not listing.ok or not isinstance(listing.data, list):
            return None
        padded = number.zfill(4)
        entry = next(
            (
                item for item in listing.data
                if str(item.get("name", "")).startswith((f"{padded}-", f"eip-{int(number)}."))
            ),
            None,
        )
        if entry is None:
            return None
        res = await get_http().get_json(
            str(entry["url"]), provider=self.name, cache_ttl=12 * 3600,
            rate_limit_per_min=20, retries=1,
        )
        if not res.ok or not isinstance(res.data, dict):
            return None
        try:
            text = base64.b64decode(res.data.get("content", "")).decode("utf-8", "replace")
        except (ValueError, TypeError):
            return None
        return text, str(entry.get("html_url") or res.data.get("html_url") or "")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        recent = await self._recent_paths()
        if not recent:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name, "aucune activité récente")
        events: list[FutureEvent] = []
        for number, stamp in recent[:6]:
            document = await self._document(number)
            if document is None:
                continue
            text, url = document
            front = parse_front_matter(text)
            status_raw = front.get("status", "")
            title = front.get("title", f"{self.kind}-{number}")
            body = text.split("---", 2)[-1]
            events.append(build_event(
                asset=self.asset, kind=self.kind, number=number, title=title,
                stage=self._stage(status_raw), status_raw=status_raw, url=url,
                updated_at=stamp, body=body, provider=self.name, source=self.source,
            ))
        if not events:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name)
        return FetchResult.success_events(events, self.name)


class SolanaSimdProvider(_GithubProposalsProvider):
    name = "solana_simd"
    source = "Solana Improvement Documents (dépôt officiel)"
    capabilities = ("events.protocol.solana_simd",)
    source_url = "https://github.com/solana-foundation/solana-improvement-documents"
    repo = "solana-foundation/solana-improvement-documents"
    directory = "proposals"
    kind = "SIMD"
    asset = Asset.SOL
    status_map: ClassVar[dict[str, ProposalStage]] = SIMD_STATUS


class EthereumEipProvider(_GithubProposalsProvider):
    name = "ethereum_eip"
    source = "Ethereum Improvement Proposals (dépôt officiel)"
    capabilities = ("events.protocol.ethereum_eip",)
    source_url = "https://github.com/ethereum/EIPs"
    repo = "ethereum/EIPs"
    directory = "EIPS"
    kind = "EIP"
    asset = Asset.ETH
    status_map: ClassVar[dict[str, ProposalStage]] = EIP_STATUS
