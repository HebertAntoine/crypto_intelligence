from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crypto_intel.providers.macro.twelve_data import (
    BY_SYMBOL,
    TwelveDataProvider,
    parse_time_series,
)
from crypto_intel.settings import reload_settings


def _payload(
    *values: dict[str, object],
    symbol: str = "SPX",
    exchange_timezone: str = "America/New_York",
) -> dict[str, object]:
    return {
        "meta": {
            "symbol": symbol,
            "interval": "1day",
            "currency": "USD",
            "exchange_timezone": exchange_timezone,
            "exchange": "United States",
            "type": "Index",
        },
        "values": list(values),
        "status": "ok",
    }


def test_twelve_data_daily_bar_keeps_observation_and_availability_separate() -> None:
    rows = parse_time_series(
        _payload({"datetime": "2026-10-23", "close": "5791.25"}),
        BY_SYMBOL["SPX"],
        fetched_at=datetime(2026, 10, 26, 12, tzinfo=UTC),
    )

    assert len(rows) == 1
    observation = rows[0]
    assert observation.value == 5791.25
    assert observation.timestamp == datetime(2026, 10, 23, 4, tzinfo=UTC)
    # Midnight after the represented New York day: conservative and DST-aware.
    assert observation.meta["available_at"] == "2026-10-24T04:00:00+00:00"
    assert observation.meta["publication_time"] is None
    assert observation.meta["quality_flags"] == ["DAILY_AVAILABILITY_CONSERVATIVE"]
    assert observation.provenance.license_note


def test_twelve_data_null_invalid_and_non_finite_values_are_never_filled() -> None:
    rows = parse_time_series(
        _payload(
            {"datetime": "2026-10-23", "close": None},
            {"datetime": "2026-10-22", "close": ""},
            {"datetime": "2026-10-21", "close": "not-a-number"},
            {"datetime": "2026-10-20", "close": "NaN"},
        ),
        BY_SYMBOL["SPX"],
    )

    assert rows == []


def test_twelve_data_rejects_a_response_for_a_different_instrument() -> None:
    rows = parse_time_series(
        _payload({"datetime": "2026-10-23", "close": "100"}, symbol="NDX"),
        BY_SYMBOL["SPX"],
    )

    assert rows == []


def test_twelve_data_never_returns_an_unfinished_daily_bar() -> None:
    payload = _payload({"datetime": "2026-10-26", "close": "5800"})

    before_available = parse_time_series(
        payload,
        BY_SYMBOL["SPX"],
        fetched_at=datetime(2026, 10, 26, 20, tzinfo=UTC),
    )
    after_available = parse_time_series(
        payload,
        BY_SYMBOL["SPX"],
        fetched_at=datetime(2026, 10, 27, 4, tzinfo=UTC),
    )

    assert before_available == []
    assert len(after_available) == 1


def test_same_local_date_from_different_exchanges_is_not_compared_as_one_close() -> None:
    """T04: a date label is not treated as a shared availability instant."""

    fetched_at = datetime(2026, 10, 23, 18, tzinfo=UTC)
    tokyo = parse_time_series(
        _payload(
            {"datetime": "2026-10-23", "close": "38950"},
            symbol="N225",
            exchange_timezone="Asia/Tokyo",
        ),
        BY_SYMBOL["N225"],
        fetched_at=fetched_at,
    )
    new_york = parse_time_series(
        _payload(
            {"datetime": "2026-10-23", "close": "5791.25"},
            exchange_timezone="America/New_York",
        ),
        BY_SYMBOL["SPX"],
        fetched_at=fetched_at,
    )

    assert len(tokyo) == 1
    assert tokyo[0].meta["available_at"] == "2026-10-23T15:00:00+00:00"
    # The New York row bears the same local date but is not available until
    # 04:00 UTC the following day, so it cannot enter this point-in-time view.
    assert new_york == []


@pytest.mark.asyncio
async def test_twelve_data_requires_key_and_explicit_licence_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-only-key")
    monkeypatch.setenv("TWELVE_DATA_REDISTRIBUTION_AUTHORIZED", "false")
    reload_settings()
    try:
        status = await TwelveDataProvider().available()
        assert not status.available
        assert "licence not confirmed" in status.reason

        monkeypatch.setenv("TWELVE_DATA_REDISTRIBUTION_AUTHORIZED", "true")
        reload_settings()
        assert (await TwelveDataProvider().available()).available
    finally:
        monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
        monkeypatch.delenv("TWELVE_DATA_REDISTRIBUTION_AUTHORIZED", raising=False)
        reload_settings()
