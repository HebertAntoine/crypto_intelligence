"""Every weight and threshold the BUY / WAIT / SELL decision uses, in one place.

These values are an initial calibration, stated as such. None of them has been
shown optimal: they are a starting point for the backtest framework
(``crypto_intel.backtest.decision_backtest``) to evaluate, and they must be
changed here - never inline in an engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ..future_events.models import DecisionHorizon

MACRO = "macro"
LIQUIDITY = "liquidity"
FLOWS = "flows"
DERIVATIVES = "derivatives"
ONCHAIN = "onchain"
TECHNICAL = "technical"
CYCLE = "cycle"

FAMILIES = (MACRO, LIQUIDITY, FLOWS, DERIVATIVES, ONCHAIN, TECHNICAL, CYCLE)

#: Families that describe the backdrop. They move the score a little but never
#: count as an independent confirmation: a BUY or a SELL needs families that
#: read the market itself.
CONTEXT_FAMILIES = frozenset({CYCLE})

FAMILY_LABEL = {
    MACRO: "Macro & banques centrales",
    LIQUIDITY: "Liquidité",
    FLOWS: "ETF & flux au comptant",
    DERIVATIVES: "Dérivés",
    ONCHAIN: "On-chain & baleines",
    TECHNICAL: "Technique & structure",
    CYCLE: "Cycle Bitcoin & régime crypto",
}
FAMILY_EMOJI = {
    MACRO: "🏛️",
    LIQUIDITY: "💵",
    FLOWS: "🪙",
    DERIVATIVES: "📈",
    ONCHAIN: "🐋",
    TECHNICAL: "📊",
    CYCLE: "🔄",
}

#: Initial weights per horizon (percent), one reasoning per horizon:
#:   24 h - short-term chart, spot tape, leverage; the cycle barely counts.
#:   7 d  - structure, leverage, spot, macro and central banks.
#:   30 d - long structure, macro trajectory, cycle, structural flows;
#:          funding at one instant matters little.
#: A family with no usable data is dropped and the rest renormalised.
HORIZON_WEIGHTS: dict[DecisionHorizon, dict[str, float]] = {
    DecisionHorizon.H24: {
        TECHNICAL: 30, FLOWS: 25, DERIVATIVES: 25, MACRO: 12, LIQUIDITY: 3, ONCHAIN: 3, CYCLE: 2,
    },
    DecisionHorizon.D7: {
        TECHNICAL: 25, DERIVATIVES: 20, FLOWS: 20, MACRO: 20, LIQUIDITY: 5, ONCHAIN: 5, CYCLE: 5,
    },
    DecisionHorizon.D30: {
        TECHNICAL: 20, MACRO: 22, LIQUIDITY: 13, FLOWS: 15, CYCLE: 15, ONCHAIN: 10, DERIVATIVES: 5,
    },
}

#: Families without which a directional call on the horizon is not defensible.
CRITICAL_FAMILIES: dict[DecisionHorizon, tuple[str, ...]] = {
    DecisionHorizon.H24: (DERIVATIVES, TECHNICAL),
    DecisionHorizon.D7: (MACRO, TECHNICAL),
    DecisionHorizon.D30: (MACRO, LIQUIDITY),
}

#: Window each horizon reads its changes over.
HORIZON_WINDOW: dict[DecisionHorizon, timedelta] = {
    DecisionHorizon.H24: timedelta(days=1),
    DecisionHorizon.D7: timedelta(days=7),
    DecisionHorizon.D30: timedelta(days=30),
}


@dataclass(frozen=True, slots=True)
class DecisionThresholds:
    """What it takes to leave WAIT. Configurable; to be validated by backtest."""

    buy_score: float = 30.0
    sell_score: float = -30.0
    min_confidence: float = 70.0
    min_confirming_families: int = 3
    #: A family "confirms" when its own score reaches this in the same direction.
    confirming_family_score: float = 15.0
    #: Below this the data is too thin or too inconsistent to act on at all.
    uncertainty_confidence: float = 50.0
    #: Minimum families with usable data for any directional call.
    min_available_families: int = 3
    #: Contradiction: both sides hold at least this share of the weight with
    #: families at or beyond ``contradiction_family_score``.
    contradiction_weight_share: float = 0.30
    contradiction_family_score: float = 30.0
    #: DVOL percentile above which the market is in an extreme-risk regime.
    extreme_dvol_percentile: float = 95.0
    #: Event risk (importance x proximity x magnitude x uncertainty x exposure)
    #: at which an upcoming event holds any entry...
    event_block_score: float = 0.6
    #: ...and the lower level at which it holds one unless the rest of the
    #: evidence is confident enough to justify crossing it.
    event_caution_score: float = 0.3
    event_caution_confidence: float = 75.0
    #: Entry quality: RSI at or above this is a stretched market - the trend
    #: may hold, the entry is late.
    stretched_rsi: float = 70.0
    #: Price within this distance under the next resistance (percent, per
    #: horizon) waits for the break rather than buying into the ceiling.
    resistance_margin_pct: dict[str, float] = field(
        default_factory=lambda: {"24h": 0.7, "7d": 1.5, "30d": 3.0}
    )
    #: A spot-pressure signal at or below minus this opposes a BUY.
    spot_opposition_signal: float = 0.2


THRESHOLDS = DecisionThresholds()


#: Component scales: the move that counts as "one unit" of signal on each
#: horizon. A signal is ``tanh(change / scale)``, so a move of one scale gives
#: about 0.76 and larger moves saturate instead of dominating.
@dataclass(frozen=True, slots=True)
class HorizonScales:
    yield_bp: float
    dollar_pct: float
    vix_points: float
    equity_pct: float
    oil_shock_pct: float
    tga_bn: float
    rrp_bn: float
    fed_assets_bn: float
    stablecoin_pct: float
    price_move_pct: float
    oi_move_pct: float


SCALES: dict[DecisionHorizon, HorizonScales] = {
    DecisionHorizon.H24: HorizonScales(
        yield_bp=5, dollar_pct=0.5, vix_points=2.0, equity_pct=1.0, oil_shock_pct=4.0,
        tga_bn=40, rrp_bn=25, fed_assets_bn=25, stablecoin_pct=0.3,
        price_move_pct=1.5, oi_move_pct=3.0,
    ),
    DecisionHorizon.D7: HorizonScales(
        yield_bp=12, dollar_pct=1.2, vix_points=3.0, equity_pct=3.0, oil_shock_pct=8.0,
        tga_bn=75, rrp_bn=50, fed_assets_bn=50, stablecoin_pct=1.0,
        price_move_pct=4.0, oi_move_pct=8.0,
    ),
    DecisionHorizon.D30: HorizonScales(
        yield_bp=25, dollar_pct=2.5, vix_points=4.0, equity_pct=6.0, oil_shock_pct=15.0,
        tga_bn=150, rrp_bn=100, fed_assets_bn=100, stablecoin_pct=2.5,
        price_move_pct=8.0, oi_move_pct=15.0,
    ),
}


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """How a series is shown and when it stops being current."""

    label: str
    emoji: str
    unit: str
    max_age: timedelta
    why: str
    source_tier: str = "OFFICIAL"


#: Beyond ``max_age`` a value is STALE: shown, dated, never used as current.
#: Ages allow for weekends and the publication rhythm of each series.
METRICS: dict[str, MetricSpec] = {
    "macro.us10y": MetricSpec(
        "Taux US 10 ans", "🏛️", "%", timedelta(days=4),
        "Le rendement sans risque de référence. Plus il est élevé, plus détenir "
        "un actif sans rendement comme une crypto coûte cher en opportunité. À "
        "lire avec les taux réels, le dollar et la liquidité.",
    ),
    "macro.us2y": MetricSpec(
        "Taux US 2 ans", "🏛️", "%", timedelta(days=4),
        "Le taux le plus sensible aux anticipations de décisions de la Fed : il "
        "monte quand le marché attend une politique plus restrictive.",
    ),
    "macro.real10y": MetricSpec(
        "Taux réel US 10 ans", "🏛️", "%", timedelta(days=4),
        "Le rendement une fois l'inflation déduite. C'est lui qui mesure vraiment "
        "le coût de renoncer à un placement sûr : sa hausse pèse historiquement "
        "sur les actifs risqués et sans rendement.",
    ),
    "macro.yield_curve_10y2y": MetricSpec(
        "Pente 10 ans - 2 ans", "🏛️", "pt", timedelta(days=4),
        "L'écart entre taux longs et courts. Une courbe qui se repentifie peut "
        "signaler des baisses de taux attendues ou une hausse de la prime de "
        "risque long terme : son sens se lit avec le reste.",
    ),
    "macro.fed_funds_rate": MetricSpec(
        "Taux effectif des fonds fédéraux", "🇺🇸", "%", timedelta(days=5),
        "Le coût de l'argent au jour le jour fixé par la Fed : la référence de "
        "toute la politique monétaire américaine.",
    ),
    "macro.dxy": MetricSpec(
        "Dollar (DXY)", "💵", "", timedelta(days=4),
        "Un dollar qui se renforce resserre les conditions financières mondiales "
        "et coïncide souvent avec une moindre appétence pour le risque.",
        source_tier="MARKET_DATA",
    ),
    "macro.vix": MetricSpec(
        "Volatilité actions (VIX)", "📉", "", timedelta(days=4),
        "La peur mesurée sur les options du S&P 500. Une montée brutale "
        "accompagne souvent des ventes d'actifs risqués, crypto comprise.",
        source_tier="MARKET_DATA",
    ),
    "macro.nasdaq": MetricSpec(
        "Nasdaq", "📈", "", timedelta(days=4),
        "L'appétit pour les actifs de croissance. La crypto évolue souvent dans "
        "le même sens que les valeurs technologiques sur les horizons courts.",
        source_tier="MARKET_DATA",
    ),
    "macro.sp500": MetricSpec(
        "S&P 500", "📈", "", timedelta(days=4),
        "Le baromètre des actions américaines : contexte d'appétit pour le risque.",
        source_tier="MARKET_DATA",
    ),
    "macro.oil_wti": MetricSpec(
        "Pétrole (WTI)", "🛢️", "$", timedelta(days=4),
        "Facteur secondaire : il ne compte que quand son mouvement est assez fort "
        "pour relancer l'inflation, retarder des baisses de taux et faire "
        "remonter les rendements.",
        source_tier="MARKET_DATA",
    ),
    "macro.cpi": MetricSpec(
        "Inflation (CPI)", "📈", "", timedelta(days=45),
        "L'inflation des prix à la consommation. Elle conditionne les décisions "
        "de la Fed et donc les taux.",
    ),
    "macro.core_cpi": MetricSpec(
        "Inflation sous-jacente (Core CPI)", "📈", "", timedelta(days=45),
        "L'inflation hors énergie et alimentation, que la Fed suit pour juger si "
        "l'inflation est durable.",
    ),
    "macro.unemployment": MetricSpec(
        "Chômage US", "👷", "%", timedelta(days=45),
        "Un chômage qui monte ralentit l'économie mais peut rapprocher des baisses "
        "de taux : son effet sur la crypto n'est pas univoque.",
    ),
    "macro.nonfarm_payrolls": MetricSpec(
        "Emplois non agricoles", "👷", "k", timedelta(days=45),
        "Les créations d'emplois : la vigueur de l'économie américaine.",
    ),
    "macro.avg_hourly_earnings": MetricSpec(
        "Salaire horaire moyen", "👷", "$", timedelta(days=45),
        "La hausse des salaires alimente l'inflation de services, surveillée par la Fed.",
    ),
    "liquidity.fed_total_assets": MetricSpec(
        "Bilan de la Fed", "🏦", "Md$", timedelta(days=9),
        "Quand la Fed achète des titres, son bilan grossit et injecte des "
        "liquidités dans le système ; quand il fond, elle en retire.",
    ),
    "liquidity.tga": MetricSpec(
        "Compte du Trésor (TGA)", "🏦", "Md$", timedelta(days=5),
        "L'argent que le Trésor garde à la Fed. Quand ce compte gonfle, il "
        "retire des liquidités du système bancaire ; quand il baisse, il en rend.",
    ),
    "liquidity.rrp": MetricSpec(
        "Reverse repo de la Fed (RRP)", "🏦", "Md$", timedelta(days=5),
        "Des liquidités garées à la Fed. Leur baisse les remet en circulation, "
        "mais l'effet s'épuise quand le stock est déjà proche de zéro.",
    ),
    "stablecoin.supply.total": MetricSpec(
        "Offre de stablecoins", "💧", "Md$", timedelta(days=2),
        "Le « cash » disponible sur les plateformes crypto. Une offre qui grossit "
        "signale des capitaux prêts à être investis.",
        source_tier="AGGREGATOR",
    ),
}


@dataclass(frozen=True, slots=True)
class ProvenanceRank:
    """Section 18: which kind of source may drive a decision."""

    order: tuple[str, ...] = (
        "OFFICIAL",
        "EXCHANGE",
        "MARKET_DATA",
        "AGGREGATOR",
        "SCRAPED",
        "SOCIAL",
    )
    #: A social source is never a primary signal.
    may_drive: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"OFFICIAL", "EXCHANGE", "MARKET_DATA", "AGGREGATOR", "SCRAPED"}
        )
    )


PROVENANCE = ProvenanceRank()
