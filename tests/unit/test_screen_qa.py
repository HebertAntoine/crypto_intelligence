"""Une revue statique des huit écrans, faute de pouvoir les regarder tourner.

Je ne peux pas voir l'application s'exécuter, et prétendre l'avoir validée
visuellement serait faux. Ce que je peux faire est vérifier, sur la source de
chaque écran, les propriétés qui ont réellement cassé par le passé :

  * un identifiant technique affiché tel quel (« Régime strongly bullish ») ;
  * une phrase anglaise de domaine restée dans l'interface ;
  * un écran sans état vide ni état d'erreur, qui affiche une page blanche
    quand l'appel échoue ;
  * un bouton décoratif, câblé sur rien.

Le contrôle porte sur les chaînes réellement destinées à l'écran — arguments
de `Text(...)` et paramètres nommés d'affichage — et non sur toute la source :
les clés JSON et les identifiants de moteur sont du vocabulaire interne et
doivent y rester.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_LIB = Path(__file__).resolve().parents[2] / "app" / "lib"
SCREENS = {
    "Aujourd'hui": "screens/today_screen.dart",
    "Marchés": "screens/markets_screen.dart",
    "Graphique": "screens/chart_screen.dart",
    "Rapport": "screens/report_screen.dart",
    "Preuves": "screens/evidence_screen.dart",
    "Recherche": "screens/research_screen.dart",
    "Connaissances": "screens/knowledge_screen.dart",
}
# La page « pourquoi » est un panneau de l'écran Aujourd'hui plutôt qu'un
# écran séparé; ses blocs vivent dans les mêmes fichiers.
SHARED = {
    "Blocs Aujourd'hui": "widgets/today_blocks.dart",
    "Diagnostic": "diagnostics/today_diagnostics.dart",
}
# La table de traduction est contrôlée à part: y chercher des identifiants
# bruts signalerait chacune de ses clés, qui sont précisément des identifiants.
LABEL_TABLE = "presentation/domain_labels.dart"

RAW_ENUM = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
LONE_ENUMS = {
    "UNCLEAR", "UNDETERMINED", "REINTEGRATION", "BREAKOUT", "FAKEOUT",
    "BULLISH", "BEARISH", "NEUTRAL",
}
ALLOWED = {
    "BTC", "ETH", "SOL", "ETF", "RSI", "ATR", "MFE", "MAE", "DVOL", "FOMC",
    "CPI", "PCE", "USD", "EUR", "OHLCV", "FDR", "PIB", "PMI", "MACD", "EMA",
    "ADX", "OI", "API", "URL", "JSON",
}
ENGLISH = re.compile(
    r"\b(price is|is near|range top|range bottom|zone quality|bar\(s\)|"
    r"would break|close above|close below|the current|structure is|"
    r"strongly bullish|strongly bearish|no measurable|insufficient data|"
    r"not available|loading|retry|unknown)\b",
    re.IGNORECASE,
)

# Les chaînes qui atteignent l'écran: arguments de Text(...) et paramètres
# nommés d'affichage. `_STRING` accepte les deux guillemets et l'échappement.
_STRING = r"""(?:'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)")"""
_DISPLAY = re.compile(
    r"(?:Text\(\s*|(?:label|title|value|hint|tooltip|semanticLabel|text|"
    r"headline|what|message)\s*:\s*)" + _STRING
)


def _source(relative: str) -> str:
    return (APP_LIB / relative).read_text(encoding="utf-8")


def _displayed_strings(source: str) -> list[str]:
    out: list[str] = []
    for match in _DISPLAY.finditer(source):
        text = match.group(1) if match.group(1) is not None else match.group(2)
        if text and any(character.isalpha() for character in text):
            out.append(text)
    return out


@pytest.fixture(scope="module", params=sorted(SCREENS | SHARED))
def screen(request):
    name = request.param
    return name, _source((SCREENS | SHARED)[name])


def test_the_display_string_reader_actually_reads_something():
    """Sans ce contrôle, une regex cassée ferait passer toute la revue.

    Un extracteur qui ne trouve plus rien rend chaque assertion de contenu
    vraie par vacuité, et la revue continuerait à s'annoncer verte.
    """
    counts = {
        name: len(_displayed_strings(_source(path)))
        for name, path in (SCREENS | SHARED).items()
    }
    empty = [name for name, count in counts.items() if count < 5]
    assert not empty, f"aucune chaîne affichée trouvée dans: {empty} ({counts})"


def test_the_label_table_covers_every_structural_location():
    """Neuf états, neuf traductions.

    Le repli rend lisible sans traduire, donc un état oublié ne casse rien de
    visible et sort en anglais approximatif. C'est exactement ainsi que la
    table backend a laissé passer `AT_RANGE_TOP` en gardant six entrées pour
    une énumération de neuf.
    """
    source = _source(LABEL_TABLE)
    block = source[source.index("String locationLabel"):]
    block = block[: block.index("_ => readableFallback")]
    for state in (
        "AT_RANGE_TOP", "NEAR_RANGE_TOP", "UPPER_THIRD", "MID_RANGE",
        "LOWER_THIRD", "NEAR_RANGE_BOTTOM", "AT_RANGE_BOTTOM",
        "ABOVE_RANGE", "BELOW_RANGE", "NO_VALID_RANGE",
    ):
        assert state in block, f"{state} n'a pas de traduction et sortirait brut"


def test_the_label_table_translates_identifiers_into_french():
    """Les clés sont des identifiants; les valeurs ne doivent plus en être."""
    source = _source(LABEL_TABLE)
    values = re.findall(
        r"""['"][A-Z][A-Z0-9_]+['"](?:\s*\|\|\s*['"][A-Z0-9_]+['"])*"""
        r"""\s*=>\s*""" + _STRING,
        source,
    )
    translated = [
        first if first is not None else second for first, second in values
    ]
    assert translated, "aucune paire identifiant → libellé trouvée"
    offenders = [
        text for text in translated
        if RAW_ENUM.search(text) or ENGLISH.search(text)
    ]
    assert not offenders, f"libellés non traduits: {offenders[:5]}"


def test_every_screen_file_exists():
    missing = [
        name for name, path in (SCREENS | SHARED).items()
        if not (APP_LIB / path).exists()
    ]
    assert not missing, f"écrans introuvables: {missing}"


def test_no_raw_identifier_is_displayed(screen):
    name, source = screen
    offenders = []
    for text in _displayed_strings(source):
        for token in RAW_ENUM.findall(text):
            if token not in ALLOWED:
                offenders.append(f"{token!r} dans {text[:60]!r}")
        for token in re.findall(r"\b[A-Z]{4,}\b", text):
            if token in LONE_ENUMS:
                offenders.append(f"{token!r} dans {text[:60]!r}")
    assert not offenders, f"{name}: identifiants bruts affichés:\n" + "\n".join(
        offenders
    )


def test_no_english_domain_sentence_is_displayed(screen):
    name, source = screen
    offenders = [
        text[:80] for text in _displayed_strings(source) if ENGLISH.search(text)
    ]
    assert not offenders, f"{name}: phrases anglaises affichées:\n" + "\n".join(
        offenders
    )


@pytest.mark.parametrize("name", sorted(SCREENS))
def test_every_screen_handles_failure_and_emptiness(name):
    """Un écran sans état d'erreur affiche une page blanche quand l'appel casse."""
    source = _source(SCREENS[name])
    assert "ErrorView" in source or "onRetry" in source, (
        f"{name}: aucun état d'erreur, l'échec d'un appel ne serait pas dit"
    )
    assert "LoadingView" in source or "ConnectionState.waiting" in source, (
        f"{name}: aucun état de chargement"
    )
    assert re.search(r"isEmpty|findsNothing|SizedBox\.shrink|Indisponible", source), (
        f"{name}: aucun état vide, une liste vide s'afficherait sans explication"
    )


@pytest.mark.parametrize("name", sorted(SCREENS))
def test_no_decorative_button(name):
    """Un bouton câblé sur rien promet une action qui n'existe pas."""
    source = _source(SCREENS[name])
    dead = re.findall(r"on(?:Pressed|Tap)\s*:\s*\(\s*\)\s*\{\s*\}", source)
    assert not dead, f"{name}: {len(dead)} bouton(s) sans action"


def test_the_today_screen_carries_the_analysis_identity():
    """L'identifiant est conservé côté client, même s'il n'est pas affiché."""
    models = _source("api/models.dart")
    assert "analysisId" in models
    assert "isCoherent" in models, (
        "rien ne détecte deux blocs décrivant des instants différents"
    )
    today = _source("screens/today_screen.dart")
    assert "AnalysisMismatchBanner" in today, (
        "un désaccord d'identifiant serait combiné silencieusement"
    )


def test_the_page_blocks_read_the_backend_rather_than_deciding():
    """Aucune décision dans Flutter: la page présente, le backend calcule."""
    blocks = _source("widgets/today_blocks.dart")
    # Un seuil numérique de décision dans la vue signifierait que l'écran
    # tranche à la place du moteur.
    forbidden = re.findall(
        r"(?:score|pressure|uncertainty|drift)\w*\s*[<>]=?\s*\d", blocks
    )
    assert not forbidden, f"seuils de décision dans la vue: {forbidden}"


def test_freshness_is_recomputed_against_the_clock_not_read_from_the_payload():
    """Une fraîcheur figée dans un instantané se présente comme actuelle."""
    assert (APP_LIB / "api" / "freshness.dart").exists()
    freshness = _source("api/freshness.dart")
    assert "deriveFreshness" in freshness


def test_the_client_freshness_thresholds_match_the_backend_config():
    """Deux couches jugent l'âge; une seule vérité doit les gouverner.

    Le client mesure la fraîcheur contre sa propre horloge — un instantané
    embarqué fige « FRESH » à l'export et l'app le lirait encore des heures
    plus tard. Il porte donc ses propres constantes, et rien n'empêchait
    jusqu'ici qu'elles s'écartent silencieusement du fichier de seuils.
    """
    import re

    from crypto_intel.config_loader import threshold

    backend = threshold("analysis_freshness", default={}) or {}
    models = _source("api/models.dart")
    client = {
        name: int(re.search(rf"{name} = (\d+);", models).group(1))
        for name in ("freshSeconds", "agingSeconds", "staleSeconds")
    }
    assert client["freshSeconds"] == backend["fresh_seconds"]
    assert client["agingSeconds"] == backend["aging_seconds"]
    assert client["staleSeconds"] == backend["stale_seconds"]


def test_the_client_never_composes_a_pressure_verdict():
    """Le libellé d'intensité vient du moteur; l'écran ne le fabrique pas.

    Un seuil recopié dans un widget finit toujours par contredire le moteur:
    c'est ainsi que « +30/100 · 4/5 · Forte » se lisait « forte pression ».
    L'écran reçoit `label` et l'affiche tel quel.
    """
    for name in ("widgets/today_blocks.dart", "screens/today_screen.dart"):
        source = _source(name)
        for forbidden in (
            "'FORTE PRESSION", '"FORTE PRESSION',
            "'PRESSION ACHETEUSE", '"PRESSION ACHETEUSE',
            "'PRESSION VENDEUSE", '"PRESSION VENDEUSE',
            "'ACHETEURS DOMINANTS", "'VENDEURS DOMINANTS",
        ):
            assert forbidden not in source, (
                f"{name}: le verdict de pression est composé dans la vue "
                f"({forbidden!r})"
            )


def test_the_coverage_words_never_qualify_an_intensity():
    """« Bonne », « Partielle » décrivent la couverture, jamais la pression."""
    source = _source("screens/today_screen.dart")
    # Le badge doit porter le mot « couverture » avec l'adjectif, sans quoi
    # « Bonne » seul se lit comme une force de pression.
    assert "'Couverture '" in source or "Couverture $" in source or (
        "'Couverture ${" in source
    ), "l'adjectif de couverture s'affiche sans être nommé comme tel"
