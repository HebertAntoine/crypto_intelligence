from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_intel.providers.events.official_calendars import (
    parse_bea_calendar,
    parse_bls_ics,
    parse_fomc_calendar,
    parse_treasury_auctions,
)

NOW = datetime(2028, 8, 10, tzinfo=UTC)


def test_fomc_parser_uses_official_panel_and_eastern_timezone():
    html = """
    <div class="panel"><div class="panel-heading"><h4>2028 FOMC Meetings</h4></div>
      <div class="row fomc-meeting">
        <div class="fomc-meeting__month"><strong>September</strong></div>
        <div class="fomc-meeting__date">19-20*</div>
      </div>
      <div class="row fomc-meeting">
        <div class="fomc-meeting__month"><strong>December</strong></div>
        <div class="fomc-meeting__date">12-13</div>
      </div>
    </div>
    """
    events = parse_fomc_calendar(html, fetched_at=NOW)

    assert len(events) == 2
    assert events[0].event_type == "FOMC_DECISION"
    assert events[0].scheduled_at == datetime(2028, 9, 20, 18, tzinfo=UTC)
    assert events[1].scheduled_at == datetime(2028, 12, 13, 19, tzinfo=UTC)
    assert events[0].metadata["includes_sep"] is True
    assert events[0].source_url.startswith("https://www.federalreserve.gov/")


def test_bls_ics_filters_major_releases_and_preserves_source_uid():
    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:cpi-2028@bls.gov
DTSTART;TZID=America/New_York:20280914T083000
SUMMARY:Consumer Price Index for August 2028
END:VEVENT
BEGIN:VEVENT
UID:minor@bls.gov
DTSTART;TZID=America/New_York:20280915T100000
SUMMARY:County Employment and Wages for Q1 2028
END:VEVENT
END:VCALENDAR
"""
    events = parse_bls_ics(ics, fetched_at=NOW)

    assert len(events) == 1
    assert events[0].event_type == "CPI"
    assert events[0].scheduled_at == datetime(2028, 9, 14, 12, 30, tzinfo=UTC)
    assert events[0].metadata["source_uid"] == "cpi-2028@bls.gov"


def test_bea_parser_reads_year_date_time_and_release_link():
    html = """
    <h2>Year 2028</h2><table><tr>
      <td><div class="release-date">September 28</div><small>8:30 AM</small></td>
      <td class="release-title">Personal Income and Outlays, August 2028</td>
      <td><a href="/news/2028/personal-income">View</a></td>
    </tr></table>
    """
    event = parse_bea_calendar(html, fetched_at=NOW)[0]

    assert event.event_type == "PCE_PERSONAL_INCOME"
    assert event.scheduled_at == datetime(2028, 9, 28, 12, 30, tzinfo=UTC)
    assert event.source_url == "https://www.bea.gov/news/2028/personal-income"


def test_treasury_same_hour_different_securities_are_not_merged():
    rows = [
        {
            "cusip": "AAA",
            "auctionDate": "2028-08-11T00:00:00",
            "securityType": "Bill",
            "securityTerm": "13-Week",
            "closingTimeCompetitive": "11:30 AM",
        },
        {
            "cusip": "BBB",
            "auctionDate": "2028-08-11T00:00:00",
            "securityType": "Bill",
            "securityTerm": "26-Week",
            "closingTimeCompetitive": "11:30 AM",
        },
    ]

    events = parse_treasury_auctions(rows, fetched_at=NOW)

    assert len(events) == 2
    assert {event.metadata["cusip"] for event in events} == {"AAA", "BBB"}
    assert all(event.directional_effect.value == "NEUTRAL" for event in events)


@pytest.mark.parametrize("parser,payload", [(parse_fomc_calendar, ""), (parse_bea_calendar, "")])
def test_empty_official_payload_fails_closed_at_parser_boundary(parser, payload):
    assert parser(payload, fetched_at=NOW) == []
