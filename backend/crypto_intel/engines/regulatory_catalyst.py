"""Stage-aware regulatory catalyst classification.

The engine describes what an official source actually says.  A markup, a
procedural motion and enacted law are separate states; no stage implies the
next one.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from ..future_events.models import FutureEvent


class RegulatoryStage(StrEnum):
    DISCUSSION = "DISCUSSION"
    HEARING = "HEARING"
    INTRODUCED = "INTRODUCED"
    COMMITTEE_MARKUP = "COMMITTEE_MARKUP"
    COMMITTEE_APPROVAL = "COMMITTEE_APPROVAL"
    MOTION = "MOTION"
    CLOTURE = "CLOTURE"
    PASSED_HOUSE = "PASSED_HOUSE"
    PASSED_SENATE = "PASSED_SENATE"
    RECONCILIATION = "RECONCILIATION"
    PRESENTED_TO_PRESIDENT = "PRESENTED_TO_PRESIDENT"
    SIGNED_INTO_LAW = "SIGNED_INTO_LAW"
    EFFECTIVE = "EFFECTIVE"
    PROPOSED_RULE = "PROPOSED_RULE"
    COMMENT_PERIOD = "COMMENT_PERIOD"
    FINAL_RULE = "FINAL_RULE"
    ENFORCEMENT = "ENFORCEMENT"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    UNKNOWN = "UNKNOWN"


class RegulatoryCatalystAnalysis(BaseModel):
    available: bool
    event_id: str | None = None
    institution: str | None = None
    subject: str | None = None
    stage: RegulatoryStage = RegulatoryStage.UNKNOWN
    stage_label: str = "Statut à confirmer"
    completed_stage_only: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    source_url: str | None = None
    explanation: str = ""


_RULES: tuple[tuple[tuple[str, ...], RegulatoryStage, str], ...] = (
    (("signed into law", "signed the act", "became law"), RegulatoryStage.SIGNED_INTO_LAW, "Signé et promulgué"),
    (("presented to president", "sent to the president"), RegulatoryStage.PRESENTED_TO_PRESIDENT, "Transmis au président"),
    (("passed the senate", "senate passed"), RegulatoryStage.PASSED_SENATE, "Adopté par le Sénat"),
    (("passed the house", "house passed"), RegulatoryStage.PASSED_HOUSE, "Adopté par la Chambre"),
    (("committee approved", "ordered to be reported", "reported favorably"), RegulatoryStage.COMMITTEE_APPROVAL, "Approuvé en commission"),
    (("cloture",), RegulatoryStage.CLOTURE, "Procédure de clôture"),
    (("markup",), RegulatoryStage.COMMITTEE_MARKUP, "Examen en commission"),
    (("hearing", "roundtable", "testimony"), RegulatoryStage.HEARING, "Audition ou table ronde"),
    (("introduced", "introduction of"), RegulatoryStage.INTRODUCED, "Texte déposé"),
    (("reconciliation",), RegulatoryStage.RECONCILIATION, "Réconciliation des textes"),
    (("motion",), RegulatoryStage.MOTION, "Motion procédurale"),
    (("final rule", "adopts rules", "adopted rules"), RegulatoryStage.FINAL_RULE, "Règle définitive"),
    (("proposed rule", "proposes", "proposal"), RegulatoryStage.PROPOSED_RULE, "Règle proposée"),
    (("comment period", "comments due"), RegulatoryStage.COMMENT_PERIOD, "Période de consultation"),
    (("charges", "charged", "enforcement", "settled charges"), RegulatoryStage.ENFORCEMENT, "Mesure d’exécution"),
    (("effective date", "takes effect"), RegulatoryStage.EFFECTIVE, "Entrée en vigueur"),
    (("discussion", "forum", "remarks"), RegulatoryStage.DISCUSSION, "Discussion publique"),
)


class RegulatoryCatalystEngine:
    @staticmethod
    def classify_stage(text: str) -> RegulatoryStage:
        lowered = " ".join(text.lower().split())
        for phrases, stage, _label in _RULES:
            if any(phrase in lowered for phrase in phrases):
                return stage
        return RegulatoryStage.ANNOUNCEMENT if lowered else RegulatoryStage.UNKNOWN

    @staticmethod
    def stage_label(stage: RegulatoryStage) -> str:
        return next((label for _phrases, candidate, label in _RULES if candidate is stage), "Annonce officielle" if stage is RegulatoryStage.ANNOUNCEMENT else "Statut à confirmer")

    def analyze(self, event: FutureEvent | None) -> RegulatoryCatalystAnalysis:
        if event is None:
            return RegulatoryCatalystAnalysis(
                available=False,
                explanation="Aucun événement réglementaire officiel disponible.",
            )
        raw_stage = event.metadata.get("regulatory_stage")
        try:
            stage = RegulatoryStage(str(raw_stage)) if raw_stage else self.classify_stage(event.title)
        except ValueError:
            stage = RegulatoryStage.UNKNOWN
        return RegulatoryCatalystAnalysis(
            available=True,
            event_id=event.canonical_event_id,
            institution=event.source,
            subject=str(event.metadata.get("subject") or event.title),
            stage=stage,
            stage_label=self.stage_label(stage),
            evidence_ids=event.evidence_ids,
            source_url=event.source_url,
            explanation=(
                f"Étape confirmée par la source : {self.stage_label(stage)}. "
                "Cette étape ne vaut pas adoption des étapes suivantes."
            ),
        )
