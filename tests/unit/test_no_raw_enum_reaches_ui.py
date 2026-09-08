"""Aucun identifiant technique ne doit atteindre l'écran.

Les moteurs raisonnent en anglais et c'est très bien: leurs enums sont des
identifiants, pas du texte. Le défaut était qu'ils traversaient l'app jusqu'à
l'utilisateur — « Régime strongly bullish », « REINTEGRATION to the up through
81375.745 », « 4h price is near range top ».

Ce test interroge l'endpoint réel: il ne vérifie pas une table de traduction,
il vérifie ce qui sortirait effectivement.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from crypto_intel.api.routes_lot4 import today

ASSETS = ["BTC", "ETH", "SOL"]

# Un identifiant technique est un SCREAMING_SNAKE_CASE. Repérer « tout mot en
# majuscules » signalait « DONNÉES INSUFFISANTES », qui est du français: les
# titres sont capitalisés par choix de design.
RAW_ENUM = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

# Valeurs d'enum susceptibles d'apparaître seules, sans underscore.
# « FAVORABLE » n'y figure pas: c'est aussi un mot français, et le signaler
# transformait « POUR DEVENIR PLUS FAVORABLE » — du français correct — en
# fuite d'identifiant. « UNFAVORABLE » et « NEUTRAL », eux, sont anglais.
LONE_ENUMS = {
    "UNCLEAR", "UNAVAILABLE", "UNDETERMINED", "REINTEGRATION", "BREAKOUT",
    "UNFAVORABLE", "NEUTRAL", "BULLISH", "BEARISH", "EXTREME",
    "ELEVATED", "STALE", "DELAYED", "FAKEOUT", "RETEST",
}

# Sigles qui restent en majuscules parce que c'est leur forme française.
ALLOWED = {
    "BTC", "ETH", "SOL", "ETF", "RSI", "ATR", "MFE", "MAE", "DVOL", "FOMC",
    "CPI", "PCE", "USD", "EUR", "OHLCV", "FDR", "LIVE", "PIB", "PMI",
}

# Mots anglais de domaine qui trahissent une phrase non traduite.
ENGLISH = re.compile(
    r"\b(price is|is near|range top|range bottom|zone quality|bar\(s\)|"
    r"would break|close above|close below|invalidate|the current|structure is|"
    r"strongly bullish|strongly bearish)\b",
    re.IGNORECASE,
)


def _user_facing(payload: dict) -> list[tuple[str, str]]:
    """Les chaînes qu'un écran affiche, avec leur emplacement."""
    out: list[tuple[str, str]] = []
    explanation = payload["buy_opportunity_explanation"]

    out.append(("headline", explanation["headline"]))
    out.append(("summary", explanation["short_summary"]))
    for group in ("positives", "waits", "negatives", "missing"):
        for factor in explanation[group]:
            out.append((f"{group}.title", factor["title"]))
            out.append((f"{group}.short_text", factor["short_text"]))
    for key in (
        "what_would_improve", "what_would_deteriorate",
        "what_would_change_structure",
    ):
        for line in explanation.get(key, []):
            out.append((key, line))

    pressure = payload["market_pressure"]
    out.append(("pressure.label", pressure["label"]))
    for component in pressure["components"]:
        out.append(("pressure.component", component["label"]))
        out.append(("pressure.detail", component.get("detail") or ""))
        out.append(("pressure.reason", component.get("reason") or ""))

    # The compact page is the surface a person actually reads first, so it is
    # held to the same rule as the explanation underneath it.
    out.extend(_page_strings(payload.get("page") or {}))
    return [(where, text) for where, text in out if text]


# Keys whose values are identifiers by design: the client switches on them and
# never prints them. Everything else in the page is read by a person.
_MACHINE_KEYS = frozenset({
    "state", "analysis_id", "asset", "key", "family", "kind", "coverage",
    "availability", "direction", "alignment", "importance", "freshness",
    "timeframe", "source", "id", "category", "polarity", "evidence_level",
    "reading_order", "raw_input", "raw_value", "type", "asset_scope",
    "edge_state", "from_state", "to_state", "guard_rails", "method",
    "formula", "drift_severity", "price_source", "schema_version", "inputs",
    "data_quality", "coverage_level", "dominant_gate", "weights",
})


def _page_strings(node, path: str = "page") -> list[tuple[str, str]]:
    """Every human-readable string in the rendered page, with its path."""
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _MACHINE_KEYS:
                continue
            out.extend(_page_strings(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_page_strings(value, f"{path}[{index}]"))
    elif isinstance(node, str):
        out.append((path, node))
    return out


@pytest.fixture(scope="module", params=ASSETS)
def payload(request, seeded_market_history):
    return asyncio.run(today(request.param))


def test_no_raw_identifier_reaches_the_user(payload):
    offenders: list[str] = []
    for where, text in _user_facing(payload):
        for token in RAW_ENUM.findall(text):
            if token in ALLOWED:
                continue
            offenders.append(f"{where}: {token!r} dans {text[:70]!r}")
        for token in re.findall(r"\b[A-Z]{4,}\b", text):
            if token in LONE_ENUMS:
                offenders.append(f"{where}: {token!r} dans {text[:70]!r}")
    assert not offenders, "identifiants bruts visibles:\n" + "\n".join(offenders)


def test_no_english_domain_sentence_reaches_the_user(payload):
    offenders = [
        f"{where}: {text[:80]!r}"
        for where, text in _user_facing(payload)
        if ENGLISH.search(text)
    ]
    assert not offenders, "phrases anglaises visibles:\n" + "\n".join(offenders)


def test_the_three_change_categories_are_distinct(payload):
    """Une invalidation de structure n'est pas une dégradation.

    « Une clôture 4H au-dessus du haut de range » se trouvait dans « ce qui
    dégraderait », alors que c'est une cassure haussière: elle invalide le
    range sans dégrader le marché.
    """
    explanation = payload["buy_opportunity_explanation"]
    for key in (
        "what_would_improve", "what_would_deteriorate",
        "what_would_change_structure",
    ):
        assert key in explanation

    degrade = " ".join(explanation["what_would_deteriorate"]).lower()
    assert "au-dessus du haut de range" not in degrade, (
        "une cassure haussière est classée comme dégradation"
    )


def test_the_dart_label_layer_covers_every_state_it_claims():
    """La couche de présentation ne doit pas prétendre traduire à vide."""
    from pathlib import Path

    labels = (
        Path(__file__).resolve().parents[2]
        / "app" / "lib" / "presentation" / "domain_labels.dart"
    ).read_text(encoding="utf-8")

    for state in (
        "STRONGLY_BULLISH", "RANGE_STRUCTURE", "NEAR_RANGE_TOP",
        "REINTEGRATION", "NO_MEASURABLE_EDGE", "EXTREME_NEGATIVE",
    ):
        assert state in labels, f"{state} n'a pas de libellé français"
    assert "looksLikeRawEnum" in labels
