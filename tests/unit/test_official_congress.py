from __future__ import annotations

from datetime import UTC, datetime

from crypto_intel.future_events.models import DirectionalBias, FutureEventStatus
from crypto_intel.providers.events.official_congress import congress_actions_to_events

NOW = datetime(2028, 9, 10, 12, tzinfo=UTC)


def _bill() -> dict[str, object]:
    return {
        "congress": 122,
        "type": "hr",
        "number": "42",
        "title": "Digital Asset Market Clarity Act of 2028",
        "url": "https://api.congress.gov/v3/bill/122/hr/42?format=json",
    }


def test_congress_motion_is_not_promoted_to_senate_passage():
    actions = {
        "122:hr:42": [
            {
                "actionDate": "2028-09-09",
                "text": "Motion to proceed to consideration of measure made in Senate.",
                "actionCode": "MOTION",
            }
        ]
    }

    event = congress_actions_to_events([_bill()], actions, fetched_at=NOW)[0]

    assert event.metadata["regulatory_stage"] == "MOTION"
    assert "Adopté par le Sénat" not in event.title
    assert event.status is FutureEventStatus.RELEASED
    assert event.directional_effect is DirectionalBias.NEUTRAL
    assert event.metadata["action_time_precision"] == "DATE"
    assert event.source_url.startswith("https://api.congress.gov/")


def test_congress_passage_requires_explicit_official_action_wording():
    actions = {
        "122:hr:42": [
            {
                "actionDate": "2028-09-10",
                "text": "Passed Senate with an amendment by Yea-Nay Vote.",
            }
        ]
    }

    event = congress_actions_to_events([_bill()], actions, fetched_at=NOW)[0]

    assert event.metadata["regulatory_stage"] == "PASSED_SENATE"
    assert "Adopté par le Sénat" in event.title
    assert event.importance.value == "CRITICAL"


def test_old_or_unrelated_congress_actions_fail_closed():
    unrelated = {**_bill(), "title": "Agricultural Weather Stations Act"}
    actions = {"122:hr:42": [{"actionDate": "2028-01-01", "text": "Passed Senate."}]}

    assert congress_actions_to_events([_bill()], actions, fetched_at=NOW) == []
    assert congress_actions_to_events([unrelated], actions, fetched_at=NOW) == []
