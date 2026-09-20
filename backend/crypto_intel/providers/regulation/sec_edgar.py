"""Crypto product filings, read from EDGAR rather than from an article about it.

The SEC's full-text search returns the filings themselves. Each form sits at a
precise point of a ladder, and the whole value of the source is that the rungs
are not the same thing:

    FILED        a request exists                     (S-1, 19b-4)
    AMENDED      the request was modified             (S-1/A, 19b-4 amendment)
    ACKNOWLEDGED the SEC opened its review            (notice of filing)
    APPROVED     the rule change was approved         (approval order)
    EFFECTIVE    the registration became effective    (EFFECT, 8-A)
    LISTED       the product exists on an exchange    (424B, prospectus)
    TRADING      it trades                            (observed elsewhere)

A filing is never announced as an approval. The engine that reads these events
keeps the stage, and the wording on screen follows the stage.

SEC policy requires an automated caller to identify itself with a contact
address; that is what ``settings.sec_user_agent`` carries. Without it the
source stays unavailable rather than being fetched anonymously.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

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
from ...settings import get_settings
from ..base import BaseProvider, FetchRequest, FetchResult
from ..http import get_http

EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_VIEWER = "https://www.sec.gov/cgi-bin/browse-edgar"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"


class FilingStage(StrEnum):
    FILED = "FILED"
    AMENDED = "AMENDED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    APPROVED = "APPROVED"
    EFFECTIVE = "EFFECTIVE"
    LISTED = "LISTED"
    TRADING = "TRADING"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


STAGE_FR = {
    FilingStage.FILED: "Dossier déposé",
    FilingStage.AMENDED: "Dossier modifié",
    FilingStage.ACKNOWLEDGED: "Examen ouvert par la SEC",
    FilingStage.APPROVED: "Approuvé",
    FilingStage.EFFECTIVE: "Enregistrement effectif",
    FilingStage.LISTED: "Produit coté",
    FilingStage.TRADING: "En négociation",
    FilingStage.WITHDRAWN: "Retiré",
    FilingStage.UNKNOWN: "Étape inconnue",
}
#: The sentence that prevents the classic mistake, stage by stage.
STAGE_CAVEAT = {
    FilingStage.FILED: "Un dépôt n'est pas une approbation.",
    FilingStage.AMENDED: "Une modification n'est pas une approbation.",
    FilingStage.ACKNOWLEDGED: "L'ouverture d'un examen n'est pas une approbation.",
    FilingStage.APPROVED: "Approuvé ne veut pas dire coté ni négocié.",
    FilingStage.EFFECTIVE: "Effectif ne veut pas dire que le produit se négocie déjà.",
    FilingStage.LISTED: "Coté : les volumes réels restent à observer.",
    FilingStage.TRADING: "En négociation : l'effet sur le prix reste à mesurer.",
    FilingStage.WITHDRAWN: "Retiré : le dossier n'avance plus.",
    FilingStage.UNKNOWN: "Étape non identifiable dans le formulaire.",
}

#: Form type -> stage. Order matters: the longest match wins.
FORM_STAGES: tuple[tuple[str, FilingStage], ...] = (
    ("19B-4/A", FilingStage.AMENDED),
    ("S-1/A", FilingStage.AMENDED),
    ("S-3/A", FilingStage.AMENDED),
    ("F-1/A", FilingStage.AMENDED),
    ("424B", FilingStage.LISTED),
    ("8-A12B", FilingStage.EFFECTIVE),
    ("8-A", FilingStage.EFFECTIVE),
    ("EFFECT", FilingStage.EFFECTIVE),
    ("19B-4", FilingStage.FILED),
    ("S-1", FilingStage.FILED),
    ("S-3", FilingStage.FILED),
    ("F-1", FilingStage.FILED),
    ("RW", FilingStage.WITHDRAWN),
    ("AW", FilingStage.WITHDRAWN),
)

ASSET_TERMS = {
    Asset.BTC: "bitcoin",
    Asset.ETH: "ethereum",
    Asset.SOL: "solana",
}
#: Filings older than this are history, not a catalyst.
RECENT_WINDOW = timedelta(days=90)
#: Only the forms that move a product along the ladder. Without this filter
#: EDGAR mostly returns portfolio reports, which say nothing about a stage.
WANTED_FORMS = "19b-4,S-1,S-3,424B4,424B3,8-A12B,EFFECT,F-1,RW"


def stage_for_form(form: str) -> FilingStage:
    upper = (form or "").upper().strip()
    for prefix, stage in FORM_STAGES:
        if upper.startswith(prefix):
            return stage
    return FilingStage.UNKNOWN


def _importance(stage: FilingStage) -> EventImportance:
    return {
        FilingStage.APPROVED: EventImportance.CRITICAL,
        FilingStage.EFFECTIVE: EventImportance.HIGH,
        FilingStage.LISTED: EventImportance.HIGH,
        FilingStage.TRADING: EventImportance.HIGH,
        FilingStage.ACKNOWLEDGED: EventImportance.MEDIUM,
    }.get(stage, EventImportance.MEDIUM)


def parse_search(payload: dict[str, Any], asset: Asset) -> list[dict[str, Any]]:
    """EDGAR full-text hits -> the fields a filing event needs."""

    hits = ((payload or {}).get("hits") or {}).get("hits") or []
    out: list[dict[str, Any]] = []
    for hit in hits:
        source = hit.get("_source") or {}
        form = str(source.get("file_type") or source.get("root_form") or "")
        filed = str(source.get("file_date") or "")
        names = source.get("display_names") or []
        try:
            when = datetime.strptime(filed, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        identifier = str(hit.get("_id") or "")
        accession, _, document = identifier.partition(":")
        cik = (source.get("ciks") or ["0"])[0]
        url = (
            f"{ARCHIVE}/{str(cik).lstrip('0')}/{accession.replace('-', '')}/{document}"
            if accession and document else "https://www.sec.gov/edgar/search/"
        )
        out.append({
            "form": form,
            "filed_at": when,
            "company": str(names[0]) if names else "Émetteur non identifié",
            "url": url,
            "accession": accession,
            "asset": asset,
        })
    return out


def build_filing_event(row: dict[str, Any], source: str) -> FutureEvent:
    stage = stage_for_form(row["form"])
    asset: Asset = row["asset"]
    company = re.sub(r"\s+\(CIK.*\)$", "", row["company"]).strip()
    return FutureEvent(
        event_type=f"SEC_FILING_{stage.value}",
        category=FutureEventCategory.REGULATION,
        schedule_type=EventScheduleType.UNSCHEDULED,
        title=f"{company} — {row['form']} ({STAGE_FR[stage].lower()})",
        source=source,
        source_tier=FutureEventSourceTier.A,
        source_url=row["url"],
        source_reference=row["accession"] or row["url"],
        source_published_at=row["filed_at"],
        detected_at=datetime.now(UTC),
        status=FutureEventStatus.ACTIVE,
        affected_assets=[asset],
        importance=_importance(stage),
        # A filing is a fact about a process, not a direction for the price.
        directional_effect=DirectionalBias.NEUTRAL,
        magnitude_effect=ExpectedMovement.NORMAL,
        time_horizon=DecisionHorizon.D30,
        confidence=0.9,
        source_references=[EventSourceReference(
            source=source, url=row["url"], tier=FutureEventSourceTier.A,
            published_at=row["filed_at"],
        )],
        metadata={
            "stage": stage.value,
            "stage_label": STAGE_FR[stage],
            "stage_caveat": STAGE_CAVEAT[stage],
            "form": row["form"],
            "issuer": company,
            "subject": f"{asset.value} {row['form']}",
            "entities": [company, asset.value],
            "source_type": "OFFICIAL",
            "catalyst": True,
        },
    )


class SecEdgarFilingsProvider(BaseProvider):
    name = "sec_edgar"
    source = "SEC EDGAR"
    category = ProviderCategory.REGULATION
    capabilities = ("events.regulation.sec_filings",)
    source_url = "https://www.sec.gov/edgar/search/"
    base_confidence = 95.0

    def _headers(self) -> dict[str, str] | None:
        agent = get_settings().sec_user_agent.strip()
        # SEC policy: an automated caller declares a contact address.
        if "@" not in agent:
            return None
        return {"User-Agent": agent, "Accept": "application/json"}

    async def fetch(self, request: FetchRequest) -> FetchResult:
        headers = self._headers()
        if headers is None:
            return FetchResult.failure(
                FetchStatus.NOT_CONFIGURED, self.name,
                "EDGAR exige un contact déclaré (SEC_USER_AGENT) : source non interrogée.",
            )
        http = get_http()
        since = (datetime.now(UTC) - RECENT_WINDOW).date().isoformat()
        assets = [request.asset] if request.asset else list(ASSET_TERMS)
        events: list[FutureEvent] = []
        for asset in assets:
            res = await http.get_json(
                EDGAR_SEARCH, provider=self.name, headers=headers,
                params={
                    "q": f'"{ASSET_TERMS[asset]}"',
                    "forms": WANTED_FORMS,
                    "startdt": since,
                    "enddt": datetime.now(UTC).date().isoformat(),
                },
                cache_ttl=6 * 3600, rate_limit_per_min=6, retries=1,
            )
            if not res.ok or not isinstance(res.data, dict):
                continue
            for row in parse_search(res.data, asset)[:10]:
                # A form whose stage cannot be read teaches nothing: skipped
                # rather than shown as "unknown stage".
                if stage_for_form(row["form"]) is FilingStage.UNKNOWN:
                    continue
                events.append(build_filing_event(row, self.source))
        if not events:
            return FetchResult.failure(FetchStatus.NO_DATA, self.name,
                                       "aucun dépôt récent trouvé")
        return FetchResult.success_events(events, self.name)
