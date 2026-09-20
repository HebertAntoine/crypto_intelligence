"""Check that every published interpretation agrees with its own evidence.

Each rule below encodes one way the system could tell a reader something its
data does not support. They are deliberately mechanical: a rule either finds a
contradiction in the payload or it does not, so the resulting score measures
internal coherence and nothing else. It says nothing about whether the market
will move as described.

The report is the stopping condition for the interpretation work: every
dimension must reach 100 %, and a dimension with no applicable factor scores
100 % by vacuity rather than by assertion — which the report states explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Words that assert a direction. An UNKNOWN factor may not use them.
_DIRECTIONAL_CLAIMS = (
    "va monter",
    "va baisser",
    "haussier",
    "baissier",
    "soutien à la hausse",
    "pression à la baisse",
)

#: Vocabulary that belongs to one family only. Seeing it in another means a
#: template was reused across families.
_FAMILY_VOCABULARY = {
    "flows": ("plateformes d'échange", "plateformes d’échange", "transfert", "baleine"),
    "whales": ("etf au comptant", "entrées nettes sur les etf"),
    "technical": ("etf", "funding", "baleine"),
    "funding": ("bollinger", "etf"),
    "volatility": ("etf", "baleine", "funding"),
}

_POSITIVE_WORDS = ("entrées nettes", "soutien", "apportent du soutien")
_NEGATIVE_WORDS = ("sorties nettes", "pression vendeuse", "abandonnent")


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    dimension: str
    factor_key: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "factor_key": self.factor_key,
            "detail": self.detail,
        }


@dataclass(slots=True)
class InterpretationQualityReport:
    checks: dict[str, int] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    DIMENSIONS = (
        "semantic_consistency",
        "source_integrity",
        "freshness_consistency",
        "direction_consistency",
        "impact_consistency",
        "decision_consistency",
        "text_consistency",
        "horizon_consistency",
    )

    def record(self, dimension: str, *, failed: bool, issue: ValidationIssue | None = None) -> None:
        self.checks[dimension] = self.checks.get(dimension, 0) + 1
        if failed:
            self.failures[dimension] = self.failures.get(dimension, 0) + 1
            if issue is not None:
                self.issues.append(issue)

    def score(self, dimension: str) -> float:
        total = self.checks.get(dimension, 0)
        if total == 0:
            return 100.0
        return round(100.0 * (total - self.failures.get(dimension, 0)) / total, 1)

    @property
    def passed(self) -> bool:
        return all(self.score(name) == 100.0 for name in self.DIMENSIONS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scores": {name: self.score(name) for name in self.DIMENSIONS},
            "checks": {name: self.checks.get(name, 0) for name in self.DIMENSIONS},
            "vacuous": [
                name for name in self.DIMENSIONS if self.checks.get(name, 0) == 0
            ],
            "passed": self.passed,
            "issue_count": len(self.issues),
            "issues": [item.to_dict() for item in self.issues],
        }


class InterpretationConsistencyValidator:
    """Validate one decision payload, factor by factor."""

    def validate(self, payload: dict[str, Any]) -> InterpretationQualityReport:
        report = InterpretationQualityReport()
        families = payload.get("families") or {}
        factors = families.get("factors") or []
        decision = str(payload.get("decision") or "")

        for factor in factors:
            self._validate_factor(factor, report)

        self._validate_decision(payload, factors, decision, report)
        self._validate_families(families, report)
        return report

    # -- per factor ---------------------------------------------------------

    def _validate_factor(self, factor: dict[str, Any], report: InterpretationQualityReport) -> None:
        key = str(factor.get("key") or "?")
        direction = str(factor.get("direction") or "")
        impact = str(factor.get("impact") or "")
        availability = str(factor.get("availability") or "")
        confidence_band = str(factor.get("confidence_band") or "")
        text = " ".join(
            [
                str(factor.get("rationale") or ""),
                *[str(item) for item in factor.get("causal_chain") or []],
            ]
        ).lower()

        # Direction must be one of the four, and UNKNOWN must not be used as a
        # synonym for a measured balance.
        report.record(
            "direction_consistency",
            failed=direction not in {"POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN"},
            issue=ValidationIssue(
                "direction_consistency", key, f"direction « {direction} » hors contrat"
            ),
        )

        # An amplitude-only instrument may never carry a direction.
        if factor.get("impact_on_direction") == "NONE":
            report.record(
                "direction_consistency",
                failed=direction in {"POSITIVE", "NEGATIVE"},
                issue=ValidationIssue(
                    "direction_consistency",
                    key,
                    "lecture d'amplitude porteuse d'une direction",
                ),
            )

        # Missing data is never neutral, and never carries a direction.
        if availability in {"UNAVAILABLE", "NOT_APPLICABLE"}:
            report.record(
                "semantic_consistency",
                failed=direction in {"POSITIVE", "NEGATIVE", "NEUTRAL"},
                issue=ValidationIssue(
                    "semantic_consistency",
                    key,
                    f"donnée {availability} présentée comme « {direction} »",
                ),
            )
            report.record(
                "semantic_consistency",
                failed=not factor.get("missing_requirements"),
                issue=ValidationIssue(
                    "semantic_consistency", key, "absence non explicitée"
                ),
            )

        if availability == "PARTIAL":
            report.record(
                "semantic_consistency",
                failed=not factor.get("missing_requirements"),
                issue=ValidationIssue(
                    "semantic_consistency", key, "lecture partielle sans manque déclaré"
                ),
            )

        # Stale evidence can never be high confidence.
        report.record(
            "freshness_consistency",
            failed=availability == "STALE" and confidence_band == "HIGH",
            issue=ValidationIssue(
                "freshness_consistency", key, "donnée périmée avec confiance élevée"
            ),
        )

        # Impact must be one of the four and must not be inferred from direction.
        report.record(
            "impact_consistency",
            failed=impact not in {"LOW", "MODERATE", "HIGH", "VERY_HIGH"},
            issue=ValidationIssue("impact_consistency", key, f"impact « {impact} » hors contrat"),
        )
        if availability in {"UNAVAILABLE", "NOT_APPLICABLE"}:
            report.record(
                "impact_consistency",
                failed=impact in {"HIGH", "VERY_HIGH"},
                issue=ValidationIssue(
                    "impact_consistency", key, "impact élevé sur une donnée absente"
                ),
            )

        # A direction-free reading must not assert a direction in its text.
        if direction == "UNKNOWN":
            claim = next((word for word in _DIRECTIONAL_CLAIMS if word in text), None)
            report.record(
                "text_consistency",
                failed=claim is not None,
                issue=ValidationIssue(
                    "text_consistency", key, f"direction inconnue affirmant « {claim} »"
                ),
            )

        # A positive reading must not be explained in entirely negative terms.
        if direction == "POSITIVE":
            report.record(
                "text_consistency",
                failed=any(word in text for word in _NEGATIVE_WORDS)
                and not any(word in text for word in _POSITIVE_WORDS),
                issue=ValidationIssue(
                    "text_consistency", key, "statut positif expliqué en termes négatifs"
                ),
            )
        if direction == "NEGATIVE":
            report.record(
                "text_consistency",
                failed="apportent du soutien" in text and "réduisent" not in text,
                issue=ValidationIssue(
                    "text_consistency", key, "statut négatif annonçant un soutien"
                ),
            )

        # No family may borrow another family's vocabulary.
        forbidden = _FAMILY_VOCABULARY.get(key, ())
        borrowed = next((word for word in forbidden if word in text), None)
        report.record(
            "text_consistency",
            failed=borrowed is not None,
            issue=ValidationIssue(
                "text_consistency", key, f"vocabulaire d'une autre famille: « {borrowed} »"
            ),
        )

        # Every available factor must carry a traceable chain and a real source.
        if availability in {"AVAILABLE", "PARTIAL", "STALE"}:
            report.record(
                "semantic_consistency",
                failed=len(factor.get("causal_chain") or []) < 2,
                issue=ValidationIssue(
                    "semantic_consistency", key, "chaîne causale absente ou trop courte"
                ),
            )
            report.record(
                "source_integrity",
                failed=not str(factor.get("provider") or "").strip(),
                issue=ValidationIssue(
                    "source_integrity", key, "fournisseur réel non renseigné"
                ),
            )

    # -- decision level -----------------------------------------------------

    def _validate_decision(
        self,
        payload: dict[str, Any],
        factors: list[dict[str, Any]],
        decision: str,
        report: InterpretationQualityReport,
    ) -> None:
        # A decision must be traceable: either a factor or a gated event.
        gate_active = bool((payload.get("event_risk_gate") or {}).get("active"))
        report.record(
            "decision_consistency",
            failed=decision in {"BUY", "SELL", "WAIT"} and not factors and not gate_active,
            issue=ValidationIssue(
                "decision_consistency", "-", "décision sans facteur ni événement traçable"
            ),
        )

        # A directional decision must have at least one factor supporting it.
        if decision in {"BUY", "SELL"}:
            wanted = "POSITIVE" if decision == "BUY" else "NEGATIVE"
            report.record(
                "decision_consistency",
                failed=not any(item.get("direction") == wanted for item in factors),
                issue=ValidationIssue(
                    "decision_consistency", "-", f"{decision} sans aucun facteur {wanted}"
                ),
            )

        # Change conditions must be concrete, not filler.
        for bucket in ("conditions_to_buy", "conditions_to_sell"):
            for line in payload.get(bucket) or []:
                report.record(
                    "decision_consistency",
                    failed="catalyseur prioritaire" in line.lower()
                    or "rétablir les familles" in line.lower(),
                    issue=ValidationIssue(
                        "decision_consistency", bucket, f"condition générique: {line[:60]}"
                    ),
                )

        # Market expectations: an unavailable one must not show a probability.
        for item in payload.get("market_expectations") or []:
            if (item or {}).get("status") != "AVAILABLE":
                report.record(
                    "source_integrity",
                    failed=item.get("market_probability") is not None,
                    issue=ValidationIssue(
                        "source_integrity",
                        "market_expectation",
                        "probabilité affichée sur une anticipation indisponible",
                    ),
                )

        # The horizon must be the one that was asked for.
        report.record(
            "horizon_consistency",
            failed=not payload.get("horizon"),
            issue=ValidationIssue("horizon_consistency", "-", "horizon absent du payload"),
        )

    # -- families -----------------------------------------------------------

    def _validate_families(
        self, families: dict[str, Any], report: InterpretationQualityReport
    ) -> None:
        items = families.get("items") or {}
        report.record(
            "semantic_consistency",
            failed=len(items) != 5,
            issue=ValidationIssue(
                "semantic_consistency", "families", f"{len(items)} familles au lieu de 5"
            ),
        )
        for name, family in items.items():
            if family.get("available"):
                continue
            # A missing family must say so, never be silently hidden.
            report.record(
                "semantic_consistency",
                failed=not str(family.get("unavailable_reason") or "").strip(),
                issue=ValidationIssue(
                    "semantic_consistency", name, "famille indisponible sans raison"
                ),
            )
            report.record(
                "direction_consistency",
                failed=family.get("directional_bias") is not None,
                issue=ValidationIssue(
                    "direction_consistency", name, "famille indisponible portant une direction"
                ),
            )


def horizons_are_independent(payloads: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    """Three horizons must not publish byte-identical interpretations.

    Copying one reading across 24 h, 7 d and 30 d would satisfy every per-factor
    rule while telling the reader the same thing three times.

    The signature covers what is actually published: the decision summary
    (verdict, entry quality, risk, reasons) when the six-family analysis is
    present, plus the factor list. Reading the factor list alone made the
    invariant depend on which secondary indicator happened to differentiate the
    horizons that day - a market-driven coincidence, not a guarantee.
    """

    signatures: dict[str, str] = {}
    for horizon, payload in payloads.items():
        factors = (payload.get("families") or {}).get("factors") or []
        summary = ((payload.get("analysis") or {}).get("summary") or {})
        published = "|".join([
            str(summary.get("sentence", "")),
            str((summary.get("entry_quality") or {}).get("label", "")),
            str((summary.get("risk") or {}).get("label", "")),
            ",".join(str(reason.get("title")) for reason in summary.get("reasons") or []),
        ])
        signatures[horizon] = published + "||" + "|".join(
            f"{item.get('key')}:{item.get('direction')}:{item.get('impact')}:"
            f"{item.get('rationale')}"
            for item in factors
        )
    distinct = len(set(signatures.values()))
    if distinct <= 1 and len(signatures) > 1:
        return False, "les horizons publient une interprétation identique"
    return True, f"{distinct} interprétation(s) distincte(s) sur {len(signatures)} horizons"
