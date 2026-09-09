"""Les figures de chandeliers, et pourquoi elles ne se mélangent pas au reste.

Deux vocabulaires cohabitent dans ce projet et ne doivent jamais se confondre.

`structure/patterns.py` décrit des **structures chartistes** : un double sommet
occupe des dizaines de barres, une tasse avec anse en occupe des centaines. Ce
module décrit des **figures de chandeliers** : un marteau tient en une barre,
une étoile du matin en trois.

Les mélanger produirait des absurdités mesurables. Un « taux de réussite »
agrégé sur des figures d'une barre et des figures de trois cents n'a aucun
sens, et une matrice de confusion qui compare un `HAMMER` à un `DOUBLE_TOP`
compare deux objets qui ne peuvent pas se substituer l'un à l'autre.

La séparation est donc structurelle — deux paquets, deux énumérations, deux
registres — et un test vérifie qu'aucun nom n'apparaît des deux côtés.

Une remarque qui gouverne tout le module : **la forme d'un chandelier ne suffit
pas à le nommer.** Un marteau et un pendu sont géométriquement identiques ;
seule la tendance qui précède les distingue. Le contexte fait partie de la
définition, pas de l'interprétation.
"""

from __future__ import annotations

from enum import StrEnum


class CandlestickFamily(StrEnum):
    """Ce que la figure est censée signaler, d'après la littérature."""

    BULLISH_REVERSAL = "BULLISH_REVERSAL"
    BEARISH_REVERSAL = "BEARISH_REVERSAL"
    BULLISH_CONTINUATION = "BULLISH_CONTINUATION"
    BEARISH_CONTINUATION = "BEARISH_CONTINUATION"
    #: Ni l'un ni l'autre : indécision. Un doji n'annonce rien par lui-même.
    INDECISION = "INDECISION"


class CandlestickPattern(StrEnum):
    """La taxonomie canonique des figures de chandeliers.

    Volontairement close et volontairement courte. Il existe des centaines de
    noms dans la littérature, dont beaucoup sont des variantes d'un même geste
    ou des définitions que deux auteurs écrivent différemment. Chaque entrée
    ici a une définition calculable sur l'OHLC, sans jugement.
    """

    # --- une barre ---------------------------------------------------------
    DOJI = "DOJI"
    DRAGONFLY_DOJI = "DRAGONFLY_DOJI"
    GRAVESTONE_DOJI = "GRAVESTONE_DOJI"
    HAMMER = "HAMMER"
    HANGING_MAN = "HANGING_MAN"
    INVERTED_HAMMER = "INVERTED_HAMMER"
    SHOOTING_STAR = "SHOOTING_STAR"
    MARUBOZU_BULLISH = "MARUBOZU_BULLISH"
    MARUBOZU_BEARISH = "MARUBOZU_BEARISH"
    SPINNING_TOP = "SPINNING_TOP"

    # --- deux barres -------------------------------------------------------
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    BULLISH_HARAMI = "BULLISH_HARAMI"
    BEARISH_HARAMI = "BEARISH_HARAMI"
    PIERCING_LINE = "PIERCING_LINE"
    DARK_CLOUD_COVER = "DARK_CLOUD_COVER"

    # --- trois barres ------------------------------------------------------
    MORNING_STAR = "MORNING_STAR"
    EVENING_STAR = "EVENING_STAR"
    THREE_WHITE_SOLDIERS = "THREE_WHITE_SOLDIERS"
    THREE_BLACK_CROWS = "THREE_BLACK_CROWS"


#: Combien de barres chaque figure occupe. Sert au dessin et au balayage: une
#: figure de trois barres ne peut pas être cherchée sur les deux premières.
PATTERN_BARS: dict[CandlestickPattern, int] = {
    CandlestickPattern.DOJI: 1,
    CandlestickPattern.DRAGONFLY_DOJI: 1,
    CandlestickPattern.GRAVESTONE_DOJI: 1,
    CandlestickPattern.HAMMER: 1,
    CandlestickPattern.HANGING_MAN: 1,
    CandlestickPattern.INVERTED_HAMMER: 1,
    CandlestickPattern.SHOOTING_STAR: 1,
    CandlestickPattern.MARUBOZU_BULLISH: 1,
    CandlestickPattern.MARUBOZU_BEARISH: 1,
    CandlestickPattern.SPINNING_TOP: 1,
    CandlestickPattern.BULLISH_ENGULFING: 2,
    CandlestickPattern.BEARISH_ENGULFING: 2,
    CandlestickPattern.BULLISH_HARAMI: 2,
    CandlestickPattern.BEARISH_HARAMI: 2,
    CandlestickPattern.PIERCING_LINE: 2,
    CandlestickPattern.DARK_CLOUD_COVER: 2,
    CandlestickPattern.MORNING_STAR: 3,
    CandlestickPattern.EVENING_STAR: 3,
    CandlestickPattern.THREE_WHITE_SOLDIERS: 3,
    CandlestickPattern.THREE_BLACK_CROWS: 3,
}

PATTERN_FAMILY: dict[CandlestickPattern, CandlestickFamily] = {
    CandlestickPattern.DOJI: CandlestickFamily.INDECISION,
    CandlestickPattern.SPINNING_TOP: CandlestickFamily.INDECISION,
    CandlestickPattern.DRAGONFLY_DOJI: CandlestickFamily.BULLISH_REVERSAL,
    CandlestickPattern.GRAVESTONE_DOJI: CandlestickFamily.BEARISH_REVERSAL,
    CandlestickPattern.HAMMER: CandlestickFamily.BULLISH_REVERSAL,
    CandlestickPattern.INVERTED_HAMMER: CandlestickFamily.BULLISH_REVERSAL,
    CandlestickPattern.HANGING_MAN: CandlestickFamily.BEARISH_REVERSAL,
    CandlestickPattern.SHOOTING_STAR: CandlestickFamily.BEARISH_REVERSAL,
    CandlestickPattern.MARUBOZU_BULLISH: CandlestickFamily.BULLISH_CONTINUATION,
    CandlestickPattern.MARUBOZU_BEARISH: CandlestickFamily.BEARISH_CONTINUATION,
    CandlestickPattern.BULLISH_ENGULFING: CandlestickFamily.BULLISH_REVERSAL,
    CandlestickPattern.BEARISH_ENGULFING: CandlestickFamily.BEARISH_REVERSAL,
    CandlestickPattern.BULLISH_HARAMI: CandlestickFamily.BULLISH_REVERSAL,
    CandlestickPattern.BEARISH_HARAMI: CandlestickFamily.BEARISH_REVERSAL,
    CandlestickPattern.PIERCING_LINE: CandlestickFamily.BULLISH_REVERSAL,
    CandlestickPattern.DARK_CLOUD_COVER: CandlestickFamily.BEARISH_REVERSAL,
    CandlestickPattern.MORNING_STAR: CandlestickFamily.BULLISH_REVERSAL,
    CandlestickPattern.EVENING_STAR: CandlestickFamily.BEARISH_REVERSAL,
    CandlestickPattern.THREE_WHITE_SOLDIERS: CandlestickFamily.BULLISH_CONTINUATION,
    CandlestickPattern.THREE_BLACK_CROWS: CandlestickFamily.BEARISH_CONTINUATION,
}

#: Les figures dont la définition exige une tendance préalable.
#:
#: C'est le point le plus mal compris de l'analyse en chandeliers. Un marteau
#: et un pendu ont EXACTEMENT la même forme; ce qui les distingue est ce qui
#: précède. Sans tendance mesurée, on ne peut pas nommer la figure — on peut
#: seulement décrire la bougie.
NEEDS_PRIOR_TREND: dict[CandlestickPattern, str] = {
    CandlestickPattern.HAMMER: "DOWN",
    CandlestickPattern.INVERTED_HAMMER: "DOWN",
    CandlestickPattern.HANGING_MAN: "UP",
    CandlestickPattern.SHOOTING_STAR: "UP",
    CandlestickPattern.MORNING_STAR: "DOWN",
    CandlestickPattern.EVENING_STAR: "UP",
    CandlestickPattern.PIERCING_LINE: "DOWN",
    CandlestickPattern.DARK_CLOUD_COVER: "UP",
    CandlestickPattern.BULLISH_ENGULFING: "DOWN",
    CandlestickPattern.BEARISH_ENGULFING: "UP",
    CandlestickPattern.BULLISH_HARAMI: "DOWN",
    CandlestickPattern.BEARISH_HARAMI: "UP",
}

#: Le sens que la théorie prête à chaque figure, +1 ou -1.
#:
#: Déclaré AVANT toute mesure et indépendamment d'elle. Sans cela, on serait
#: tenté de lire un rendement négatif après un marteau comme « la figure marche
#: dans l'autre sens » — c'est-à-dire de choisir l'hypothèse après avoir vu le
#: résultat. Zéro pour les figures d'indécision, qui n'annoncent pas de sens.
EXPECTED_DIRECTION: dict[CandlestickPattern, int] = {
    CandlestickPattern.DOJI: 0,
    CandlestickPattern.SPINNING_TOP: 0,
    CandlestickPattern.DRAGONFLY_DOJI: 1,
    CandlestickPattern.GRAVESTONE_DOJI: -1,
    CandlestickPattern.HAMMER: 1,
    CandlestickPattern.INVERTED_HAMMER: 1,
    CandlestickPattern.HANGING_MAN: -1,
    CandlestickPattern.SHOOTING_STAR: -1,
    CandlestickPattern.MARUBOZU_BULLISH: 1,
    CandlestickPattern.MARUBOZU_BEARISH: -1,
    CandlestickPattern.BULLISH_ENGULFING: 1,
    CandlestickPattern.BEARISH_ENGULFING: -1,
    CandlestickPattern.BULLISH_HARAMI: 1,
    CandlestickPattern.BEARISH_HARAMI: -1,
    CandlestickPattern.PIERCING_LINE: 1,
    CandlestickPattern.DARK_CLOUD_COVER: -1,
    CandlestickPattern.MORNING_STAR: 1,
    CandlestickPattern.EVENING_STAR: -1,
    CandlestickPattern.THREE_WHITE_SOLDIERS: 1,
    CandlestickPattern.THREE_BLACK_CROWS: -1,
}

#: Ce que ce module a le droit d'influencer.
#:
#: `DESCRIPTIVE_ONLY` est une **conclusion mesurée**, pas une précaution de
#: principe: la PHASE 37B a produit 216 dossiers, 1 040 tests, zéro avantage
#: démontré, et 87 signes sur 116 qui s'inversent hors échantillon.
#:
#: Ces figures peuvent donc être affichées et stockées. Elles ne doivent
#: toucher ni un sens d'achat ou de vente, ni un timing, ni un score
#: d'opportunité, ni une conviction directionnelle. Un test de garde échoue si
#: un module de décision importe ce paquet — la contrainte vit dans la suite de
#: tests, pas seulement dans ce commentaire.
USAGE = "DESCRIPTIVE_ONLY"

#: Ce que la mesure a réellement établi, pour que la raison voyage avec la
#: contrainte et ne se perde pas au prochain refactor.
USAGE_EVIDENCE = (
    "PHASE 37B, candlestick_v1: 216 dossiers, 1 040 tests, 0 POSITIVE_EDGE, "
    "0 NEGATIVE_EDGE, 1 seul test survivant au FDR global sur un échantillon "
    "trop mince pour compter, et 87 signes sur 116 qui s'inversent entre "
    "fenêtres chronologiques."
)

#: Version des règles, comme pour les détecteurs structurels.
#:
#: **Gelée pour la phase de validation.** Mesurer v1 telle quelle, puis
#: seulement envisager une v2: régler les seuils sur les résultats observés
#: reviendrait à choisir la définition qui donne le meilleur chiffre.
DETECTOR_VERSION = "candlestick_v1"
