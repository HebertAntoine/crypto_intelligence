"""Un nom canonique par figure, et les chemins qui y mènent.

Trois moteurs peuvent voir la même chose et l'appeler « Head & Shoulders »,
« HEAD_SHOULDERS » ou « HS ». Comparer les chaînes brutes ferait passer un
accord pour un désaccord, et ce serait invisible: le compte de concordance
baisserait sans qu'aucune ligne de code n'ait tort.

Deux règles gouvernent ce module.

**La taxonomie des structures ne touche jamais celle des chandeliers.** Un
`DOUBLE_TOP` occupe des dizaines de barres, un `HAMMER` en occupe une. Les
ranger dans la même énumération inviterait à les compter ensemble, ce qui n'a
pas de sens. `is_candlestick_name()` existe pour que le mélange soit détectable
plutôt que silencieux.

**Deux moteurs de la même famille ne font pas deux validations.** Si notre
détecteur et un moteur externe cherchent tous deux des extrema locaux, leur
accord dit surtout qu'ils partagent une méthode — et leurs erreurs seront
corrélées. `MethodFamily` sert à ne pas confondre « deux avis » et « deux avis
indépendants ».
"""

from __future__ import annotations

from enum import StrEnum


class StructuralPatternName(StrEnum):
    """Les noms canoniques des structures chartistes."""

    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    TRIPLE_TOP = "TRIPLE_TOP"
    TRIPLE_BOTTOM = "TRIPLE_BOTTOM"
    HEAD_SHOULDERS = "HEAD_SHOULDERS"
    INVERSE_HEAD_SHOULDERS = "INVERSE_HEAD_SHOULDERS"
    ASCENDING_TRIANGLE = "ASCENDING_TRIANGLE"
    DESCENDING_TRIANGLE = "DESCENDING_TRIANGLE"
    SYMMETRICAL_TRIANGLE = "SYMMETRICAL_TRIANGLE"
    RISING_WEDGE = "RISING_WEDGE"
    FALLING_WEDGE = "FALLING_WEDGE"
    BULL_FLAG = "BULL_FLAG"
    BEAR_FLAG = "BEAR_FLAG"
    BULL_PENNANT = "BULL_PENNANT"
    BEAR_PENNANT = "BEAR_PENNANT"
    ASCENDING_CHANNEL = "ASCENDING_CHANNEL"
    DESCENDING_CHANNEL = "DESCENDING_CHANNEL"
    HORIZONTAL_CHANNEL = "HORIZONTAL_CHANNEL"
    CUP_HANDLE = "CUP_HANDLE"
    RECTANGLE_RANGE = "RECTANGLE_RANGE"
    ROUNDING_TOP = "ROUNDING_TOP"
    ROUNDING_BOTTOM = "ROUNDING_BOTTOM"


STRUCTURAL_PATTERNS = frozenset(name.value for name in StructuralPatternName)

#: Ce que NOTRE moteur produit aujourd'hui, vers le nom canonique.
#:
#: Douze des vingt-deux noms. Les dix absents — fanions, canaux, tasse avec
#: anse, rectangle, arrondis — ne sont pas détectés: la table dit donc aussi ce
#: qui manque.
OURS_TO_CANONICAL: dict[str, StructuralPatternName] = {
    "double_top": StructuralPatternName.DOUBLE_TOP,
    "double_bottom": StructuralPatternName.DOUBLE_BOTTOM,
    "triple_top": StructuralPatternName.TRIPLE_TOP,
    "triple_bottom": StructuralPatternName.TRIPLE_BOTTOM,
    "head_and_shoulders": StructuralPatternName.HEAD_SHOULDERS,
    "inverse_head_and_shoulders": StructuralPatternName.INVERSE_HEAD_SHOULDERS,
    "ascending_triangle": StructuralPatternName.ASCENDING_TRIANGLE,
    "descending_triangle": StructuralPatternName.DESCENDING_TRIANGLE,
    "symmetrical_triangle": StructuralPatternName.SYMMETRICAL_TRIANGLE,
    "rising_wedge": StructuralPatternName.RISING_WEDGE,
    "falling_wedge": StructuralPatternName.FALLING_WEDGE,
    "bull_flag": StructuralPatternName.BULL_FLAG,
    "bear_flag": StructuralPatternName.BEAR_FLAG,
}

#: Les vocabulaires étrangers rencontrés, vers le nom canonique.
#:
#: Écrit d'après les README et le code réellement lus, pas d'après ce qu'un
#: fournisseur « devrait » nommer. `M_Head` et `W_Bottom` viennent du modèle
#: FODUU; `IHS`, `DT`, `DB` du moteur de Tyson Cung.
ALIASES: dict[str, StructuralPatternName] = {
    "hs": StructuralPatternName.HEAD_SHOULDERS,
    "h&s": StructuralPatternName.HEAD_SHOULDERS,
    "head and shoulders": StructuralPatternName.HEAD_SHOULDERS,
    "head and shoulders top": StructuralPatternName.HEAD_SHOULDERS,
    "head_shoulders": StructuralPatternName.HEAD_SHOULDERS,
    "ihs": StructuralPatternName.INVERSE_HEAD_SHOULDERS,
    "inverse head and shoulders": StructuralPatternName.INVERSE_HEAD_SHOULDERS,
    "head and shoulders bottom": StructuralPatternName.INVERSE_HEAD_SHOULDERS,
    "inverse h&s": StructuralPatternName.INVERSE_HEAD_SHOULDERS,
    "dt": StructuralPatternName.DOUBLE_TOP,
    "m_head": StructuralPatternName.DOUBLE_TOP,
    "m head": StructuralPatternName.DOUBLE_TOP,
    "db": StructuralPatternName.DOUBLE_BOTTOM,
    "w_bottom": StructuralPatternName.DOUBLE_BOTTOM,
    "w bottom": StructuralPatternName.DOUBLE_BOTTOM,
    "channel up": StructuralPatternName.ASCENDING_CHANNEL,
    "channel down": StructuralPatternName.DESCENDING_CHANNEL,
    "channel": StructuralPatternName.HORIZONTAL_CHANNEL,
    "cup and handle": StructuralPatternName.CUP_HANDLE,
    "cup-and-handle": StructuralPatternName.CUP_HANDLE,
    "rectangle": StructuralPatternName.RECTANGLE_RANGE,
    "range": StructuralPatternName.RECTANGLE_RANGE,
    "triangle": StructuralPatternName.SYMMETRICAL_TRIANGLE,
    "pennant": StructuralPatternName.BULL_PENNANT,
}

#: Les noms de chandeliers, pour pouvoir REFUSER de les traiter ici.
#:
#: La liste est volontairement courte: il ne s'agit pas de couvrir toute la
#: littérature, mais d'attraper une confusion de taxonomie si elle survient.
_CANDLESTICK_MARKERS = frozenset({
    "doji", "hammer", "hanging_man", "hanging man", "marubozu", "spinning_top",
    "spinning top", "engulfing", "harami", "piercing", "dark_cloud",
    "dark cloud", "morning_star", "morning star", "evening_star",
    "evening star", "soldiers", "crows", "shooting_star", "shooting star",
})


def is_candlestick_name(raw: str) -> bool:
    """Ce nom appartient-il à l'autre taxonomie ?

    Sert à échouer bruyamment plutôt qu'à ranger un marteau parmi les
    structures.
    """
    lowered = raw.strip().lower().replace("-", "_")
    return any(marker in lowered for marker in _CANDLESTICK_MARKERS)


def canonical(raw: str) -> StructuralPatternName | None:
    """Le nom canonique d'une figure, ou rien.

    `None` plutôt qu'une supposition: un nom inconnu doit apparaître comme
    inconnu. Deviner ferait entrer silencieusement une figure mal identifiée
    dans une comparaison, et le désaccord qui en résulterait serait attribué au
    marché plutôt qu'à la table.

    Lève si le nom appartient à la taxonomie des chandeliers — c'est une erreur
    d'appel, pas une donnée manquante.
    """
    if not raw:
        return None
    if is_candlestick_name(raw):
        raise ValueError(
            f"'{raw}' is a candlestick pattern; the two taxonomies are separate "
            "and must not be resolved through the same table"
        )
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if key.upper() in STRUCTURAL_PATTERNS:
        return StructuralPatternName(key.upper())
    if key in OURS_TO_CANONICAL:
        return OURS_TO_CANONICAL[key]
    spaced = key.replace("_", " ")
    return ALIASES.get(key) or ALIASES.get(spaced)


class MethodFamily(StrEnum):
    """Comment un moteur trouve ses figures.

    Deux moteurs de la même famille se trompent de la même façon. Leur accord
    est donc une confirmation faible, et le compter comme deux avis
    indépendants surestimerait la confiance — exactement l'erreur qu'un
    consensus est censé éviter.
    """

    #: Pivots confirmés causalement, sur hauts et bas bruts. Le nôtre.
    CAUSAL_PIVOTS = "CAUSAL_PIVOTS"
    #: Extrema locaux sur une série lissée. Famille voisine de la précédente.
    SMOOTHED_EXTREMA = "SMOOTHED_EXTREMA"
    #: Droites ajustées par régression sur des points.
    LINE_REGRESSION = "LINE_REGRESSION"
    #: Régression à noyau puis appariement de formes — Lo, Mamaysky & Wang.
    KERNEL_SMOOTHING = "KERNEL_SMOOTHING"
    #: Reconnaissance d'image.
    VISION_MODEL = "VISION_MODEL"
    #: Règles sur les seules valeurs OHLC d'une à trois barres.
    CANDLE_RULES = "CANDLE_RULES"


#: Quelle famille pour quel moteur, d'après le code réellement lu.
METHOD_FAMILIES: dict[str, MethodFamily] = {
    "ours": MethodFamily.CAUSAL_PIVOTS,
    "tysoncung/crypto-chart-patterns": MethodFamily.SMOOTHED_EXTREMA,
    "michaelsboost/CandleEdge": MethodFamily.CANDLE_RULES,
    "przemyslawbak/OHLC_Candlestick_Patterns": MethodFamily.CANDLE_RULES,
    "zeta-zetra/chart_patterns": MethodFamily.CAUSAL_PIVOTS,
    "foduucom/stockmarket-pattern-detection-yolov8": MethodFamily.VISION_MODEL,
}
