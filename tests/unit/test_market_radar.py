"""Sections 41-44: attention is not direction, and stale items leave on their own."""

from datetime import UTC, datetime, timedelta

import pytest

from crypto_intel.engines.market_radar import (
    AttentionLevel,
    EventDirection,
    RadarCategory,
    RadarItem,
    RadarStatus,
    SourceTrust,
    advance,
    assign_clusters,
    confirm,
    home_items,
    interpret_result,
    is_market_material,
    is_on_home,
)

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


def item(
    *,
    category: RadarCategory = RadarCategory.CENTRAL_BANK,
    trust: SourceTrust = SourceTrust.OFFICIAL,
    title: str = "Réunion du FOMC",
    scheduled_in: timedelta | None = timedelta(hours=30),
    published_at: datetime | None = None,
    event_id: str = "evt-1",
) -> RadarItem:
    return RadarItem(
        event_id=event_id,
        title=title,
        category=category,
        trust=trust,
        source="federalreserve.gov",
        detected_at=NOW - timedelta(days=2),
        scheduled_at=NOW + scheduled_in if scheduled_in is not None else None,
        published_at=published_at,
    )


# --- Section 41: an upcoming event carries attention, never a direction ------


def test_upcoming_event_has_attention_without_direction():
    fomc = advance(item(), NOW)

    assert fomc.attention in {AttentionLevel.HIGH, AttentionLevel.CRITICAL}
    assert fomc.direction is EventDirection.UNKNOWN


def test_attention_never_produces_a_direction_whatever_the_proximity():
    for hours in (0.5, 6, 30, 240, 720):
        watched = advance(item(scheduled_in=timedelta(hours=hours)), NOW)
        assert watched.direction is EventDirection.UNKNOWN, hours


def test_imminent_event_raises_attention():
    far = advance(item(scheduled_in=timedelta(days=20)), NOW)
    soon = advance(item(scheduled_in=timedelta(hours=6)), NOW)

    order = [
        AttentionLevel.NONE,
        AttentionLevel.LOW,
        AttentionLevel.MODERATE,
        AttentionLevel.HIGH,
        AttentionLevel.CRITICAL,
    ]
    assert order.index(soon.attention) > order.index(far.attention)


# --- Section 42: direction only once a result can be compared ---------------


def test_direction_comes_from_the_gap_with_consensus():
    released = item(scheduled_in=timedelta(hours=-2))
    released.result = "CPI 2,4 %"
    released.consensus = "2,7 %"

    interpret_result(released, outcome_vs_consensus="BETTER")

    assert released.direction is EventDirection.FAVORABLE
    assert "meilleur" in released.interpretation


def test_in_line_result_is_neutral_not_favorable():
    released = item(scheduled_in=timedelta(hours=-2))
    interpret_result(released, outcome_vs_consensus="IN_LINE")

    assert released.direction is EventDirection.NEUTRAL


def test_result_contradicted_by_flows_is_reported_as_mixed():
    released = item(scheduled_in=timedelta(hours=-2))
    interpret_result(released, outcome_vs_consensus="BETTER", market_confirms=False)

    assert released.direction is EventDirection.MIXED
    assert "ne le confirment pas" in released.interpretation


def test_rate_decision_alone_is_never_coded_bullish_or_bearish():
    """A cut is not good news by definition; only the gap with what was priced says."""

    hike = item(title="La Fed relève ses taux")
    cut = item(title="La Fed abaisse ses taux")

    assert advance(hike, NOW).direction is EventDirection.UNKNOWN
    assert advance(cut, NOW).direction is EventDirection.UNKNOWN


# --- Section 43: materiality -----------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Bitcoin could reach 200k, analyst says",
        "Voici pourquoi le BTC pourrait exploser",
        "Top 5 altcoins to watch",
        "Price prediction: ETH en 2027",
    ],
)
def test_commentary_is_not_material(title):
    verdict = is_market_material(title, RadarCategory.CRYPTO_NATIVE, SourceTrust.REPUTABLE_NEWS)

    assert verdict.material is False
    assert verdict.reason


@pytest.mark.parametrize(
    ("title", "category"),
    [
        ("Fed decision: rates held at 4.25%", RadarCategory.CENTRAL_BANK),
        ("US inflation data released for August", RadarCategory.MACRO),
        ("Le Sénat adopté le texte sur les stablecoins", RadarCategory.REGULATION),
        ("Exchange halts withdrawals after exploit", RadarCategory.FINANCIAL_RISK),
    ],
)
def test_a_new_fact_is_material(title, category):
    assert is_market_material(title, category, SourceTrust.OFFICIAL).material is True


def test_social_source_is_a_lead_not_an_entry():
    verdict = is_market_material(
        "SEC approves spot ETF", RadarCategory.REGULATION, SourceTrust.SOCIAL
    )

    assert verdict.material is False
    assert "confirmer" in verdict.reason


def test_mentioning_bitcoin_is_not_a_qualification():
    assert (
        is_market_material(
            "Bitcoin dans le viseur des investisseurs",
            RadarCategory.CRYPTO_NATIVE,
            SourceTrust.REPUTABLE_NEWS,
        ).material
        is False
    )


# --- Section 44: what stops mattering leaves by itself ----------------------


def test_digested_event_expires_without_intervention():
    published = NOW - timedelta(hours=30)
    old = item(category=RadarCategory.MACRO, scheduled_in=None, published_at=published)
    old.result = "conforme"
    old.interpretation = "Résultat conforme aux attentes: peu de surprise."

    advance(old, NOW)

    assert old.status is RadarStatus.EXPIRED
    assert is_on_home(old) is False


def test_decay_window_depends_on_the_category():
    """A rules change keeps mattering longer than a rate print."""

    published = NOW - timedelta(hours=30)
    macro = item(category=RadarCategory.MACRO, scheduled_in=None, published_at=published)
    rule = item(category=RadarCategory.REGULATION, scheduled_in=None, published_at=published)
    for event in (macro, rule):
        event.result = "publié"
        event.interpretation = "lu"
        advance(event, NOW)

    assert macro.status is RadarStatus.EXPIRED
    assert rule.status is not RadarStatus.EXPIRED


def test_home_keeps_only_what_counts_now():
    live = item(event_id="live", scheduled_in=timedelta(hours=4))
    stale = item(
        event_id="stale",
        category=RadarCategory.MACRO,
        scheduled_in=None,
        published_at=NOW - timedelta(hours=40),
    )
    stale.result, stale.interpretation = "publié", "lu"

    kept = home_items([live, stale], now=NOW)

    assert [entry.event_id for entry in kept] == ["live"]


def test_home_is_capped_so_the_page_stays_readable():
    many = [item(event_id=f"e{i}", scheduled_in=timedelta(hours=3 + i)) for i in range(12)]

    assert len(home_items(many, now=NOW, limit=5)) <= 5


def test_expired_item_is_not_resurrected():
    old = item(category=RadarCategory.OTHER, scheduled_in=None, published_at=NOW - timedelta(days=5))
    old.status = RadarStatus.EXPIRED

    assert advance(old, NOW).status is RadarStatus.EXPIRED


# --- Unconfirmed detections influence nothing -------------------------------


def test_unconfirmed_detection_contributes_nothing_to_the_decision():
    rumour = item(trust=SourceTrust.SOCIAL, title="La SEC annonce demain")
    rumour.direction = EventDirection.FAVORABLE  # even if something set one

    assert rumour.decision_contribution == 0.0


def test_unconfirmed_detection_stays_low_attention():
    rumour = advance(item(trust=SourceTrust.SOCIAL, scheduled_in=timedelta(hours=3)), NOW)

    assert rumour.attention is AttentionLevel.LOW


def test_confirmation_by_an_official_source_promotes_the_item():
    lead = item(trust=SourceTrust.SOCIAL)
    confirm(lead, official_source="federalreserve.gov", trust=SourceTrust.OFFICIAL)

    assert lead.is_confirmed is True
    assert lead.trust is SourceTrust.OFFICIAL
    assert lead.status is RadarStatus.CONFIRMED


def test_confirmed_item_without_direction_still_contributes_nothing():
    """Knowing something is happening is not knowing which way it points."""

    upcoming = advance(item(), NOW)

    assert upcoming.is_confirmed is True
    assert upcoming.decision_contribution == 0.0


# --- Clustering -------------------------------------------------------------


def test_the_pieces_of_one_event_share_a_cluster():
    statement = item(event_id="stmt", scheduled_in=timedelta(hours=30))
    presser = item(event_id="presser", scheduled_in=timedelta(hours=30, minutes=30))

    assign_clusters([statement, presser])

    assert statement.cluster_id == presser.cluster_id


def test_unrelated_events_do_not_share_a_cluster():
    fomc = item(event_id="fomc", scheduled_in=timedelta(hours=30))
    cpi = item(event_id="cpi", category=RadarCategory.MACRO, scheduled_in=timedelta(hours=30))

    assign_clusters([fomc, cpi])

    assert fomc.cluster_id != cpi.cluster_id


# --- The serialised shape keeps the two notions apart -----------------------


def test_payload_exposes_attention_and_direction_as_distinct_fields():
    payload = advance(item(), NOW).to_dict()

    assert payload["attention"] in {level.value for level in AttentionLevel}
    assert payload["direction"] == EventDirection.UNKNOWN.value
    assert payload["attention"] != payload["direction"]


# --- Calibration: everything critical at once means nothing is --------------


def test_a_distant_meeting_does_not_saturate_attention():
    """The most important event on the calendar, five months out, is context."""

    distant = advance(item(scheduled_in=timedelta(days=150)), NOW)

    assert distant.attention in {AttentionLevel.NONE, AttentionLevel.LOW}
    assert is_on_home(distant) is False


def test_attention_decreases_monotonically_with_distance():
    order = [
        AttentionLevel.NONE,
        AttentionLevel.LOW,
        AttentionLevel.MODERATE,
        AttentionLevel.HIGH,
        AttentionLevel.CRITICAL,
    ]
    levels = [
        order.index(advance(item(scheduled_in=timedelta(days=days)), NOW).attention)
        for days in (1, 5, 20, 150)
    ]

    assert levels == sorted(levels, reverse=True)


def test_expired_item_carries_no_attention():
    """Whatever it was worth, it is over."""

    old = item(category=RadarCategory.MACRO, scheduled_in=None, published_at=NOW - timedelta(days=4))
    old.result, old.interpretation = "publié", "lu"

    advance(old, NOW)

    assert old.status is RadarStatus.EXPIRED
    assert old.attention is AttentionLevel.NONE


def test_a_passed_event_without_result_still_demands_attention():
    """The failure mode a freshness check never catches: recent row, no information."""

    unread = advance(item(scheduled_in=timedelta(hours=-3)), NOW)

    assert unread.status is RadarStatus.RELEASED
    assert unread.attention is AttentionLevel.CRITICAL


# --- Health summary ---------------------------------------------------------


def test_summary_counts_events_passed_without_a_result():
    from crypto_intel.engines.market_radar import radar_summary

    unread = item(event_id="unread", scheduled_in=timedelta(hours=-3))
    upcoming = item(event_id="upcoming", scheduled_in=timedelta(hours=6))

    summary = radar_summary([unread, upcoming], now=NOW)

    assert summary["awaiting_result"] == 1
    assert summary["tracked"] == 2


def test_summary_survives_an_empty_store():
    from crypto_intel.engines.market_radar import radar_summary

    assert radar_summary([], now=NOW)["tracked"] == 0


def test_bridge_maps_a_stored_catalyst_without_copying_it():
    from types import SimpleNamespace

    from crypto_intel.engines.market_radar import radar_item_from_event

    row = SimpleNamespace(
        canonical_event_id="evt-42",
        title="Décision de taux de la BCE",
        category="MONETARY_POLICY",
        source_tier="A",
        source="European Central Bank",
        detected_at=NOW,
        scheduled_at=NOW + timedelta(hours=10),
        source_published_at=None,
        source_url="https://www.ecb.europa.eu/",
        affected_assets=["BTC"],
    )

    mapped = radar_item_from_event(row)

    assert mapped.category is RadarCategory.CENTRAL_BANK
    assert mapped.trust is SourceTrust.OFFICIAL
    assert mapped.direction is EventDirection.UNKNOWN


def test_bridge_keeps_tier_e_as_a_social_lead():
    from types import SimpleNamespace

    from crypto_intel.engines.market_radar import radar_item_from_event

    row = SimpleNamespace(
        canonical_event_id="evt-99",
        title="Rumeur d'approbation",
        category="REGULATION",
        source_tier="E",
        source="réseau social",
        detected_at=NOW,
        scheduled_at=None,
        source_published_at=NOW,
        source_url=None,
        affected_assets=[],
    )

    mapped = radar_item_from_event(row)

    assert mapped.trust is SourceTrust.SOCIAL
    assert mapped.decision_contribution == 0.0


def test_home_payload_carries_attention_beside_relevance():
    """The two must travel together, or the page states one and implies the other."""

    from types import SimpleNamespace

    from crypto_intel.engines.future_decision import _with_attention

    event = SimpleNamespace(
        id="fev_1",
        canonical_event_id="canon_1",
        title="Décision de taux de la BCE",
        category="MONETARY_POLICY",
        source_tier="A",
        source="European Central Bank",
        detected_at=NOW,
        scheduled_at=NOW + timedelta(hours=8),
        source_published_at=None,
        source_url=None,
        affected_assets=["BTC"],
    )
    ranked = [SimpleNamespace(to_dict=lambda: {"event_id": "fev_1", "relevance_score": 80})]

    payload = _with_attention(ranked, [event], NOW)[0]

    assert payload["relevance_score"] == 80
    assert payload["attention"] == AttentionLevel.CRITICAL.value
    assert payload["direction"] == EventDirection.UNKNOWN.value


def test_home_payload_lookup_works_on_the_canonical_id_too():
    from types import SimpleNamespace

    from crypto_intel.engines.future_decision import _with_attention

    event = SimpleNamespace(
        id="fev_2",
        canonical_event_id="canon_2",
        title="Réunion du FOMC",
        category="MONETARY_POLICY",
        source_tier="A",
        source="Federal Reserve",
        detected_at=NOW,
        scheduled_at=NOW + timedelta(hours=8),
        source_published_at=None,
        source_url=None,
        affected_assets=[],
    )
    ranked = [SimpleNamespace(to_dict=lambda: {"event_id": "canon_2"})]

    assert "attention" in _with_attention(ranked, [event], NOW)[0]
