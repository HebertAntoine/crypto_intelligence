"""Official US series, parsed from the formats the institutions actually publish."""

from datetime import UTC, datetime, timedelta

from crypto_intel.providers.macro.official_us import (
    RELEASE_DELAY,
    _available_at,
    parse_bls,
    parse_effr,
    parse_h41,
    parse_rrp,
    parse_tga,
    parse_treasury_curve,
)

CURVE = (
    'Date,"1 Mo","2 Yr","10 Yr","30 Yr"\n'
    "09/18/2026,3.97,4.76,5.01,5.34\n"
    "09/17/2026,3.96,4.70,4.95,N/A\n"
)
REAL = 'Date,"5 YR","10 YR"\n09/18/2026,2.55,2.68\n'


def test_treasury_curve_reads_each_wanted_column_and_skips_blanks():
    rows = parse_treasury_curve(CURVE, {"2 Yr": "macro.us2y", "10 Yr": "macro.us10y", "30 Yr": "macro.us30y"})
    by_key = {(m, d.day): v for m, d, v in rows}

    assert by_key[("macro.us10y", 18)] == 5.01
    assert by_key[("macro.us2y", 17)] == 4.70
    assert ("macro.us30y", 17) not in by_key  # N/A is absent, never zero
    real = parse_treasury_curve(REAL, {"10 YR": "macro.real10y"})
    assert real == [("macro.real10y", datetime(2026, 9, 18, tzinfo=UTC), 2.68)]


def test_tga_reads_both_statement_formats():
    current = {"data": [
        {"record_date": "2026-09-17", "account_type": "Treasury General Account (TGA) Opening Balance",
         "open_today_bal": "991708", "close_today_bal": "null"},
        {"record_date": "2026-09-17", "account_type": "Treasury General Account (TGA) Closing Balance",
         "open_today_bal": "972675", "close_today_bal": "null"},
    ]}
    legacy = {"data": [
        {"record_date": "2020-06-01", "account_type": "Federal Reserve Account",
         "open_today_bal": "1449129", "close_today_bal": "1394436"},
        {"record_date": "2020-06-01", "account_type": "Short-Term Cash Investments (Table V)",
         "open_today_bal": "0", "close_today_bal": "0"},
    ]}

    assert parse_tga(current) == [(datetime(2026, 9, 17, tzinfo=UTC), 972675.0)]
    assert parse_tga(legacy) == [(datetime(2020, 6, 1, tzinfo=UTC), 1394436.0)]


def test_rrp_sums_reverse_repo_operations_per_day():
    payload = {"repo": {"operations": [
        {"operationDate": "2026-09-18", "operationType": "Reverse Repo", "totalAmtAccepted": 576000000},
        {"operationDate": "2026-09-18", "operationType": "Repo", "totalAmtAccepted": 99},
    ]}}
    assert parse_rrp(payload) == [(datetime(2026, 9, 18, tzinfo=UTC), 576000000.0)]


def test_effr_keeps_only_the_effective_rate():
    payload = {"refRates": [
        {"effectiveDate": "2026-09-17", "type": "EFFR", "percentRate": 3.88},
        {"effectiveDate": "2026-09-17", "type": "OBFR", "percentRate": 3.87},
    ]}
    assert parse_effr(payload) == [(datetime(2026, 9, 17, tzinfo=UTC), 3.88)]


def test_h41_reads_total_assets_and_the_wednesday_it_describes():
    html = """
    <p>Release Date: September 17, 2026</p>
    <table><tr><th></th><th>Sep 16, 2026</th><th>Change since Sep 9, 2026</th></tr>
    <tr><td>Total assets</td><td>(0)</td><td>6,746,548</td><td>+ 5,929</td><td>+ 137,951</td></tr>
    </table>
    """
    parsed = parse_h41(html)
    assert parsed["day"] == datetime(2026, 9, 16, tzinfo=UTC)
    assert parsed["total_assets_musd"] == 6746548.0
    assert parsed["change_week_musd"] == 5929.0


def test_bls_monthly_values_ignore_the_annual_average():
    payload = {"Results": {"series": [{"data": [
        {"year": "2026", "period": "M08", "value": "334.131"},
        {"year": "2025", "period": "M13", "value": "320.0"},
    ]}]}}
    assert parse_bls(payload) == [(datetime(2026, 8, 1, tzinfo=UTC), 334.131)]


def test_a_monthly_release_is_never_available_during_its_month():
    august = datetime(2026, 8, 1, tzinfo=UTC)
    assert _available_at("macro.cpi", august) > datetime(2026, 9, 1, tzinfo=UTC)
    # The curve is published after the close, never at the day's start.
    assert RELEASE_DELAY["macro.us10y"] >= timedelta(hours=20)
