"""Deterministic verification of claims made in transcripts and media.

This module deliberately does not extract facts with an LLM and never fetches
data.  It accepts a claim plus already collected :class:`PointInTimeValue`
objects, classifies the wording, resolves only unambiguous entities, and
recomputes quantitative claims from values that were knowable at the claim's
timestamp.

The conservative ordering is intentional:

* conditional language remains a forecast even if a matching number exists;
* an unresolved entity stops numeric verification rather than guessing;
* temporal co-occurrence never proves direct causality;
* only then may a deterministic calculation confirm or contradict a figure.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.pointintime import Availability, PointInTimeValue, as_of_filter


class ClaimVerificationStatus(StrEnum):
    """Required outcomes from section 8 of the product specification."""

    CONFIRMED = "CONFIRMED"
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIABLE = "UNVERIFIABLE"
    AMBIGUOUS = "AMBIGUOUS"
    OUTDATED = "OUTDATED"
    OPINION = "OPINION"
    FORECAST = "FORECAST"


class ClaimType(StrEnum):
    QUANTITATIVE_CHANGE = "QUANTITATIVE_CHANGE"
    CAUSAL = "CAUSAL"
    FORECAST = "FORECAST"
    ENTITY = "ENTITY"
    FACTUAL = "FACTUAL"
    OPINION = "OPINION"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ClaimPeriod(BaseModel):
    """The period the speaker claims to describe, not an inferred data window."""

    model_config = ConfigDict(frozen=True)

    label: str
    start: datetime | None = None
    end: datetime | None = None
    frequency: str | None = None

    @field_validator("start", "end")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None


class ClaimEntity(BaseModel):
    """One entity mention without silently promoting a candidate to an identity."""

    model_config = ConfigDict(frozen=True)

    mention: str
    entity_type: str
    canonical_id: str | None = None
    canonical_name: str | None = None
    candidates: list[str] = Field(default_factory=list)
    verified: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)


class VerificationSource(BaseModel):
    """The exact point-in-time input (or causal study) used for a verdict."""

    model_config = ConfigDict(frozen=True)

    source: str
    metric: str
    role: str
    value: float | None = None
    unit: str | None = None
    observation_time: datetime | None = None
    release_time: datetime | None = None
    availability: Availability | None = None
    revision_number: int = 0
    source_url: str | None = None

    @field_validator("observation_time", "release_time")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None


class CausalEvidence(BaseModel):
    """Explicit evidence for causality; ordinary price observations are not enough."""

    model_config = ConfigDict(frozen=True)

    cause: str
    effect: str
    source: str
    method: str
    supports_direct_causality: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    source_url: str | None = None


class Claim(BaseModel):
    """A complete, serialisable audit record for one checked assertion."""

    model_config = ConfigDict(frozen=True)

    claim_id: str = ""
    original_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    claim_type: ClaimType
    entities: list[ClaimEntity] = Field(default_factory=list)
    claimed_value: float | None = None
    claimed_unit: str | None = None
    claimed_period: ClaimPeriod | None = None
    claimed_cause: str | None = None
    source_timestamp: datetime | None = None
    verification_sources: list[VerificationSource] = Field(default_factory=list)
    calculated_value: float | None = None
    comparison_method: str
    verification_status: ClaimVerificationStatus
    confidence: float = Field(ge=0.0, le=100.0)
    notes: list[str] = Field(default_factory=list)

    @field_validator("source_timestamp")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None

    def model_post_init(self, __context: Any) -> None:
        if self.claim_id:
            return
        timestamp = self.source_timestamp.isoformat() if self.source_timestamp else "unknown-time"
        raw = f"{self.normalized_text}|{timestamp}"
        object.__setattr__(self, "claim_id", "claim_" + hashlib.sha1(raw.encode()).hexdigest()[:16])


# A descriptive alias is convenient for callers while keeping the required
# payload name ``Claim``.
VerifiedClaim = Claim


@dataclass(slots=True, frozen=True)
class EntityDefinition:
    canonical_id: str
    canonical_name: str
    entity_type: str
    aliases: tuple[str, ...]
    metrics: tuple[str, ...] = ()


DEFAULT_ENTITY_CATALOG: tuple[EntityDefinition, ...] = (
    EntityDefinition(
        canonical_id="NASDAQ_COMPOSITE",
        canonical_name="Nasdaq Composite",
        entity_type="INDEX",
        aliases=("nasdaq composite", "composite nasdaq", "ixic"),
        metrics=("macro.nasdaq", "market.nasdaq_composite.close"),
    ),
    EntityDefinition(
        canonical_id="NASDAQ_100",
        canonical_name="Nasdaq-100",
        entity_type="INDEX",
        aliases=("nasdaq-100", "nasdaq 100", "ndx"),
        metrics=("macro.nasdaq100", "market.nasdaq_100.close"),
    ),
    EntityDefinition(
        canonical_id="DJIA",
        canonical_name="Dow Jones Industrial Average",
        entity_type="INDEX",
        aliases=(
            "dow jones industrial average",
            "dow jones",
            "djia",
        ),
        metrics=("macro.dow", "market.dow.close"),
    ),
    EntityDefinition(
        canonical_id="SP500",
        canonical_name="S&P 500",
        entity_type="INDEX",
        aliases=("s&p 500", "s and p 500", "standard and poor's 500"),
        metrics=("macro.sp500",),
    ),
    EntityDefinition(
        canonical_id="RUSSELL_2000",
        canonical_name="Russell 2000",
        entity_type="INDEX",
        aliases=("russell 2000", "rut"),
        metrics=("macro.russell2000",),
    ),
    EntityDefinition(
        canonical_id="NIKKEI_225",
        canonical_name="Nikkei 225",
        entity_type="INDEX",
        aliases=("nikkei 225", "nikkei", "n225"),
        metrics=("macro.nikkei225",),
    ),
    EntityDefinition(
        canonical_id="EURO_STOXX_50",
        canonical_name="Euro Stoxx 50",
        entity_type="INDEX",
        aliases=("euro stoxx 50", "stoxx 50", "stoxx50e"),
        metrics=("macro.eurostoxx50",),
    ),
    EntityDefinition(
        canonical_id="BTC",
        canonical_name="Bitcoin",
        entity_type="ASSET",
        aliases=("bitcoin", "btc"),
        metrics=("price.btc.close", "market.btc.close"),
    ),
    EntityDefinition(
        canonical_id="ETH",
        canonical_name="Ethereum",
        entity_type="ASSET",
        aliases=("ethereum", "ether", "eth"),
        metrics=("price.eth.close",),
    ),
    EntityDefinition(
        canonical_id="SOL",
        canonical_name="Solana",
        entity_type="ASSET",
        aliases=("solana", "sol"),
        metrics=("price.sol.close",),
    ),
    EntityDefinition(
        canonical_id="JEROME_POWELL",
        canonical_name="Jerome Powell",
        entity_type="PERSON",
        aliases=("jerome powell", "jerome h powell", "jay powell", "powell"),
    ),
)


_MONTHS = {
    "janvier": 1,
    "january": 1,
    "fevrier": 2,
    "february": 2,
    "mars": 3,
    "march": 3,
    "avril": 4,
    "april": 4,
    "mai": 5,
    "may": 5,
    "juin": 6,
    "june": 6,
    "juillet": 7,
    "july": 7,
    "aout": 8,
    "august": 8,
    "septembre": 9,
    "september": 9,
    "octobre": 10,
    "october": 10,
    "novembre": 11,
    "november": 11,
    "decembre": 12,
    "december": 12,
}

_FORECAST_RE = re.compile(
    r"\b(si|scenario|prevision|projection|conditionnel|pourrait|pourraient|"
    r"baisserait|chuterait|monterait|devrait|risque de|il est possible)\b"
)
_CAUSAL_RE = re.compile(
    r"\b(a cause|a directement cause|a provoque|a directement provoque|"
    r"a declenche|a entraine|est responsable de|fait chuter|caused|triggered|led to)\b"
)
_OPINION_RE = re.compile(r"\b(a mon avis|je pense|je crois|selon moi|in my opinion)\b")
_TODAY_RE = re.compile(r"\b(aujourd'hui|ce jour|today)\b")
_CURRENT_MARKET_RE = re.compile(
    r"\b(actuellement|maintenant|en ce moment|a l'heure actuelle|currently|now|at present)\b"
)
_DRAWDOWN_FROM_PEAK_RE = re.compile(
    r"(?:\bdepuis\s+(?:son|le|un|ce)\s+(?:plus haut|sommet|pic|record)\b|"
    r"\b(?:sous|en dessous de)\s+(?:son|le|un|ce)\s+(?:plus haut|sommet|pic|record)\b|"
    r"\b(?:from|below|off)\s+(?:its|the|a)\s+(?:peak|high|record)\b|"
    r"\bdrawdown\b)"
)
_SOL_CRYPTO_CONTEXT_RE = re.compile(
    r"\b(?:crypto(?:monnaie)?s?|token|jeton|blockchain|altcoin|sol[/_-]?(?:usd|usdt))\b"
)
_NEGATIVE_CHANGE_RE = re.compile(
    r"\b(baisse|baisser|baissera|baissé|perdu|perdre|perte|chute|chuter|recul|moins)\b"
)
_POSITIVE_CHANGE_RE = re.compile(
    r"\b(hausse|monter|montera|gagne|gagner|progresse|progression|plus)\b"
)
_PERCENT_RE = re.compile(
    r"(?P<sign>[+-])?\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?:%(?!\w)|pour\s*cent\b)"
)
_CLAIM_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TRANSCRIPT_TIME_RE = re.compile(r"^\s*(?:\[(?:\d{1,2}:)?\d{1,2}:\d{2}\]|(?:\d{1,2}:)?\d{1,2}:\d{2})\s*")
_PERSON_SPEECH_RE = re.compile(
    r"\b(?:jerome|jay)\s+[a-z][a-z'-]+\b.*\b(?:declare|dit|affirme|said|stated)\b"
)


def normalize_text(text: str) -> str:
    """Return a stable matching representation while preserving the original elsewhere."""

    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    lowered = without_accents.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", lowered).strip()


def extract_claim_texts(text: str, *, max_claims: int = 100) -> list[str]:
    """Conservatively extract checkable statements from a transcript.

    This is intentionally not a generic sentence summariser.  It selects
    market changes expressed as percentages, explicit causal assertions and
    named-index/person statements.  Plain price levels and allocations are
    left to the Lexa plan verifier, so a level said by an analyst is not
    accidentally promoted to a current market fact.
    """

    if max_claims <= 0:
        return []
    output: list[str] = []
    seen: set[str] = set()
    index_aliases = tuple(
        alias
        for definition in DEFAULT_ENTITY_CATALOG
        if definition.entity_type == "INDEX"
        for alias in definition.aliases
    )
    for raw in _CLAIM_BOUNDARY_RE.split(text or ""):
        candidate = _TRANSCRIPT_TIME_RE.sub("", raw).strip(" \t-–—")
        if not candidate:
            continue
        normalized = normalize_text(candidate)
        has_percentage_change = bool(
            _PERCENT_RE.search(normalized)
            and (
                _NEGATIVE_CHANGE_RE.search(normalized)
                or _POSITIVE_CHANGE_RE.search(normalized)
                or _FORECAST_RE.search(normalized)
            )
        )
        named_index = any(_has_alias(normalized, alias) for alias in index_aliases)
        selected = bool(
            has_percentage_change
            or _CAUSAL_RE.search(normalized)
            or (named_index and _PERCENT_RE.search(normalized))
            or _PERSON_SPEECH_RE.search(normalized)
        )
        if not selected or normalized in seen:
            continue
        output.append(candidate)
        seen.add(normalized)
        if len(output) >= max_claims:
            break
    return output


def _has_alias(text: str, alias: str) -> bool:
    normal_alias = normalize_text(alias)
    expression = re.escape(normal_alias).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){expression}(?!\w)", text) is not None


@dataclass(slots=True, frozen=True)
class _Calculation:
    value: float | None
    method: str
    sources: tuple[VerificationSource, ...] = ()
    notes: tuple[str, ...] = ()


class ClaimVerificationEngine:
    """Offline fact checker for structured market and transcript claims."""

    def __init__(
        self,
        *,
        entity_catalog: Sequence[EntityDefinition] = DEFAULT_ENTITY_CATALOG,
        absolute_tolerance_pct: float = 0.75,
        relative_tolerance: float = 0.10,
    ) -> None:
        self.entity_catalog = tuple(entity_catalog)
        self.absolute_tolerance_pct = max(0.0, absolute_tolerance_pct)
        self.relative_tolerance = max(0.0, relative_tolerance)
        self._definitions = {item.canonical_id: item for item in self.entity_catalog}

    def verify(
        self,
        original_text: str,
        *,
        observations: Sequence[PointInTimeValue] = (),
        source_timestamp: datetime | None = None,
        as_of: datetime | None = None,
        claimed_value: float | None = None,
        claimed_unit: str | None = None,
        claimed_period: ClaimPeriod | None = None,
        claimed_cause: str | None = None,
        metric: str | None = None,
        entity_hints: Sequence[ClaimEntity] = (),
        causal_evidence: Sequence[CausalEvidence] = (),
    ) -> Claim:
        """Verify one claim from supplied evidence only.

        ``source_timestamp`` dates the assertion. ``as_of`` may be earlier for
        a historical replay, but can never make observations published after
        that instant visible. No provider, network client, or language model is
        called by this method.
        """

        if not original_text or not original_text.strip():
            raise ValueError("a claim must contain non-empty original text")

        source_time = _as_utc(source_timestamp) if source_timestamp is not None else None
        replay_time = _as_utc(as_of) if as_of is not None else None
        cutoff = min(source_time, replay_time) if source_time and replay_time else (
            replay_time or source_time
        )
        normalized = normalize_text(original_text)
        entities, entity_notes = self._resolve_entities(original_text, normalized)
        entities = self._merge_entity_hints(entities, entity_hints)

        extracted_value, extracted_unit = self._extract_value(normalized)
        value = claimed_value if claimed_value is not None else extracted_value
        unit = claimed_unit if claimed_unit is not None else extracted_unit
        period = claimed_period or self._extract_period(normalized, source_time)
        cause = claimed_cause or self._extract_cause(original_text, normalized)
        claim_type = self._claim_type(normalized, value, entities)

        common: dict[str, Any] = {
            "original_text": original_text,
            "normalized_text": normalized,
            "claim_type": claim_type,
            "entities": entities,
            "claimed_value": value,
            "claimed_unit": unit,
            "claimed_period": period,
            "claimed_cause": cause,
            "source_timestamp": source_time,
        }

        # Modality outranks the presence of a number. A conditional -30% is a
        # scenario, not a false current observation waiting to be contradicted.
        if claim_type is ClaimType.FORECAST:
            return Claim(
                **common,
                comparison_method="deterministic_modal_language_classification",
                verification_status=ClaimVerificationStatus.FORECAST,
                confidence=99.0,
                notes=[
                    "Le conditionnel décrit un scénario futur; il ne peut pas être "
                    "promu en fait observé.",
                ],
            )

        # An opinion remains an opinion even when it mentions an ambiguous
        # entity.  Entity ambiguity must not promote a subjective statement
        # into a fact-checkable assertion.
        if claim_type is ClaimType.OPINION:
            return Claim(
                **common,
                comparison_method="deterministic_opinion_classification",
                verification_status=ClaimVerificationStatus.OPINION,
                confidence=98.0,
                notes=["Le texte exprime une appréciation personnelle, pas un fait mesurable."],
            )

        ambiguity_notes = [*entity_notes]
        unresolved = [item for item in entities if not item.verified]
        explicit_index_ids = {
            item.canonical_id
            for item in entities
            if item.verified and item.entity_type == "INDEX"
        }
        if {"NASDAQ_COMPOSITE", "NASDAQ_100"} <= explicit_index_ids:
            ambiguity_notes.append(
                "Nasdaq Composite et Nasdaq-100 sont deux indices distincts; "
                "le texte ne permet pas de choisir la série revendiquée."
            )
        if unresolved or ambiguity_notes:
            return Claim(
                **common,
                comparison_method="deterministic_entity_resolution",
                verification_status=ClaimVerificationStatus.AMBIGUOUS,
                confidence=97.0,
                notes=ambiguity_notes or [
                    "Au moins une identité n'est pas vérifiée; aucune identité canonique "
                    "n'est affirmée."
                ],
            )

        # A dated statement that explicitly presents a market value as
        # today's/current is not silently reused on a later day.  This narrow
        # rule is limited to market assets and indices (or the word "today"):
        # monthly macro facts must not expire merely because a week elapsed.
        is_outdated = self._is_outdated_current_claim(
            normalized,
            entities=entities,
            source_time=source_time,
            replay_time=replay_time,
        )
        if is_outdated and claim_type is not ClaimType.QUANTITATIVE_CHANGE:
            # Required by the predicate; the explicit assertions also keep
            # static type checkers from widening the Optional values here.
            assert source_time is not None and replay_time is not None
            age = replay_time - source_time
            return Claim(
                **common,
                comparison_method="explicit_current_wording_vs_source_timestamp",
                verification_status=ClaimVerificationStatus.OUTDATED,
                confidence=100.0,
                notes=[
                    "L'affirmation se présente comme actuelle, mais sa date source précède "
                    f"la vérification de {age.total_seconds() / 3600:.1f} h; elle ne peut "
                    "pas servir de valeur de marché courante."
                ],
            )

        if claim_type is ClaimType.CAUSAL:
            return self._verify_causality(common, causal_evidence)

        if claim_type is ClaimType.QUANTITATIVE_CHANGE:
            if cutoff is None:
                return Claim(
                    **common,
                    comparison_method="point_in_time_check_unavailable",
                    verification_status=ClaimVerificationStatus.UNVERIFIABLE,
                    confidence=100.0,
                    notes=[
                        "La date de l'affirmation manque; impossible de déterminer quelles "
                        "observations étaient alors connaissables."
                    ],
                )
            calculation = self._calculate_change(
                observations=observations,
                period=period,
                cutoff=cutoff,
                metric=metric,
                entities=entities,
                unit=unit,
                from_peak=bool(_DRAWDOWN_FROM_PEAK_RE.search(normalized)),
            )
            if is_outdated:
                assert source_time is not None and replay_time is not None
                age = replay_time - source_time
                numeric_notes = list(calculation.notes)
                if calculation.value is not None and value is not None:
                    _, _, comparison_note = self._compare_percentages(
                        value,
                        calculation.value,
                    )
                    numeric_notes.append(comparison_note)
                numeric_notes.append(
                    "L'affirmation se présente comme actuelle, mais sa date source précède "
                    f"la vérification de {age.total_seconds() / 3600:.1f} h; elle ne peut "
                    "pas servir de valeur de marché courante."
                )
                return Claim(
                    **common,
                    verification_sources=list(calculation.sources),
                    calculated_value=(
                        round(calculation.value, 6)
                        if calculation.value is not None
                        else None
                    ),
                    comparison_method="explicit_current_wording_vs_source_timestamp",
                    verification_status=ClaimVerificationStatus.OUTDATED,
                    confidence=100.0,
                    notes=numeric_notes,
                )
            if calculation.value is None or value is None:
                return Claim(
                    **common,
                    verification_sources=list(calculation.sources),
                    calculated_value=calculation.value,
                    comparison_method=calculation.method,
                    verification_status=ClaimVerificationStatus.UNVERIFIABLE,
                    confidence=100.0,
                    notes=list(calculation.notes) or [
                        "La valeur revendiquée ou les données nécessaires au recalcul manquent."
                    ],
                )
            status, confidence, comparison_note = self._compare_percentages(value, calculation.value)
            return Claim(
                **common,
                verification_sources=list(calculation.sources),
                calculated_value=round(calculation.value, 6),
                comparison_method=calculation.method,
                verification_status=status,
                confidence=confidence,
                notes=[*calculation.notes, comparison_note],
            )

        return Claim(
            **common,
            comparison_method="no_deterministic_rule_or_authorized_evidence",
            verification_status=ClaimVerificationStatus.UNVERIFIABLE,
            confidence=100.0,
            notes=["Aucune règle déterministe ni source fournie ne permet de vérifier ce fait."],
        )

    @staticmethod
    def _is_outdated_current_claim(
        normalized: str,
        *,
        entities: Sequence[ClaimEntity],
        source_time: datetime | None,
        replay_time: datetime | None,
    ) -> bool:
        if source_time is None or replay_time is None or replay_time <= source_time:
            return False
        if replay_time.date() <= source_time.date():
            return False
        if _TODAY_RE.search(normalized):
            return True
        time_sensitive_entity = any(
            item.verified and item.entity_type in {"ASSET", "INDEX"} for item in entities
        )
        return bool(time_sensitive_entity and _CURRENT_MARKET_RE.search(normalized))

    def _claim_type(
        self,
        normalized: str,
        value: float | None,
        entities: Sequence[ClaimEntity],
    ) -> ClaimType:
        if _FORECAST_RE.search(normalized):
            return ClaimType.FORECAST
        if _CAUSAL_RE.search(normalized):
            return ClaimType.CAUSAL
        if _OPINION_RE.search(normalized):
            return ClaimType.OPINION
        if value is not None:
            return ClaimType.QUANTITATIVE_CHANGE
        if any(not item.verified for item in entities):
            return ClaimType.ENTITY
        return ClaimType.FACTUAL

    def _resolve_entities(
        self,
        original: str,
        normalized: str,
    ) -> tuple[list[ClaimEntity], list[str]]:
        resolved: list[ClaimEntity] = []
        notes: list[str] = []
        matched_ids: set[str] = set()

        for definition in self.entity_catalog:
            alias = next(
                (
                    candidate
                    for candidate in definition.aliases
                    if _has_alias(normalized, candidate)
                    and not (
                        definition.canonical_id == "SOL"
                        and normalize_text(candidate) == "sol"
                        and not self._has_explicit_sol_context(original, normalized)
                    )
                ),
                None,
            )
            if alias is None:
                continue
            matched_ids.add(definition.canonical_id)
            resolved.append(
                ClaimEntity(
                    mention=alias,
                    entity_type=definition.entity_type,
                    canonical_id=definition.canonical_id,
                    canonical_name=definition.canonical_name,
                    verified=True,
                    confidence=100.0,
                )
            )

        # "Nasdaq" alone is not an index identifier. It may mean the exchange,
        # Composite, Nasdaq-100, or colloquially a technology-heavy market.
        if _has_alias(normalized, "nasdaq") and not (
            {"NASDAQ_COMPOSITE", "NASDAQ_100"} & matched_ids
        ):
            resolved.append(
                ClaimEntity(
                    mention="Nasdaq",
                    entity_type="INDEX",
                    candidates=["Nasdaq Composite", "Nasdaq-100"],
                    verified=False,
                    confidence=100.0,
                )
            )
            notes.append(
                "Le terme « Nasdaq » seul ne distingue pas le Nasdaq Composite du Nasdaq-100."
            )

        uncertain_person = self._fuzzy_person_candidate(normalized, matched_ids)
        if uncertain_person is not None:
            mention, definition, similarity = uncertain_person
            resolved.append(
                ClaimEntity(
                    mention=mention,
                    entity_type="PERSON",
                    candidates=[definition.canonical_name],
                    verified=False,
                    confidence=round(similarity * 100.0, 1),
                )
            )
            notes.append(
                f"Le nom transcrit « {mention} » ressemble à « {definition.canonical_name} » "
                "mais n'est pas une correspondance exacte; l'identité reste non vérifiée."
            )

        return resolved, notes

    @staticmethod
    def _has_explicit_sol_context(original: str, normalized: str) -> bool:
        """Accept the ticker SOL, but never infer it from the French noun ``sol``."""

        explicit_ticker = re.search(r"(?<!\w)(?:\$SOL|SOL)(?!\w)", original) is not None
        return explicit_ticker or _SOL_CRYPTO_CONTEXT_RE.search(normalized) is not None

    @staticmethod
    def _merge_entity_hints(
        detected: Sequence[ClaimEntity],
        hints: Sequence[ClaimEntity],
    ) -> list[ClaimEntity]:
        output = list(detected)
        seen = {(item.mention, item.canonical_id) for item in output}
        for hint in hints:
            key = (hint.mention, hint.canonical_id)
            if key not in seen:
                output.append(hint)
                seen.add(key)
        return output

    def _fuzzy_person_candidate(
        self,
        normalized: str,
        matched_ids: set[str],
    ) -> tuple[str, EntityDefinition, float] | None:
        words = re.findall(r"[a-z][a-z'-]+", normalized)
        best: tuple[str, EntityDefinition, float] | None = None
        for definition in self.entity_catalog:
            if definition.entity_type != "PERSON" or definition.canonical_id in matched_ids:
                continue
            canonical = normalize_text(definition.canonical_name)
            width = len(canonical.split())
            for index in range(0, len(words) - width + 1):
                mention = " ".join(words[index : index + width])
                similarity = SequenceMatcher(None, mention, canonical).ratio()
                # A near match is a candidate, never an automatic correction.
                if 0.87 <= similarity < 1.0 and (best is None or similarity > best[2]):
                    best = (mention, definition, similarity)
        return best

    @staticmethod
    def _extract_value(normalized: str) -> tuple[float | None, str | None]:
        match = _PERCENT_RE.search(normalized)
        if match is None:
            return None, None
        value = float(match.group("value").replace(",", "."))
        if match.group("sign") == "-":
            value = -value
        elif match.group("sign") != "+":
            context = normalized[max(0, match.start() - 80) : match.start()]
            # "10 % sous son sommet" carries the same negative sign as
            # "a perdu 10 % depuis son sommet", even though the direction is
            # stated after the number in the first form.
            drawdown_context = normalized[
                max(0, match.start() - 80) : min(len(normalized), match.end() + 80)
            ]
            if _NEGATIVE_CHANGE_RE.search(context) or _DRAWDOWN_FROM_PEAK_RE.search(
                drawdown_context
            ):
                value = -value
            elif _POSITIVE_CHANGE_RE.search(context):
                value = abs(value)
        return value, "pct"

    @staticmethod
    def _extract_period(
        normalized: str,
        source_timestamp: datetime | None,
    ) -> ClaimPeriod | None:
        month_expression = "|".join(sorted(_MONTHS, key=len, reverse=True))
        match = re.search(rf"\b(?P<month>{month_expression})(?:\s+(?P<year>20\d{{2}}))?\b", normalized)
        month: int | None = None
        year: int | None = None
        if match is not None:
            month = _MONTHS[match.group("month")]
            year_text = match.group("year")
            year = int(year_text) if year_text else (source_timestamp.year if source_timestamp else None)
        elif source_timestamp is not None and re.search(
            r"\b(ce mois|du mois|sur le mois|mensuel|mensuelle|month to date|monthly)\b",
            normalized,
        ):
            month = source_timestamp.month
            year = source_timestamp.year

        if month is None or year is None:
            return None
        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            following_month = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            following_month = datetime(year, month + 1, 1, tzinfo=UTC)
        calendar_end = following_month - timedelta(microseconds=1)
        end = min(calendar_end, source_timestamp) if source_timestamp is not None else calendar_end
        return ClaimPeriod(
            label=f"{year:04d}-{month:02d}",
            start=start,
            end=end,
            frequency="MONTH",
        )

    @staticmethod
    def _extract_cause(original: str, normalized: str) -> str | None:
        match = _CAUSAL_RE.search(normalized)
        if match is None:
            return None
        # Normalisation preserves character count for ordinary Latin text well
        # enough for this display excerpt; fall back to the whole first clause.
        candidate = original[: match.start()].strip(" ,.;:-")
        if candidate:
            return candidate
        return original.split(",", maxsplit=1)[0].strip() or None

    def _calculate_change(
        self,
        *,
        observations: Sequence[PointInTimeValue],
        period: ClaimPeriod | None,
        cutoff: datetime,
        metric: str | None,
        entities: Sequence[ClaimEntity],
        unit: str | None,
        from_peak: bool,
    ) -> _Calculation:
        method = (
            "period_peak_to_latest_drawdown: 100 * (price_current / price_peak - 1)"
            if from_peak
            else "month_to_date_close_to_close: 100 * (price_end / price_start - 1)"
        )
        if unit != "pct":
            return _Calculation(
                value=None,
                method="unsupported_unit",
                notes=(f"L'unité {unit!r} n'a pas de règle de recalcul déterministe.",),
            )
        if period is None or period.frequency != "MONTH" or period.start is None or period.end is None:
            return _Calculation(
                value=None,
                method=method,
                notes=("La période mensuelle n'est pas définie sans ambiguïté.",),
            )

        selected_metric = metric or self._metric_for_entities(entities)
        if selected_metric is None:
            unique_metrics = {item.metric for item in observations}
            if len(unique_metrics) == 1:
                selected_metric = next(iter(unique_metrics))
        if selected_metric is None:
            return _Calculation(
                value=None,
                method=method,
                notes=("La série à utiliser n'est pas identifiée sans ambiguïté.",),
            )

        known = as_of_filter(list(observations), cutoff, allow_revised=False)
        known = [
            item
            for item in known
            if item.metric == selected_metric
            and not (
                item.revision_time is not None
                and item.revision_time > cutoff
                and not item.is_first_print
            )
        ]
        during = [
            item
            for item in known
            if period.start <= item.observation_time <= min(period.end, cutoff)
        ]
        if from_peak:
            if not during:
                return _Calculation(
                    value=None,
                    method=method,
                    notes=(
                        "Il faut des clôtures disponibles dans la période pour identifier "
                        "le pic et la clôture courante sans regard vers le futur.",
                    ),
                )
            peak_value = max(
                during,
                key=lambda item: (item.value, item.observation_time, item.revision_number),
            )
            current_value = max(
                during,
                key=lambda item: (item.observation_time, item.revision_number),
            )
            if (
                not math.isfinite(peak_value.value)
                or not math.isfinite(current_value.value)
                or peak_value.value == 0
            ):
                return _Calculation(
                    value=None,
                    method=method,
                    notes=("Le pic ou la clôture courante est invalide, ou le pic est nul.",),
                )
            calculated = 100.0 * (current_value.value / peak_value.value - 1.0)
            sources = (
                self._source_from_value(peak_value, role="drawdown_peak"),
                self._source_from_value(current_value, role="drawdown_current"),
            )
            notes = (
                f"Pic de période connu: clôture du {peak_value.observation_time.isoformat()} = "
                f"{peak_value.value:g}.",
                "Clôture courante connue à la date de l'affirmation: "
                f"{current_value.observation_time.isoformat()} = {current_value.value:g}.",
            )
            return _Calculation(value=calculated, method=method, sources=sources, notes=notes)

        before = [item for item in known if item.observation_time < period.start]
        if not before or not during:
            return _Calculation(
                value=None,
                method=method,
                notes=(
                    "Il faut une clôture antérieure au début de période et une clôture "
                    "disponible dans la période, toutes deux connues à la date de vérification.",
                ),
            )

        start_value = max(
            before,
            key=lambda item: (item.observation_time, item.revision_number),
        )
        end_value = max(
            during,
            key=lambda item: (item.observation_time, item.revision_number),
        )
        if (
            not math.isfinite(start_value.value)
            or not math.isfinite(end_value.value)
            or start_value.value == 0
        ):
            return _Calculation(
                value=None,
                method=method,
                notes=("Les clôtures nécessaires sont invalides ou la base est nulle.",),
            )

        calculated = 100.0 * (end_value.value / start_value.value - 1.0)
        sources = (
            self._source_from_value(start_value, role="period_start_reference"),
            self._source_from_value(end_value, role="period_end_latest_available"),
        )
        notes = (
            f"Référence: clôture du {start_value.observation_time.isoformat()} = "
            f"{start_value.value:g}.",
            f"Dernière clôture disponible: {end_value.observation_time.isoformat()} = "
            f"{end_value.value:g}.",
        )
        return _Calculation(value=calculated, method=method, sources=sources, notes=notes)

    def _metric_for_entities(self, entities: Sequence[ClaimEntity]) -> str | None:
        canonical_ids = {
            item.canonical_id for item in entities if item.verified and item.canonical_id is not None
        }
        metrics = {
            self._definitions[identifier].metrics[0]
            for identifier in canonical_ids
            if identifier in self._definitions and self._definitions[identifier].metrics
        }
        return next(iter(metrics)) if len(metrics) == 1 else None

    @staticmethod
    def _source_from_value(value: PointInTimeValue, *, role: str) -> VerificationSource:
        source_url = value.meta.get("source_url")
        return VerificationSource(
            source=value.source,
            metric=value.metric,
            role=role,
            value=value.value,
            unit=str(value.meta.get("unit") or "") or None,
            observation_time=value.observation_time,
            release_time=value.release_time,
            availability=value.availability,
            revision_number=value.revision_number,
            source_url=str(source_url) if source_url else None,
        )

    def _compare_percentages(
        self,
        claimed: float,
        calculated: float,
    ) -> tuple[ClaimVerificationStatus, float, str]:
        tolerance = max(self.absolute_tolerance_pct, abs(claimed) * self.relative_tolerance)
        difference = abs(claimed - calculated)
        claimed_sign = 0 if abs(claimed) < 1e-12 else (1 if claimed > 0 else -1)
        calculated_sign = 0 if abs(calculated) < 1e-12 else (1 if calculated > 0 else -1)

        if claimed_sign != calculated_sign and claimed_sign != 0:
            status = ClaimVerificationStatus.CONTRADICTED
            confidence = 99.0
            reason = "les directions revendiquée et calculée sont opposées"
        elif difference <= tolerance:
            status = ClaimVerificationStatus.CONFIRMED
            confidence = 98.0
            reason = f"l'écart est dans la tolérance de {tolerance:.2f} point(s)"
        elif claimed_sign == calculated_sign and claimed_sign != 0:
            status = ClaimVerificationStatus.PARTIALLY_CONFIRMED
            confidence = 95.0
            reason = "la direction concorde mais pas l'amplitude"
        else:
            status = ClaimVerificationStatus.CONTRADICTED
            confidence = 98.0
            reason = "l'écart dépasse la tolérance déterministe"

        note = (
            f"Valeur revendiquée: {claimed:+.4f} %; valeur calculée: "
            f"{calculated:+.4f} %; {reason}."
        )
        return status, confidence, note

    @staticmethod
    def _verify_causality(
        common: dict[str, Any],
        evidence: Sequence[CausalEvidence],
    ) -> Claim:
        supporting = [item for item in evidence if item.supports_direct_causality]
        sources = [
            VerificationSource(
                source=item.source,
                metric="causal_evidence",
                role=item.method,
                source_url=item.source_url,
            )
            for item in evidence
        ]
        if supporting:
            confidence = min(item.confidence for item in supporting)
            return Claim(
                **common,
                verification_sources=sources,
                comparison_method="explicit_causal_evidence_review",
                verification_status=ClaimVerificationStatus.CONFIRMED,
                confidence=confidence,
                notes=[
                    "La causalité directe est étayée par une méthode explicitement fournie; "
                    "le moteur n'a pas déduit ce lien de la seule chronologie."
                ],
            )
        return Claim(
            **common,
            verification_sources=sources,
            comparison_method="direct_causality_requires_explicit_evidence",
            verification_status=ClaimVerificationStatus.UNVERIFIABLE,
            confidence=99.0,
            notes=[
                "La causalité directe alléguée n'est pas démontrée. Une proximité "
                "temporelle ou une corrélation ne suffit pas à établir que l'événement "
                "politique a causé le mouvement de marché."
            ],
        )


__all__ = [
    "DEFAULT_ENTITY_CATALOG",
    "CausalEvidence",
    "Claim",
    "ClaimEntity",
    "ClaimPeriod",
    "ClaimType",
    "ClaimVerificationEngine",
    "ClaimVerificationStatus",
    "EntityDefinition",
    "VerificationSource",
    "VerifiedClaim",
    "extract_claim_texts",
    "normalize_text",
]
