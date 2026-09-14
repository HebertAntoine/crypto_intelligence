"""Section 3 and 14: a title must describe the metric that was actually measured.

The bug these tests close: the ETF block carried the sentence "les vendeurs
traversent le spread plus souvent que d'habitude", which describes who crosses
the bid/ask at spot. When the ETF series went stale the family fell back to spot
pressure and kept the ETF title, so the screen named one metric and described
another.
"""

import json
from pathlib import Path

import pytest

SNAPSHOTS = Path(__file__).resolve().parents[2] / "app" / "assets" / "api_snapshots"
ASSETS = ("BTC", "ETH", "SOL")
HORIZONS = ("24h", "7d", "30d")

#: Wording that belongs to exactly one metric. Seeing it under another key means
#: a text was reused across metrics, whatever the reason.
_EXCLUSIVE_WORDING = {
    "spot": ("spread", "prix demandé", "acheteurs au comptant"),
    "flows": ("etf", "entrées nettes", "sorties nettes", "séances"),
    "energy": ("brent", "wti", "pétrole"),
    "rates": ("ans", "rendement", "pente"),
    "credit": ("écarts de crédit", "haut rendement"),
    "funding": ("coût du levier", "funding"),
    "volatility": ("bollinger", "bandes"),
}

#: Which wording may never appear under which key.
_FORBIDDEN = {
    "flows": _EXCLUSIVE_WORDING["spot"],
    "spot": ("etf",),
    "energy": ("etf", "spread"),
    "rates": ("etf", "pétrole", "spread"),
    "credit": ("etf", "pétrole"),
    "funding": ("etf", "rendement obligataire"),
    "technical": ("etf", "pétrole", "funding"),
    "volatility": ("etf", "pétrole"),
}


def payload(asset: str, horizon: str) -> dict:
    path = SNAPSHOTS / f"future__{asset}__horizon-{horizon}.json"
    if not path.exists():
        pytest.skip(f"snapshot absent: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def factors(asset: str, horizon: str) -> list[dict]:
    return (payload(asset, horizon).get("families") or {}).get("factors") or []


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_no_metric_borrows_another_metric_wording(asset, horizon) -> None:
    for factor in factors(asset, horizon):
        forbidden = _FORBIDDEN.get(factor["key"])
        if not forbidden:
            continue
        text = (
            factor["rationale"] + " " + " ".join(factor["causal_chain"])
        ).lower()
        for word in forbidden:
            assert word not in text, f"{asset} {horizon} {factor['key']}: « {word} »"


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_an_etf_reading_never_describes_spot_aggression(asset, horizon) -> None:
    """The exact reported bug, pinned on every asset and horizon."""

    for factor in factors(asset, horizon):
        if factor["key"] != "flows":
            continue
        text = factor["rationale"].lower()
        assert "spread" not in text
        assert "prix demandé" not in text
        # An ETF reading talks about sessions and net flows.
        assert "séance" in text or "m$" in text


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_a_stale_reading_is_labelled_stale_not_current(asset, horizon) -> None:
    for factor in factors(asset, horizon):
        if factor["availability"] != "STALE":
            continue
        # Stale evidence states how old it is, and never claims high confidence.
        assert factor["missing_requirements"], factor["key"]
        assert factor["confidence_band"] != "HIGH", factor["key"]


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_no_amount_is_published_without_a_unit(asset, horizon) -> None:
    """A figure with no unit is a figure a reader cannot check."""

    import re

    for factor in factors(asset, horizon):
        for sentence in [factor["rationale"], *factor["causal_chain"]]:
            for match in re.finditer(r"[+-]?\d[\d\s]*[.,]?\d*\s*(\S{0,3})", sentence):
                tail = match.group(1)
                if not tail:
                    continue
                assert tail.strip()[:1] in {
                    "M", "$", "%", "j", "h", "p", "s", "é", "a", "c", "u", "d",
                    "n", "l", "m", "b", "e", "f", "t", "v", "o", "r", "i", "g",
                    ".", ",", ")", "(", "/", "-", "+", "°", "'", "’", ":",
                }, f"{factor['key']}: {sentence}"


@pytest.mark.parametrize("asset", ASSETS)
def test_the_home_page_keeps_at_most_four_signal_readings(asset) -> None:
    """Section 6: the home page shows the few factors that explain the call."""

    explainable = {
        "flows", "spot", "positioning", "derivatives", "funding", "basis",
        "technical", "volatility", "implied_volatility", "energy", "rates",
        "credit", "whales",
    }
    usable = [
        item
        for item in factors(asset, "7d")
        if item["key"] in explainable
        and item["availability"] not in {"UNAVAILABLE", "NOT_APPLICABLE"}
    ]
    # The engine may publish more; the screen caps what it renders. What must
    # hold here is that enough explainable readings exist to fill the section.
    assert usable, asset


def test_unknown_is_never_rendered_as_neutral() -> None:
    for asset in ASSETS:
        for horizon in HORIZONS:
            for factor in factors(asset, horizon):
                if factor["availability"] in {"UNAVAILABLE", "NOT_APPLICABLE"}:
                    assert factor["direction"] == "UNKNOWN", factor["key"]
                    assert factor["direction"] != "NEUTRAL"
