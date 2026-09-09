"""La taxonomie canonique, et les deux confusions qu'elle empeche.

**Comparer des chaines.** Trois moteurs peuvent voir la meme chose et
l'appeler « Head & Shoulders », « HEAD_SHOULDERS » ou « HS ». Comparer les noms
bruts ferait passer un accord pour un desaccord, et le compte de concordance
baisserait sans qu'aucune ligne de code n'ait tort.

**Melanger les deux familles.** Un HAMMER n'est pas une structure chartiste.
Le resoudre par la meme table le ferait entrer silencieusement dans une
comparaison de figures.
"""

from __future__ import annotations

import pytest

from crypto_intel.pattern_learning import (
    METHOD_FAMILIES,
    SOURCES,
    STRUCTURAL_PATTERNS,
    LicenceStatus,
    MethodFamily,
    StructuralPatternName,
    canonical,
    is_candlestick_name,
)
from crypto_intel.pattern_learning.ontology import ALIASES, OURS_TO_CANONICAL


class TestTheTaxonomyIsComplete:
    def test_it_covers_the_twenty_two_requested_names(self):
        assert len(STRUCTURAL_PATTERNS) == 22

    def test_every_name_our_engine_produces_maps_somewhere(self):
        from crypto_intel.structure.patterns import PATTERN_CLASSES

        # Les cles de registre (« triangle », « wedge », « flag ») ne sont pas
        # des noms de figures: seules les figures emises comptent.
        emitted = {
            name for name in PATTERN_CLASSES
            if name not in ("triangle", "wedge", "flag")
        }
        unmapped = {name for name in emitted if canonical(name) is None}
        assert not unmapped, f"noms produits sans equivalent canonique: {unmapped}"

    def test_every_alias_resolves_to_a_real_canonical_name(self):
        for alias, target in ALIASES.items():
            assert target.value in STRUCTURAL_PATTERNS, alias

    def test_ours_maps_only_to_real_names(self):
        for name, target in OURS_TO_CANONICAL.items():
            assert target.value in STRUCTURAL_PATTERNS, name


class TestNamesAreResolvedNotCompared:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("double_top", StructuralPatternName.DOUBLE_TOP),
            ("DOUBLE_TOP", StructuralPatternName.DOUBLE_TOP),
            ("M_Head", StructuralPatternName.DOUBLE_TOP),
            ("W_Bottom", StructuralPatternName.DOUBLE_BOTTOM),
            ("H&S", StructuralPatternName.HEAD_SHOULDERS),
            ("Head and Shoulders Bottom", StructuralPatternName.INVERSE_HEAD_SHOULDERS),
            ("IHS", StructuralPatternName.INVERSE_HEAD_SHOULDERS),
            ("Channel Up", StructuralPatternName.ASCENDING_CHANNEL),
            ("cup-and-handle", StructuralPatternName.CUP_HANDLE),
        ],
    )
    def test_foreign_vocabularies_land_on_the_same_name(self, raw, expected):
        assert canonical(raw) == expected

    def test_an_unknown_name_returns_nothing_rather_than_a_guess(self):
        """Deviner ferait entrer une figure mal identifiee dans une
        comparaison, et le desaccord serait attribue au marche."""
        assert canonical("wolfe_wave") is None
        assert canonical("") is None


class TestTheTwoTaxonomiesStaySeparate:
    @pytest.mark.parametrize(
        "raw",
        ["hammer", "HAMMER", "morning_star", "Three Black Crows",
         "bullish_engulfing", "dark cloud cover", "spinning top"],
    )
    def test_candlestick_names_are_recognised_as_such(self, raw):
        assert is_candlestick_name(raw)

    @pytest.mark.parametrize(
        "raw", ["double_top", "symmetrical_triangle", "cup_handle", "bull_flag"]
    )
    def test_structural_names_are_not_mistaken_for_candlesticks(self, raw):
        assert not is_candlestick_name(raw)

    def test_resolving_a_candlestick_here_raises_rather_than_returns_none(self):
        """Une erreur d'appel, pas une donnee manquante: renvoyer None
        laisserait croire a un nom inconnu au lieu d'un melange de taxonomies."""
        with pytest.raises(ValueError, match="candlestick"):
            canonical("hammer")

    def test_no_candlestick_name_is_in_the_structural_enum(self):
        for name in STRUCTURAL_PATTERNS:
            assert not is_candlestick_name(name)


class TestNoFalseIndependence:
    """Deux moteurs de la meme famille ne font pas deux validations."""

    def test_our_engine_declares_its_family(self):
        assert METHOD_FAMILIES["ours"] is MethodFamily.CAUSAL_PIVOTS

    def test_every_registered_engine_declares_a_family(self):
        for source in SOURCES.values():
            if source.kind.value in ("RULE_ENGINE", "PRETRAINED_MODEL"):
                assert source.method_family is not None, source.id

    def test_the_only_usable_engine_is_in_a_neighbouring_family(self):
        """Fait mesure, pas suppose: son code utilise argrelextrema sur une
        moyenne mobile, le notre des pivots confirmes causalement. Son accord
        est donc une confirmation FAIBLE."""
        source = SOURCES["tysoncung_crypto_chart_patterns"]
        assert source.status is LicenceStatus.TRAIN_ALLOWED
        assert source.method_family is MethodFamily.SMOOTHED_EXTREMA
        assert any("corrélées" in c or "FAIBLE" in c for c in source.caveats)


class TestTheRegistryRefusesByDefault:
    def test_every_source_carries_its_licence_evidence(self):
        for source in SOURCES.values():
            assert source.licence_evidence, f"{source.id} sans preuve de licence"

    def test_an_unverified_licence_can_never_be_usable(self):
        """Un depot public n'est pas un depot libre."""
        for source in SOURCES.values():
            if not source.licence_verified:
                assert source.status is LicenceStatus.BLOCKED_PENDING_LICENSE, (
                    f"{source.id}: licence non verifiee mais statut "
                    f"{source.status.value}"
                )

    def test_a_source_without_a_licence_is_blocked(self):
        blocked = SOURCES["zeta_zetra_chart_patterns"]
        assert blocked.licence == "AUCUNE"
        assert blocked.status is LicenceStatus.BLOCKED_PENDING_LICENSE
        assert not blocked.usable

    def test_the_agpl_risk_is_recorded_beyond_its_own_source(self):
        """Le point depasse la source: il contraint notre propre modele."""
        model = SOURCES["foduu_yolov8_stockmarket"]
        assert model.status is LicenceStatus.BLOCKED_PENDING_LICENSE
        assert any("NOTRE modèle" in c for c in model.caveats)

    def test_exactly_one_source_may_be_used_for_comparison_today(self):
        allowed = [
            s for s in SOURCES.values()
            if s.status is LicenceStatus.TRAIN_ALLOWED
        ]
        assert len(allowed) == 1, (
            "si ce compte change, le plan de consensus change avec lui: "
            f"{[s.id for s in allowed]}"
        )
