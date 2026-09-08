"""Every engine identifier, once, in French.

Engines reason in English enums and that is right: an enum is an identifier,
not a sentence. The defect was that identifiers travelled all the way to the
screen — "Régime strongly bullish", "4h price is near range top",
"edge séparé: NOT_YET_TESTED".

Translating at the point of display would mean translating in several places
and forgetting one, which is exactly what happened: the location table existed
but was missing four of its nine states, so `AT_RANGE_TOP` reached a user
verbatim while `NEAR_RANGE_TOP` did not. One table per vocabulary, read by
every producer of user-facing text, makes that failure impossible to repeat
silently — a missing key is now missing for everyone at once.

Grammatical gender is the reason some vocabularies appear twice: a *direction*
is feminine and a *régime* is masculine, so "haussière" and "haussier" are two
tables and not one lookup with a wrong ending.
"""

from __future__ import annotations

REGIME_FR: dict[str, str] = {
    "STRONGLY_BULLISH": "fortement haussier",
    "BULLISH": "haussier",
    "NEUTRAL": "neutre",
    "BEARISH": "baissier",
    "STRONGLY_BEARISH": "fortement baissier",
    "UNDETERMINED": "indéterminé",
}

DIRECTION_FR: dict[str, str] = {
    "STRONGLY_BULLISH": "FORTEMENT HAUSSIÈRE",
    "BULLISH": "HAUSSIÈRE",
    "NEUTRAL": "SANS DIRECTION NETTE",
    "BEARISH": "BAISSIÈRE",
    "STRONGLY_BEARISH": "FORTEMENT BAISSIÈRE",
    "UNDETERMINED": "INDÉTERMINÉE",
}

TIMING_FR: dict[str, str] = {
    "STRONG_OPPORTUNITY": "OPPORTUNITÉ FORTE",
    "OPPORTUNITY": "OPPORTUNITÉ",
    "WATCH": "À SURVEILLER",
    "WAIT": "ATTENDRE",
    "UNFAVORABLE": "DÉFAVORABLE",
    "INSUFFICIENT_DATA": "DONNÉES INSUFFISANTES",
}

# "Tested and nothing survived" and "never tested" are different answers, and
# collapsing them would let an untested asset borrow the credibility of a
# completed negative result.
EDGE_FR: dict[str, str] = {
    "POSITIVE_EDGE": "AVANTAGE DÉMONTRÉ",
    "NEGATIVE_EDGE": "RELATION INVERSE DÉMONTRÉE",
    "NO_MEASURABLE_EDGE": "AUCUN AVANTAGE DÉMONTRÉ",
    "INSUFFICIENT_DATA": "AUCUNE RELATION TESTÉE",
}

# Nine states, all nine present. This table is the one that leaked.
LOCATION_FR: dict[str, str] = {
    "AT_RANGE_BOTTOM": "sur le bas de son range",
    "NEAR_RANGE_BOTTOM": "proche du bas de son range",
    "LOWER_THIRD": "dans le tiers bas de son range",
    "MID_RANGE": "au milieu de son range",
    "UPPER_THIRD": "dans le tiers haut de son range",
    "NEAR_RANGE_TOP": "proche du haut de son range",
    "AT_RANGE_TOP": "sur le haut de son range",
    "ABOVE_RANGE": "au-dessus de son range",
    "BELOW_RANGE": "sous son range",
    "NO_VALID_RANGE": "sans range validé",
}

# The same nine states as a headline rather than inside a sentence.
LOCATION_TITLE_FR: dict[str, str] = {
    "AT_RANGE_BOTTOM": "Sur le bas du range",
    "NEAR_RANGE_BOTTOM": "Proche du bas du range",
    "LOWER_THIRD": "Dans le tiers bas du range",
    "MID_RANGE": "Au milieu du range",
    "UPPER_THIRD": "Dans le tiers haut du range",
    "NEAR_RANGE_TOP": "Proche du haut du range",
    "AT_RANGE_TOP": "Sur le haut du range",
    "ABOVE_RANGE": "Au-dessus du range",
    "BELOW_RANGE": "Sous le range",
    "NO_VALID_RANGE": "Aucun range validé",
}

STRUCTURE_FR: dict[str, str] = {
    "BULLISH_STRUCTURE": "Haussière",
    "BEARISH_STRUCTURE": "Baissière",
    "RANGE_STRUCTURE": "En range",
    "UNCLEAR": "Pas encore lisible",
    "UNDETERMINED": "Indéterminée",
}

STRUCTURE_SENTENCE_FR: dict[str, str] = {
    "BULLISH_STRUCTURE": "haussière",
    "BEARISH_STRUCTURE": "baissière",
    "RANGE_STRUCTURE": "en range",
    "UNCLEAR": "pas encore lisible",
    "UNDETERMINED": "indéterminée",
}

VOLATILITY_FR: dict[str, str] = {
    "VERY_LOW": "Très faible", "LOW": "Faible", "NORMAL": "Normale",
    "HIGH": "Élevée", "VERY_HIGH": "Extrême", "UNKNOWN": "Inconnue",
}

VOLATILITY_SENTENCE_FR: dict[str, str] = {
    "VERY_LOW": "très faible", "LOW": "faible", "NORMAL": "normale",
    "HIGH": "élevée", "VERY_HIGH": "extrême", "UNKNOWN": "inconnue",
}

PRICING_FR: dict[str, str] = {
    "EXPENSIVE": "chère", "SLIGHTLY_EXPENSIVE": "un peu chère", "FAIR": "normale",
    "SLIGHTLY_CHEAP": "un peu bon marché", "CHEAP": "bon marché",
    "UNKNOWN": "non évaluée",
}

CROWDING_FR: dict[str, str] = {
    "LOW": "Faible", "NORMAL": "Normal", "ELEVATED": "Élevé",
    "EXTREME": "Extrême", "UNKNOWN": "Inconnu",
}

FUNDING_BAND_FR: dict[str, str] = {
    "EXTREME_NEGATIVE": "Nettement négatif", "NEGATIVE": "Plutôt faible",
    "NEUTRAL": "Dans la norme", "POSITIVE": "Plutôt élevé",
    "EXTREME_POSITIVE": "Nettement élevé", "UNKNOWN": "Indisponible",
}

LEVERAGE_STATE_FR: dict[str, str] = {
    "NEW_LONGS": "Nouveaux longs", "NEW_SHORTS": "Nouveaux shorts",
    "SHORT_COVERING": "Rachats de shorts", "LONG_LIQUIDATION": "Sorties de longs",
    "DELEVERAGING": "Réduction du levier", "QUIET": "Calme",
    "BALANCED": "Équilibré", "UNKNOWN": "Indisponible",
}

PATTERN_STATE_FR: dict[str, str] = {
    "CANDIDATE": "figure en formation",
    "CONFIRMED": "figure confirmée",
    "FAILED": "figure invalidée",
}

PATTERN_EDGE_FR: dict[str, str] = {
    "POSITIVE_EDGE": "avantage démontré",
    "NEGATIVE_EDGE": "relation inverse démontrée",
    "NO_MEASURABLE_EDGE": "aucun avantage démontré",
    "UNSTABLE": "résultat instable",
    "INSUFFICIENT_DATA": "preuve insuffisante",
    "NOT_YET_TESTED": "pas encore testé",
}

BREAKOUT_FR: dict[str, str] = {
    "BREAKOUT": "Cassure",
    "FAILED_BREAKOUT": "Cassure échouée",
    "FAKEOUT": "Fausse cassure",
    "REINTEGRATION": "Réintégration du range",
    "RETEST": "Retest de la zone cassée",
}

TIMEFRAME_FR: dict[str, str] = {
    "1w": "1S", "1d": "1J", "4h": "4H", "1h": "1H", "15m": "15M",
}

EVENT_KIND_FR: dict[str, str] = {
    "CPI": "Inflation US (CPI)", "FOMC": "Décision Fed (FOMC)",
    "NFP": "Emploi US (NFP)", "PPI": "Prix producteurs (PPI)",
    "PCE": "Inflation PCE", "GDP": "Croissance US (PIB)",
    "ETF_FLOW": "Flux ETF", "UNEMPLOYMENT": "Chômage US",
}


def fr(table: dict[str, str], value: object, default: str = "") -> str:
    """Look a value up by its enum name, accepting the enum or its string."""
    key = str(getattr(value, "value", value) or "").upper()
    return table.get(key, default)
