from __future__ import annotations

import re
from pathlib import Path

APP_LIB = Path(__file__).resolve().parents[2] / "app" / "lib"


def _dart_sources() -> list[Path]:
    return sorted(APP_LIB.rglob("*.dart"))


def test_flutter_production_code_has_no_hardcoded_market_prices():
    forbidden = [
        "€52 840",
        "€2 210",
        "€128",
        "+2,4 %",
        "+1,8 %",
        "52840",
        "2210",
        "81634.80",
        "84200",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _dart_sources())
    for token in forbidden:
        assert token not in combined


def test_flutter_chart_does_not_draw_synthetic_market_candles():
    chart_screen = APP_LIB / "screens" / "chart_screen.dart"
    text = chart_screen.read_text(encoding="utf-8")
    assert "_syntheticCandle" not in text
    assert "_chartValues" not in text
    assert "Bougies OHLCV indisponibles" in text


def test_fixtures_cannot_reach_the_production_runtime_path():
    """Fixtures may hold invented numbers; nothing must route to them by default.

    The provider fixtures exist so tests can run without network. They become
    dangerous the moment a runtime path can select them without the operator
    asking, so the guard is that every entry point into them is gated on
    MOCK_MODE and nothing else.
    """
    # The live Settings object is not consulted: the test session deliberately
    # turns MOCK_MODE on, so reading it here would assert the wrong thing. What
    # matters is the declared default that a deployment inherits.
    settings_src = (
        Path(__file__).resolve().parents[2]
        / "backend" / "crypto_intel" / "settings.py"
    ).read_text(encoding="utf-8")
    declaration = next(
        line for line in settings_src.splitlines() if "mock_mode" in line
    )
    assert "False" in declaration, (
        f"MOCK_MODE does not default to False ({declaration.strip()!r}); "
        "fixtures would serve a deployment that sets no environment"
    )

    fixtures = Path(__file__).resolve().parents[2] / "backend" / "crypto_intel" / "providers" / "fixtures.py"
    callers = []
    root = Path(__file__).resolve().parents[2] / "backend" / "crypto_intel"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "fixtures" in text and path != fixtures:
            callers.append((path, text))

    for path, text in callers:
        assert "mock_mode" in text, (
            f"{path.relative_to(root)} reaches the fixtures without checking "
            "MOCK_MODE, so invented data could be served in production"
        )


def test_snapshot_freshness_is_never_rendered_verbatim():
    """A bundled snapshot's own freshness claim is frozen at capture time.

    The snapshots record `freshness: LIVE` and an age of milliseconds because
    that was true the instant they were exported. Rendering those fields months
    later labels stale numbers as real-time, which is the exact failure this
    page must not have.
    """
    today_screen = APP_LIB / "screens" / "today_screen.dart"
    text = today_screen.read_text(encoding="utf-8")
    for frozen in ("market.status", "market.freshness", "market.ageSeconds"):
        assert frozen not in text, f"{frozen} is displayed straight from the payload"

    assert (APP_LIB / "api" / "freshness.dart").exists(), (
        "the derived-freshness policy is missing"
    )


def test_bundled_snapshots_still_carry_an_observation_timestamp():
    """Derived freshness needs `as_of`; without it the app must show nothing.

    This guards the export rather than the app: a snapshot exported without
    timestamps would leave the UI unable to tell fresh from ancient, and its
    only correct response would be to render everything unavailable.
    """
    import json

    snapshots = Path(__file__).resolve().parents[2] / "app" / "assets" / "api_snapshots"
    for asset in ("BTC", "ETH", "SOL"):
        path = snapshots / f"today__{asset}.json"
        if not path.exists():
            continue
        market = json.loads(path.read_text()).get("market_data") or {}
        if market.get("price_usd") is None:
            continue
        assert market.get("as_of") or market.get("timestamp"), (
            f"{path.name} carries a price with no observation timestamp"
        )


def test_deployment_never_caches_data_snapshots_as_immutable():
    """Flutter does not hash asset filenames, so `immutable` freezes the data.

    The deployment marked `/assets/(.*)` as immutable for a year while serving
    `main.dart.js` with no-cache. The result was a browser running new code
    against snapshots captured before those snapshots even carried a price:
    the page showed a funding percentile and an uncertainty score from an
    older build, above a price rendered UNAVAILABLE. Code and data must age at
    the same rate, or they contradict each other.
    """
    import json

    root = Path(__file__).resolve().parents[2]
    for name in ("vercel.json", "app/vercel.json"):
        path = root / name
        if not path.exists():
            continue
        config = json.loads(path.read_text(encoding="utf-8"))
        for rule in config.get("headers", []):
            source = rule.get("source", "")
            if "/assets/" not in source:
                continue
            for header in rule.get("headers", []):
                if header.get("key", "").lower() != "cache-control":
                    continue
                value = header["value"].lower()
                assert "immutable" not in value, (
                    f"{name} serves {source} as immutable; asset filenames are "
                    "not content-hashed, so bundled data can never refresh"
                )
                assert "max-age=31536000" not in value, (
                    f"{name} pins {source} for a year"
                )


def test_the_client_asks_for_the_directory_pubspec_actually_ships():
    """A mismatch here fails silently and looks exactly like missing data.

    If the client requests `assets/x/` while pubspec bundles `assets/y/`, every
    snapshot lookup misses and the page renders UNAVAILABLE across the board -
    indistinguishable, on screen, from a backend outage. The two must be read
    from the same string.
    """
    root = Path(__file__).resolve().parents[2]

    client = (root / "app" / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    requested = re.search(r"return '(assets/[^/]+)/\$name\.json';", client)
    assert requested, "the snapshot path is no longer a recognisable literal"
    directory = requested.group(1)

    pubspec = (root / "app" / "pubspec.yaml").read_text(encoding="utf-8")
    assert f"- {directory}/" in pubspec, (
        f"client requests {directory}/ but pubspec does not bundle it"
    )

    shipped = root / "app" / directory
    assert shipped.is_dir(), f"{directory} does not exist on disk"
    assert list(shipped.glob("today__*.json")), f"{directory} ships no today snapshots"


def test_the_export_script_writes_where_the_app_reads():
    root = Path(__file__).resolve().parents[2]
    client = (root / "app" / "lib" / "api" / "client.dart").read_text(encoding="utf-8")
    directory = re.search(r"return 'assets/([^/]+)/\$name\.json';", client).group(1)

    script = (root / "scripts" / "export_flutter_static_api.py").read_text(encoding="utf-8")
    assert f'"{directory}"' in script, (
        f"the export script does not write into assets/{directory}"
    )


def test_a_stale_price_is_labelled_not_erased():
    """Hiding the number is as unhelpful as pretending it is current.

    A deployment without a reachable backend serves bundled snapshots, so its
    data is always ageing - that is the normal state, not a fault. Replacing
    the price with the word "PÉRIMÉ" past a day emptied the page entirely.
    The value stays; the freshness label beside it carries the age.
    """
    text = (APP_LIB / "screens" / "today_screen.dart").read_text(encoding="utf-8")
    price_fn = text.split("String _marketPriceLabel(", 1)[1].split("\n}", 1)[0]
    assert "'PÉRIMÉ'" not in price_fn, (
        "the price label substitutes a status word for the value"
    )
    assert "'INDISPONIBLE'" in price_fn, (
        "a genuinely absent price must still read as unavailable"
    )


def test_a_dated_analysis_says_so_rather_than_claiming_the_present():
    text = (APP_LIB / "screens" / "today_screen.dart").read_text(encoding="utf-8")
    verdict = text.split("String _verdictBody(", 1)[1].split("\n}", 1)[0]
    assert "blocksAnalysis" in verdict, (
        "the verdict sentence ignores whether its data is still current"
    )
    assert "pas le marché actuel" in verdict, (
        "a stale reading must state that it does not describe the present"
    )
