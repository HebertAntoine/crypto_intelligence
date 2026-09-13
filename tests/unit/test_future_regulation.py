from __future__ import annotations

from datetime import UTC, datetime

from crypto_intel.engines.regulatory_catalyst import (
    RegulatoryCatalystEngine,
    RegulatoryStage,
)
from crypto_intel.future_events.models import FutureEventStatus
from crypto_intel.providers.events.official_regulation import (
    parse_cftc_calendar,
    parse_house_calendar,
    parse_senate_calendar,
    regulatory_feed_items_to_events,
)

NOW = datetime(2028, 9, 10, tzinfo=UTC)


def test_clarity_markup_is_not_reported_as_adopted():
    engine = RegulatoryCatalystEngine()

    stage = engine.classify_stage("Committee markup of the CLARITY Act")

    assert stage is RegulatoryStage.COMMITTEE_MARKUP
    assert "adopt" not in engine.stage_label(stage).lower()


def test_feed_proposal_is_source_backed_unscheduled_release():
    events = regulatory_feed_items_to_events(
        [
            {
                "title": "SEC proposes rules for crypto asset offerings",
                "summary": "Official proposed rule release",
                "url": "https://www.sec.gov/newsroom/press-releases/example",
                "published_at": datetime(2028, 9, 9, 15, tzinfo=UTC),
                "institution": "SEC",
                "source": "SEC Press Releases",
            }
        ],
        fetched_at=NOW,
    )

    assert len(events) == 1
    event = events[0]
    assert event.scheduled_at is None
    assert event.status is FutureEventStatus.RELEASED
    assert event.runtime_status(NOW) is FutureEventStatus.RELEASED
    assert event.metadata["regulatory_stage"] == "PROPOSED_RULE"
    assert event.source_tier.value == "A"
    assert event.source_url.startswith("https://www.sec.gov/")


def test_house_markup_uses_visible_official_date_not_stale_html_attribute():
    html = """
    <div class="events-future"><article class="card-h-event">
      <time datetime="2025-02-12"><span> Sep </span><span> 15</span><span> 2028</span></time>
      <h6>Markups</h6>
      <h3><a href="/calendar/EventSingle.aspx?EventID=42">Markup of the CLARITY Act</a></h3>
      <footer><span>10:00 AM</span><address>Washington, DC</address></footer>
    </article></div>
    """
    event = parse_house_calendar(html, fetched_at=NOW)[0]

    assert event.scheduled_at == datetime(2028, 9, 15, 14, tzinfo=UTC)
    assert event.metadata["regulatory_stage"] == "COMMITTEE_MARKUP"
    assert event.source_url.endswith("EventID=42")


def test_cftc_calendar_keeps_event_end_and_does_not_infer_direction():
    html = """
    <table><tbody><tr>
      <td><time datetime="2028-09-18T14:00:00Z">09/18/2028</time></td>
      <td class="views-field-title">
        <a href="/PressRoom/Events/crypto-roundtable">CFTC digital asset roundtable</a>
        <div class="field-start-date"><time datetime="2028-09-18T14:00:00Z"></time></div>
        <div class="field-end-date"><time datetime="2028-09-18T17:00:00Z"></time></div>
      </td>
    </tr></tbody></table>
    """
    event = parse_cftc_calendar(html, fetched_at=NOW)[0]

    assert event.scheduled_at == datetime(2028, 9, 18, 14, tzinfo=UTC)
    assert event.expected_end_at == datetime(2028, 9, 18, 17, tzinfo=UTC)
    assert event.metadata["regulatory_stage"] == "HEARING"
    assert event.directional_effect.value == "NEUTRAL"


def test_senate_banking_calendar_uses_official_datetime_and_stage_only():
    html = """
    <article class="hearing-item">
      <time datetime="2028-09-15T10:00">09/15/28 10:00AM</time>
      <h3><a href="/hearings/markup-of-the-digital-asset-clarity-act">
        Markup of the Digital Asset CLARITY Act
      </a></h3>
    </article>
    """

    event = parse_senate_calendar(
        html,
        source_url="https://www.banking.senate.gov/hearings",
        source_name="U.S. Senate Banking Committee",
        fetched_at=NOW,
    )[0]

    assert event.scheduled_at == datetime(2028, 9, 15, 14, tzinfo=UTC)
    assert event.metadata["regulatory_stage"] == "COMMITTEE_MARKUP"
    assert event.directional_effect.value == "NEUTRAL"
    assert event.source_url.endswith("markup-of-the-digital-asset-clarity-act")


def test_senate_agriculture_calendar_requires_visible_time():
    dated_only = """
    <div class="hearing-item">
      <time datetime="September 15, 2028">Date: 09/15/28</time>
      <a href="/hearings/digital-commodities">Digital commodities hearing</a>
    </div>
    """
    complete = dated_only.replace("Date: 09/15/28", "Date: 09/15/28 Time: 03:30pm")

    assert (
        parse_senate_calendar(
            dated_only,
            source_url="https://www.agriculture.senate.gov/hearings",
            source_name="U.S. Senate Agriculture Committee",
            fetched_at=NOW,
        )
        == []
    )
    event = parse_senate_calendar(
        complete,
        source_url="https://www.agriculture.senate.gov/hearings",
        source_name="U.S. Senate Agriculture Committee",
        fetched_at=NOW,
    )[0]
    assert event.scheduled_at == datetime(2028, 9, 15, 19, 30, tzinfo=UTC)
