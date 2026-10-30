from datetime import UTC, datetime

from crypto_intel.core.pointintime import Availability, PointInTimeValue
from crypto_intel.engines.claim_verification import (
    ClaimType,
    ClaimVerificationEngine,
    ClaimVerificationStatus,
    extract_claim_texts,
)

# After the US cash close: the 26 October close is knowable, while the next
# session remains future information and must be excluded.
NOW = datetime(2026, 10, 26, 22, tzinfo=UTC)
NASDAQ_COMPOSITE = "market.nasdaq_composite.close"


def _close(day: int, value: float, *, release_day: int | None = None) -> PointInTimeValue:
    observed = datetime(2026, 10 if day > 0 else 9, day if day > 0 else 30, 21, tzinfo=UTC)
    release = datetime(
        2026,
        10 if (release_day or day) > 0 else 9,
        (release_day or day) if (release_day or day) > 0 else 30,
        21,
        1,
        tzinfo=UTC,
    )
    return PointInTimeValue(
        metric=NASDAQ_COMPOSITE,
        value=value,
        observation_time=observed,
        release_time=release,
        availability=Availability.POINT_IN_TIME,
        source="official_market_feed",
        meta={"unit": "index_points", "source_url": "https://example.test/nasdaq"},
    )


def test_false_monthly_drop_is_contradicted_by_point_in_time_closes() -> None:
    observations = [
        _close(-1, 20_000.0),
        _close(10, 20_400.0),
        _close(26, 21_000.0),
        # A dramatic future close must not leak into a check dated 26 October.
        _close(27, 10_000.0),
    ]

    result = ClaimVerificationEngine().verify(
        "Le Nasdaq Composite a perdu environ 10 % au cours du mois d'octobre 2026.",
        observations=observations,
        source_timestamp=NOW,
        metric=NASDAQ_COMPOSITE,
    )

    assert result.verification_status is ClaimVerificationStatus.CONTRADICTED
    assert result.claim_type is ClaimType.QUANTITATIVE_CHANGE
    assert result.claimed_value == -10.0
    assert result.claimed_unit == "pct"
    assert result.claimed_period is not None
    assert result.claimed_period.label == "2026-10"
    assert result.calculated_value == 5.0
    assert len(result.verification_sources) == 2
    assert result.verification_sources[-1].observation_time.day == 26
    assert "100 * (price_end / price_start - 1)" in result.comparison_method
    assert result.original_text.startswith("Le Nasdaq Composite")
    assert result.normalized_text.startswith("le nasdaq composite")


def test_a_later_replay_time_cannot_leak_data_published_after_the_claim() -> None:
    observations = [
        _close(-1, 20_000.0),
        _close(26, 21_000.0),
        _close(27, 10_000.0),
    ]

    result = ClaimVerificationEngine().verify(
        "Le Nasdaq Composite a gagné 5 % au cours du mois d'octobre 2026.",
        observations=observations,
        source_timestamp=NOW,
        as_of=datetime(2026, 10, 30, 22, tzinfo=UTC),
        metric=NASDAQ_COMPOSITE,
    )

    assert result.verification_status is ClaimVerificationStatus.CONFIRMED
    assert result.calculated_value == 5.0
    assert result.verification_sources[-1].observation_time.day == 26


def test_bare_nasdaq_is_ambiguous_between_composite_and_nasdaq_100() -> None:
    result = ClaimVerificationEngine().verify(
        "Le Nasdaq a perdu 4 % ce mois.",
        source_timestamp=NOW,
    )

    assert result.verification_status is ClaimVerificationStatus.AMBIGUOUS
    assert result.calculated_value is None
    assert result.entities[0].canonical_id is None
    assert result.entities[0].verified is False
    assert result.entities[0].candidates == ["Nasdaq Composite", "Nasdaq-100"]
    assert any("deux" in note.lower() or "distingue" in note.lower() for note in result.notes)


def test_conditional_thirty_percent_drop_stays_a_forecast() -> None:
    result = ClaimVerificationEngine().verify(
        "Si le support casse, le Bitcoin pourrait chuter de 30 %.",
        source_timestamp=NOW,
    )

    assert result.verification_status is ClaimVerificationStatus.FORECAST
    assert result.claim_type is ClaimType.FORECAST
    assert result.claimed_value == -30.0
    assert result.claimed_unit == "pct"
    assert result.calculated_value is None
    assert result.entities[0].canonical_id == "BTC"


def test_direct_political_causality_without_evidence_is_flagged() -> None:
    result = ClaimVerificationEngine().verify(
        "L'annonce du président a directement provoqué le krach boursier.",
        source_timestamp=NOW,
    )

    assert result.verification_status is ClaimVerificationStatus.UNVERIFIABLE
    assert result.claim_type is ClaimType.CAUSAL
    assert result.claimed_cause == "L'annonce du président"
    assert result.comparison_method == "direct_causality_requires_explicit_evidence"
    assert any("causalité directe" in note.lower() for note in result.notes)
    assert any("politique" in note.lower() for note in result.notes)


def test_uncertain_transcribed_name_is_not_promoted_to_an_identity() -> None:
    result = ClaimVerificationEngine().verify(
        "Jérome Powel a déclaré que les taux resteraient élevés.",
        source_timestamp=NOW,
    )

    assert result.verification_status is ClaimVerificationStatus.AMBIGUOUS
    assert result.claim_type is ClaimType.ENTITY
    person = next(entity for entity in result.entities if entity.entity_type == "PERSON")
    assert person.canonical_id is None
    assert person.canonical_name is None
    assert person.verified is False
    assert person.candidates == ["Jerome Powell"]
    assert any("identité reste non vérifiée" in note for note in result.notes)


def test_explicit_today_market_claim_is_outdated_on_a_later_day() -> None:
    result = ClaimVerificationEngine().verify(
        "Le Bitcoin gagne 5 % aujourd'hui.",
        source_timestamp=datetime(2026, 10, 20, 20, tzinfo=UTC),
        as_of=NOW,
    )

    assert result.verification_status is ClaimVerificationStatus.OUTDATED
    assert result.calculated_value is None
    assert result.comparison_method == "explicit_current_wording_vs_source_timestamp"


def test_historical_month_claim_is_not_expired_only_because_replayed_later() -> None:
    observations = [_close(-1, 20_000.0), _close(26, 21_000.0)]

    result = ClaimVerificationEngine().verify(
        "Le Nasdaq Composite a gagné 5 % au cours du mois d'octobre 2026.",
        observations=observations,
        source_timestamp=NOW,
        as_of=datetime(2026, 11, 30, 22, tzinfo=UTC),
        metric=NASDAQ_COMPOSITE,
    )

    assert result.verification_status is ClaimVerificationStatus.CONFIRMED


def test_drawdown_wording_uses_the_period_peak_not_the_month_open() -> None:
    observations = [
        _close(-1, 20_000.0),
        _close(10, 22_000.0),
        _close(26, 19_800.0),
    ]

    result = ClaimVerificationEngine().verify(
        "Le Nasdaq Composite est 10 % sous son sommet en octobre 2026.",
        observations=observations,
        source_timestamp=NOW,
        metric=NASDAQ_COMPOSITE,
    )

    assert result.claimed_value == -10.0
    assert result.calculated_value == -10.0
    assert result.verification_status is ClaimVerificationStatus.CONFIRMED
    assert result.comparison_method.startswith("period_peak_to_latest_drawdown")
    assert [source.role for source in result.verification_sources] == [
        "drawdown_peak",
        "drawdown_current",
    ]


def test_old_today_change_is_calculated_then_explicitly_marked_outdated() -> None:
    source_time = datetime(2026, 10, 20, 22, tzinfo=UTC)
    observations = [_close(-1, 20_000.0), _close(20, 21_000.0)]

    result = ClaimVerificationEngine().verify(
        "Le Nasdaq Composite gagne 5 % ce mois aujourd'hui.",
        observations=observations,
        source_timestamp=source_time,
        as_of=NOW,
        metric=NASDAQ_COMPOSITE,
    )

    assert result.calculated_value == 5.0
    assert result.verification_status is ClaimVerificationStatus.OUTDATED
    assert len(result.verification_sources) == 2
    assert any("dans la tolérance" in note for note in result.notes)


def test_opinion_is_not_promoted_to_ambiguity() -> None:
    result = ClaimVerificationEngine().verify(
        "À mon avis, le Nasdaq est trop cher.",
        source_timestamp=NOW,
    )

    assert result.claim_type is ClaimType.OPINION
    assert result.verification_status is ClaimVerificationStatus.OPINION


def test_french_noun_sol_is_not_resolved_as_solana_without_crypto_context() -> None:
    result = ClaimVerificationEngine().verify(
        "Le sol a perdu 5 % de sa valeur ce mois.",
        source_timestamp=NOW,
    )

    assert all(entity.canonical_id != "SOL" for entity in result.entities)
    assert result.verification_status is ClaimVerificationStatus.UNVERIFIABLE


def test_explicit_uppercase_sol_ticker_is_resolved_as_solana() -> None:
    result = ClaimVerificationEngine().verify(
        "SOL a perdu 5 % ce mois.",
        source_timestamp=NOW,
    )

    assert any(entity.canonical_id == "SOL" for entity in result.entities)


def test_claim_status_contract_contains_every_required_status() -> None:
    assert {item.value for item in ClaimVerificationStatus} == {
        "CONFIRMED",
        "PARTIALLY_CONFIRMED",
        "CONTRADICTED",
        "UNVERIFIABLE",
        "AMBIGUOUS",
        "OUTDATED",
        "OPINION",
        "FORECAST",
    }


def test_transcript_claim_extraction_excludes_price_levels_and_allocations() -> None:
    transcript = """
    [00:10] Le Nasdaq a perdu 10 % ce mois-ci.
    [00:20] Si le support casse, Bitcoin pourrait chuter de 30 %.
    [00:30] Je place 40 % du budget sur la zone à 62 000 dollars.
    [00:40] L'annonce politique a directement provoqué le krach.
    """

    claims = extract_claim_texts(transcript)

    assert len(claims) == 3
    assert any("Nasdaq" in claim for claim in claims)
    assert any("pourrait" in claim for claim in claims)
    assert any("provoqué" in claim for claim in claims)
    assert all("budget" not in claim for claim in claims)
