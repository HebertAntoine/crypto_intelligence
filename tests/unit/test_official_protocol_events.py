from __future__ import annotations

import json
from datetime import UTC, datetime

from crypto_intel.core.enums import Asset
from crypto_intel.future_events.models import (
    DirectionalBias,
    EventScheduleType,
    FutureEventStatus,
)
from crypto_intel.providers.events.official_protocols import (
    parse_ethereum_protocol_feed,
    parse_solana_incidents,
    parse_solana_news,
)

NOW = datetime(2028, 9, 10, 12, tzinfo=UTC)


def test_ethereum_exact_utc_activation_becomes_scheduled_neutral_event():
    xml = """<?xml version="1.0"?><rss><channel><item>
      <title>Orchid Mainnet Upgrade Announcement</title>
      <link>https://blog.ethereum.org/2028/09/09/orchid-mainnet</link>
      <pubDate>Sat, 09 Sep 2028 10:00:00 GMT</pubDate>
      <category>Protocol</category>
      <description>The upgrade activates September 16, 2028, 21:49:11 UTC.</description>
    </item></channel></rss>"""

    event = parse_ethereum_protocol_feed(xml, fetched_at=NOW)[0]

    assert event.affected_assets == [Asset.ETH]
    assert event.schedule_type is EventScheduleType.SCHEDULED
    assert event.scheduled_at == datetime(2028, 9, 16, 21, 49, 11, tzinfo=UTC)
    assert event.directional_effect is DirectionalBias.NEUTRAL
    assert event.source_url.startswith("https://blog.ethereum.org/")


def test_ethereum_does_not_invent_schedule_from_date_without_exact_utc_time():
    xml = """<?xml version="1.0"?><rss><channel><item>
      <title>Protocol testnet update on September 16, 2028</title>
      <link>https://blog.ethereum.org/2028/09/09/testnet-update</link>
      <pubDate>Sat, 09 Sep 2028 10:00:00 GMT</pubDate>
      <category>Protocol</category>
      <description>A testnet update is planned; timing will be confirmed.</description>
    </item></channel></rss>"""

    event = parse_ethereum_protocol_feed(xml, fetched_at=NOW)[0]

    assert event.schedule_type is EventScheduleType.UNSCHEDULED
    assert event.scheduled_at is None
    assert event.status is FutureEventStatus.RELEASED


def test_solana_jsonld_only_accepts_official_protocol_sections():
    posts = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BlogPosting",
                "url": "https://solana.com/news/mainnet-upgrade",
                "headline": "Mainnet Upgrade",
                "description": "Activation October 2, 2028 at 14:00 UTC.",
                "datePublished": "2028-09-09T10:00:00Z",
                "articleSection": "Upgrades",
            },
            {
                "@type": "BlogPosting",
                "url": "https://solana.com/news/community-story",
                "headline": "Community story",
                "description": "A community member profile.",
                "datePublished": "2028-09-09T10:00:00Z",
                "articleSection": "Community",
            },
        ],
    }
    html = f'<script type="application/ld+json">{json.dumps(posts)}</script>'

    events = parse_solana_news(html, fetched_at=NOW)

    assert len(events) == 1
    assert events[0].affected_assets == [Asset.SOL]
    assert events[0].scheduled_at == datetime(2028, 10, 2, 14, tzinfo=UTC)
    assert events[0].directional_effect is DirectionalBias.NEUTRAL


def test_solana_active_incident_is_high_amplitude_but_directionless():
    payload = {
        "incidents": [
            {
                "id": "incident-1",
                "name": "Mainnet Beta block production degraded",
                "status": "investigating",
                "impact": "critical",
                "created_at": "2028-09-10T10:00:00Z",
                "updated_at": "2028-09-10T11:00:00Z",
                "resolved_at": None,
                "incident_updates": [
                    {"body": "Engineers are investigating degraded block production."}
                ],
            }
        ]
    }

    event = parse_solana_incidents(payload, fetched_at=NOW)[0]

    assert event.status is FutureEventStatus.ACTIVE
    assert event.importance.value == "CRITICAL"
    assert event.magnitude_effect.value == "HIGH"
    assert event.directional_effect is DirectionalBias.NEUTRAL
    assert event.source_reference == "incident-1"


def test_old_resolved_solana_incident_is_not_reintroduced():
    payload = {
        "incidents": [
            {
                "id": "old",
                "name": "Old outage",
                "status": "resolved",
                "impact": "critical",
                "created_at": "2028-01-01T10:00:00Z",
                "updated_at": "2028-01-01T12:00:00Z",
                "resolved_at": "2028-01-01T12:00:00Z",
            }
        ]
    }

    assert parse_solana_incidents(payload, fetched_at=NOW) == []
