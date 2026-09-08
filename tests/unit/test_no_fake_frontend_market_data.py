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
    """Sans bougies, le graphique le dit; il n'en fabrique pas.

    Le message d'état vide a suivi le moteur de rendu quand il a quitté
    l'écran pour `chart/candle_chart.dart`. La propriété est la même — un jeu
    vide produit une phrase, jamais une courbe — mais elle se vérifie
    désormais là où le dessin a lieu.
    """
    sources = {
        name: (APP_LIB / name).read_text(encoding="utf-8")
        for name in (
            "screens/chart_screen.dart",
            "chart/candle_chart.dart",
            "chart/chart_viewport.dart",
        )
    }
    for name, text in sources.items():
        assert "_syntheticCandle" not in text, name
        assert "_chartValues" not in text, name

    painter = sources["chart/candle_chart.dart"]
    assert "Aucune bougie disponible" in painter, (
        "le peintre ne dit pas explicitement qu'il n'a rien à dessiner"
    )
    # Et il sort avant de peindre quoi que ce soit.
    assert "if (viewport.isEmpty)" in painter

    viewport = sources["chart/chart_viewport.dart"]
    # Une fenêtre vide ne fabrique aucune bougie de remplacement.
    assert "isEmpty ? const [] :" in viewport


def test_the_chart_scale_is_computed_on_the_visible_window_only():
    """L'échelle verticale ne doit plus venir de tout le jeu de données.

    L'ancien peintre prenait le minimum et le maximum de **toutes** les
    bougies: un pic vieux de plusieurs années écrasait soixante bougies
    récentes contre le bas du cadre, et il n'existait aucune fenêtre à
    déplacer.
    """
    viewport = _source_or_none("chart/chart_viewport.dart")
    assert viewport is not None, "le repère temps/prix est absent"
    # Les extrêmes se lisent sur `visible`, pas sur `candles`.
    assert "visible.map((c) => c.low)" in viewport
    assert "candles.map((c) => c.low)" not in viewport

    screen = (APP_LIB / "screens" / "chart_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "reduce(math.min)" not in screen, (
        "l'écran calcule encore une échelle sur l'ensemble des bougies"
    )


def _source_or_none(relative: str) -> str | None:
    path = APP_LIB / relative
    return path.read_text(encoding="utf-8") if path.exists() else None


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
        # Importer le module est un accès; le nommer dans un commentaire n'en
        # est pas un. Le filtre précédent se déclenchait sur de la prose.
        imports_fixtures = (
            "from .providers import fixtures" in text
            or "from ..providers import fixtures" in text
            or "from .providers.fixtures import" in text
            or "from ..providers.fixtures import" in text
            or "import providers.fixtures" in text
        )
        if imports_fixtures and path != fixtures:
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


def test_vercel_config_matches_the_schema_it_declares():
    """An unknown key fails the deployment, not the app - so it fails silently here.

    A `_comment` key added to a header rule to explain the cache policy was
    rejected by Vercel's schema validation and broke the build. Nothing in the
    repository catches that, because the config is never exercised locally.
    """
    import json

    allowed_rule = {"source", "headers", "has", "missing"}
    allowed_header = {"key", "value"}
    allowed_rewrite = {"source", "destination", "has", "missing", "statusCode"}

    root = Path(__file__).resolve().parents[2]
    for name in ("vercel.json", "app/vercel.json"):
        path = root / name
        if not path.exists():
            continue
        config = json.loads(path.read_text(encoding="utf-8"))

        for rule in config.get("headers", []):
            extra = set(rule) - allowed_rule
            assert not extra, f"{name}: header rule carries {extra}"
            for header in rule.get("headers", []):
                extra = set(header) - allowed_header
                assert not extra, f"{name}: header entry carries {extra}"

        for rewrite in config.get("rewrites", []):
            extra = set(rewrite) - allowed_rewrite
            assert not extra, f"{name}: rewrite carries {extra}"


def test_french_ui_shows_no_english_labels():
    """Les enums restent anglais en interne; l'écran ne doit pas les montrer.

    Ce garde-fou est statique parce que les sections concernées vivent dans un
    ListView paresseux: un test widget ne les construit pas, et passerait donc
    sans rien vérifier.
    """
    today_screen = (APP_LIB / "screens" / "today_screen.dart").read_text(
        encoding="utf-8"
    )
    for english in ("'Drivers'", "'Caveats'"):
        assert english not in today_screen, (
            f"{english} est affiché tel quel dans l'UI française"
        )
    for french in ("Facteurs principaux", "Points de vigilance"):
        assert french in today_screen, f"{french} manque"

    diagnostics = (APP_LIB / "diagnostics" / "today_diagnostics.dart").read_text(
        encoding="utf-8"
    )
    # Le panneau affichait STRONGLY_BULLISH brut avant d'être traduit.
    assert "directionLabel(direction)" in diagnostics


def test_family_freshness_is_recomputed_never_read_from_the_payload():
    """Le champ `freshness` d'une famille est figé à l'export du snapshot.

    Le défaut observé: « instantané embarqué, backend injoignable » affiché
    au-dessus de « Prix : À JOUR · il y a 1 s ». Les deux venaient du même
    payload, dont le bloc families portait age_seconds=0.5 gelé à la capture.
    """
    models = (APP_LIB / "api" / "models.dart").read_text(encoding="utf-8")
    assert "DerivedFreshness derived({DateTime? now})" in models
    assert "bool usableNow({DateTime? now})" in models

    for name in ("screens/today_screen.dart", "diagnostics/today_diagnostics.dart"):
        text = (APP_LIB / name).read_text(encoding="utf-8")
        assert "state.ageSeconds!" not in text, (
            f"{name} affiche l'âge exporté au lieu de le recalculer"
        )
        assert "freshnessLabel(state.freshness)" not in text, (
            f"{name} affiche la fraîcheur figée du payload"
        )


def test_the_official_logos_are_bundled_and_declared():
    """Les trois PNG doivent exister et être déclarés, sinon le tracé reprend.

    `CryptoLogo` retombe silencieusement sur son tracé vectoriel quand un
    fichier manque: rien ne casse, et personne ne remarque que le logo
    officiel n'est pas affiché.
    """
    root = Path(__file__).resolve().parents[2]
    logos = root / "app" / "assets" / "logos"

    for name in ("btc", "eth", "sol"):
        path = logos / f"{name}.png"
        assert path.exists(), f"{name}.png absent"
        header = path.read_bytes()[:8]
        assert header == b"\x89PNG\r\n\x1a\n", f"{name}.png n'est pas un PNG"

    pubspec = (root / "app" / "pubspec.yaml").read_text(encoding="utf-8")
    assert "- assets/logos/" in pubspec, "le dossier n'est pas embarqué"

    widget = (
        root / "app" / "lib" / "widgets" / "mobile_kit.dart"
    ).read_text(encoding="utf-8")
    assert "assets/logos/${asset.toLowerCase()}.png" in widget
    # Le repli doit rester: un fichier retiré ne doit jamais laisser un vide.
    assert "errorBuilder:" in widget


def test_only_one_widget_renders_an_asset_logo():
    """Un second rendu privé est ce qui a laissé « Aujourd'hui » en arrière.

    `today_screen.dart` avait sa propre classe `_CryptoLogo` avec ses propres
    tracés vectoriels. Les fichiers PNG ont été branchés sur le widget partagé,
    et l'écran principal a continué d'afficher les dessins sans que rien ne
    signale l'écart.
    """
    root = Path(__file__).resolve().parents[2]
    lib = root / "app" / "lib"

    definitions: list[str] = []
    for path in lib.rglob("*.dart"):
        text = path.read_text(encoding="utf-8")
        for marker in ("class CryptoLogo", "class _CryptoLogo"):
            if marker in text:
                definitions.append(f"{path.relative_to(lib)}:{marker}")

    assert definitions == ["widgets/mobile_kit.dart:class CryptoLogo"], (
        "plusieurs widgets rendent un logo: " + ", ".join(definitions)
    )

    # Les tracés vectoriels ne vivent qu'à côté du widget partagé, en repli.
    for name in ("_EthPainter", "_SolPainter"):
        holders = [
            str(path.relative_to(lib))
            for path in lib.rglob("*.dart")
            if f"class {name}" in path.read_text(encoding="utf-8")
        ]
        assert holders in ([], ["widgets/mobile_kit.dart"]), (
            f"{name} défini ailleurs que dans le kit partagé: {holders}"
        )
