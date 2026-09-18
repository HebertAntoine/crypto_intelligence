"""Sections 21-22: the Fed is not the only central bank that moves crypto."""

from datetime import UTC, datetime

from crypto_intel.future_events.models import (
    EventImportance,
    ExpectedMovement,
    FutureEventCategory,
    FutureEventSourceTier,
)
from crypto_intel.providers.events.central_banks import (
    parse_boj_calendar,
    parse_ecb_calendar,
)

FETCHED = datetime(2026, 9, 18, 12, tzinfo=UTC)

ECB_HTML = """
<div class="definition-list -zebra"><dl>
  <dt>10/09/2026</dt>
  <dd>Governing Council of the ECB: non-monetary policy meeting (in Frankfurt)</dd>
  <dt>28/10/2026</dt>
  <dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 1)</dd>
  <dt>29/10/2026</dt>
  <dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 2),
      followed by press conference</dd>
</dl></div>
"""

BOJ_HTML = """
<table><caption>Table : 2026</caption>
  <tr><th>Date of MPM</th><th>Release Schedule</th></tr>
  <tr><td>Jan. 22 (Thurs.), 23 (Fri.) [PDF 171KB]</td><td>Jan. 23 (Fri.)</td></tr>
  <tr><td>Mar. 18 (Wed.), 19 (Thurs.)</td><td>-</td></tr>
</table>
"""


# --- ECB --------------------------------------------------------------------


def test_ecb_non_monetary_meeting_is_not_a_rate_decision():
    """The Governing Council also meets on governance business: no rate is set."""

    events = parse_ecb_calendar(ECB_HTML, fetched_at=FETCHED)

    assert all(event.scheduled_at.date() != datetime(2026, 9, 10).date() for event in events)


def test_ecb_decision_is_anchored_on_day_two():
    """Day 1 has no decision; anchoring there puts the event a day early."""

    events = parse_ecb_calendar(ECB_HTML, fetched_at=FETCHED)

    assert len(events) == 1
    assert events[0].scheduled_at.date() == datetime(2026, 10, 29).date()


def test_ecb_decision_uses_the_published_announcement_time():
    """14:15 CET is the ECB's own convention, which is 13:15 UTC in October."""

    event = parse_ecb_calendar(ECB_HTML, fetched_at=FETCHED)[0]

    assert event.scheduled_at == datetime(2026, 10, 29, 13, 15, tzinfo=UTC)


def test_ecb_event_is_tier_a_monetary_policy():
    event = parse_ecb_calendar(ECB_HTML, fetched_at=FETCHED)[0]

    assert event.category is FutureEventCategory.MONETARY_POLICY
    assert event.source_tier is FutureEventSourceTier.A
    assert event.importance is EventImportance.HIGH


# --- BoJ --------------------------------------------------------------------


def test_boj_meeting_is_anchored_on_the_closing_day():
    """The statement lands when the two-day meeting ends, not when it opens."""

    events = parse_boj_calendar(BOJ_HTML, fetched_at=FETCHED)

    assert [event.scheduled_at.date() for event in events] == [
        datetime(2026, 1, 23).date(),
        datetime(2026, 3, 19).date(),
    ]


def test_boj_time_is_flagged_as_approximate():
    """The BoJ publishes no fixed hour, so nothing downstream may treat it as one."""

    event = parse_boj_calendar(BOJ_HTML, fetched_at=FETCHED)[0]

    assert event.metadata["time_is_approximate"] is True


def test_boj_names_the_carry_channel():
    """Why a Tokyo meeting reaches a crypto portfolio at all."""

    event = parse_boj_calendar(BOJ_HTML, fetched_at=FETCHED)[0]

    assert "portage" in event.metadata["transmission"]


# --- Shared contract --------------------------------------------------------


def test_a_scheduled_decision_carries_amplitude_not_direction():
    """A meeting on a calendar cannot tell us which way rates go."""

    for event in parse_ecb_calendar(ECB_HTML) + parse_boj_calendar(BOJ_HTML):
        assert event.magnitude_effect is ExpectedMovement.HIGH
        assert event.metadata["direction_known"] is False


def test_no_meeting_date_is_hardcoded():
    """Every date must come from the institution's own page."""

    assert parse_ecb_calendar("<html></html>") == []
    assert parse_boj_calendar("<html></html>") == []
