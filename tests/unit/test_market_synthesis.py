"""Sections 20, 22, 53, 54 and 55: risk is not correction, and doubt is stated.

The distinction these tests defend is the one the mission puts first: a market
can look frightening on every risk measure and still not be correcting. Only the
confirmation conditions promote elevated risk into a confirmed correction.
"""

from crypto_intel.engines.factor_semantics import (
    Availability,
    FactorAssessment,
    FactorDirection,
    FactorImpact,
)
from crypto_intel.engines.market_synthesis import (
    Likelihood,
    MarketState,
    MarketSynthesisEngine,
    Uncertainty,
)


def factor(
    key: str,
    direction: FactorDirection,
    impact: FactorImpact = FactorImpact.MODERATE,
    *,
    label: str | None = None,
    availability: Availability = Availability.AVAILABLE,
) -> FactorAssessment:
    return FactorAssessment(
        key=key,
        label=label or key.capitalize(),
        direction=direction,
        impact=impact,
        confidence=0.8,
        availability=availability,
        freshness="FRESH",
        provider="test",
        rationale=f"lecture {key}",
        causal_chain=[f"{key} mesuré.", "observation", "mécanisme"],
    )


def synth(factors, **kwargs):
    return MarketSynthesisEngine().synthesize(factors, **kwargs)


# --- section 53: multi-signal, not yet confirmed ----------------------------


def test_negative_macro_with_calm_credit_is_elevated_risk_not_correction() -> None:
    """The exact case in the brief: risk everywhere, confirmation missing."""

    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("flows", FactorDirection.POSITIVE, label="Flux"),
            factor("credit", FactorDirection.POSITIVE, FactorImpact.MODERATE, label="Crédit"),
        ]
    )
    assert result.state is MarketState.ELEVATED_RISK
    assert result.state is not MarketState.CORRECTION_CONFIRMED
    assert "non confirmée" in result.headline


def test_the_counter_evidence_section_is_never_silently_empty() -> None:
    """Section 20 exists to fight confirmation bias; it must carry content."""

    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("flows", FactorDirection.POSITIVE, label="Flux"),
            factor("credit", FactorDirection.POSITIVE, label="Crédit"),
        ]
    )
    assert result.counter_evidence
    labels = {item["label"] for item in result.counter_evidence}
    assert "Crédit" in labels
    for item in result.counter_evidence:
        assert item["direction"] == "POSITIVE"


# --- section 54: confirmation -----------------------------------------------


def test_every_family_deteriorating_confirms_the_correction() -> None:
    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("technical", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Technique"),
            factor("flows", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Flux"),
            factor("credit", FactorDirection.NEGATIVE, FactorImpact.VERY_HIGH, label="Crédit"),
            factor("positioning", FactorDirection.NEGATIVE, label="Positionnement"),
        ]
    )
    assert result.state is MarketState.CORRECTION_CONFIRMED
    met, total = result.confirmation_met
    assert met == total


def test_confirmation_counts_weight_not_a_naive_vote() -> None:
    """Four minor conditions must not outweigh the ones that matter."""

    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("credit", FactorDirection.POSITIVE, FactorImpact.MODERATE, label="Crédit"),
            factor("flows", FactorDirection.POSITIVE, FactorImpact.HIGH, label="Flux"),
        ]
    )
    weights = {item.text: item.weight for item in result.confirmation_conditions}
    assert weights["Les écarts de crédit se tendent nettement"] == 3
    assert weights["L'énergie continue de progresser"] == 1
    assert result.state is not MarketState.CORRECTION_CONFIRMED


# --- section 55: insufficient data ------------------------------------------


def test_too_few_usable_families_produce_insufficient_data() -> None:
    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, label="Taux"),
            factor(
                "credit",
                FactorDirection.UNKNOWN,
                label="Crédit",
                availability=Availability.UNAVAILABLE,
            ),
            factor(
                "flows",
                FactorDirection.UNKNOWN,
                label="Flux",
                availability=Availability.UNAVAILABLE,
            ),
        ]
    )
    assert result.state is MarketState.INSUFFICIENT_DATA
    assert result.uncertainty is Uncertainty.VERY_HIGH
    assert set(result.missing_families) == {"Crédit", "Flux"}


def test_insufficient_data_never_produces_a_strong_claim() -> None:
    result = synth([factor("rates", FactorDirection.NEGATIVE, label="Taux")])
    assert result.state is MarketState.INSUFFICIENT_DATA
    assert result.main_scenario is None
    assert "Aucune affirmation forte" in result.summary


# --- sections 22 and 28: risk, trigger, confirmation; no invented odds -------


def test_risk_and_confirmation_are_separate_axes() -> None:
    """Same negative weight, different confirmation, different state."""

    risky = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("credit", FactorDirection.POSITIVE, label="Crédit"),
            factor("flows", FactorDirection.POSITIVE, label="Flux"),
        ]
    )
    confirmed = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("credit", FactorDirection.NEGATIVE, FactorImpact.VERY_HIGH, label="Crédit"),
            factor("flows", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Flux"),
        ]
    )
    assert risky.state is MarketState.ELEVATED_RISK
    assert confirmed.state is MarketState.CORRECTION_CONFIRMED


def test_no_invented_probability_is_ever_published() -> None:
    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("credit", FactorDirection.POSITIVE, label="Crédit"),
        ]
    )
    payload = result.to_dict()
    for scenario in (payload["main_scenario"], payload["alternative_scenario"]):
        assert scenario["likelihood"] in {item.value for item in Likelihood}
        assert "%" not in scenario["likelihood"]
        assert scenario["likelihood_basis"] == "HEURISTIC_ASSESSMENT"


def test_both_scenarios_are_always_published_together() -> None:
    """A main scenario without an alternative is an unfalsifiable claim."""

    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("credit", FactorDirection.POSITIVE, label="Crédit"),
        ]
    )
    assert result.main_scenario is not None
    assert result.alternative_scenario is not None


def test_invalidation_conditions_exist_for_every_reading() -> None:
    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, label="Énergie"),
            factor("flows", FactorDirection.POSITIVE, label="Flux"),
            factor("credit", FactorDirection.POSITIVE, label="Crédit"),
        ]
    )
    texts = {item.text for item in result.invalidation_conditions}
    assert "Les rendements se détendent" in texts
    assert "Le crédit reste calme" in texts
    # A condition already satisfied is marked as such rather than hidden.
    assert any(item.met for item in result.invalidation_conditions)


def test_contradictory_families_raise_the_declared_uncertainty() -> None:
    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, label="Énergie"),
            factor("flows", FactorDirection.POSITIVE, FactorImpact.HIGH, label="Flux"),
            factor("credit", FactorDirection.POSITIVE, label="Crédit"),
        ]
    )
    assert result.uncertainty is Uncertainty.HIGH


def test_the_state_label_is_french_and_carries_its_marker() -> None:
    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("credit", FactorDirection.POSITIVE, label="Crédit"),
        ]
    )
    assert result.to_dict()["state_label"] == "🟠 RISQUE ÉLEVÉ"


def test_the_synthesis_needs_no_language_model() -> None:
    """Section 47: the verdict must survive the model being unreachable."""

    import inspect

    from crypto_intel.engines import market_synthesis

    source = inspect.getsource(market_synthesis)
    for token in ("llm", "openai", "anthropic", "completion"):
        assert token not in source.lower()


def test_an_empty_counter_evidence_section_says_so_explicitly() -> None:
    """A blank block reads as "not checked", which is the opposite of the point."""

    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("positioning", FactorDirection.NEGATIVE, label="Positionnement"),
        ]
    )
    assert result.counter_evidence
    assert result.counter_evidence[0]["label"] == "Aucune contre-preuve mesurée"


def test_a_missing_family_marks_the_analysis_partial_not_neutral() -> None:
    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, label="Énergie"),
            factor("technical", FactorDirection.NEGATIVE, label="Technique"),
            factor("flows", FactorDirection.POSITIVE, label="Flux"),
            factor(
                "credit",
                FactorDirection.UNKNOWN,
                label="Crédit",
                availability=Availability.UNAVAILABLE,
            ),
        ]
    )
    assert result.data_status == "PARTIAL_DATA"
    assert result.missing_families == ["Crédit"]
    assert result.state is not MarketState.INSUFFICIENT_DATA


def test_the_summary_never_embeds_a_raw_official_event_title() -> None:
    """Official names are English; the summary is what the reader sees first."""

    result = synth(
        [
            factor("rates", FactorDirection.NEGATIVE, FactorImpact.HIGH, label="Taux"),
            factor("energy", FactorDirection.NEGATIVE, label="Énergie"),
            factor("technical", FactorDirection.POSITIVE, label="Technique"),
        ],
        next_events=[
            {"title": "FOMC monetary policy decision (September 2026)"},
            {"title": "19-Year Bond Treasury auction"},
        ],
    )
    assert "FOMC" not in result.summary
    assert "Treasury" not in result.summary
    assert "catalyseur(s) majeur(s)" in result.summary
