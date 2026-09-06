"""Enumerations shared across every layer.

These are deliberately explicit: the difference between "we don't have the
data" and "the data says zero" is the whole point of this project.
"""

from __future__ import annotations

from enum import StrEnum


class Asset(StrEnum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"
    GLOBAL = "GLOBAL"

    @classmethod
    def tradables(cls) -> list[Asset]:
        return [cls.BTC, cls.ETH, cls.SOL]


class Timeframe(StrEnum):
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"

    @property
    def minutes(self) -> int:
        return {"15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}[self.value]


class Freshness(StrEnum):
    """How recent a datapoint is, relative to its own metric class.

    Ordered worst-to-best via `rank`. UNAVAILABLE is not "old data",
    it is the absence of data - a distinction the scoring engine relies on.
    """

    LIVE = "LIVE"
    MIN_15 = "MIN_15"
    HOUR_1 = "HOUR_1"
    TODAY = "TODAY"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"

    @property
    def rank(self) -> int:
        return {
            "UNAVAILABLE": 0,
            "STALE": 1,
            "TODAY": 2,
            "HOUR_1": 3,
            "MIN_15": 4,
            "LIVE": 5,
        }[self.value]

    @property
    def is_usable(self) -> bool:
        return self is not Freshness.UNAVAILABLE

    @property
    def label_fr(self) -> str:
        return {
            "LIVE": "temps reel",
            "MIN_15": "< 15 min",
            "HOUR_1": "< 1 h",
            "TODAY": "aujourd'hui",
            "STALE": "perimee",
            "UNAVAILABLE": "indisponible",
        }[self.value]


class DataQuality(StrEnum):
    MEASURED = "MEASURED"        # read directly from an authoritative source
    DERIVED = "DERIVED"          # computed by us from measured values
    ESTIMATED = "ESTIMATED"      # heuristic - always flagged as such
    UNAVAILABLE = "UNAVAILABLE"  # no data. never a placeholder number.


class EvidenceKind(StrEnum):
    """The four epistemic levels. Never mix them."""

    FACT = "FACT"
    COMPUTATION = "COMPUTATION"
    INTERPRETATION = "INTERPRETATION"
    HYPOTHESIS = "HYPOTHESIS"


class ProviderCategory(StrEnum):
    MARKET = "market"
    DERIVATIVES = "derivatives"
    ETF = "etf"
    ONCHAIN = "onchain"
    DEFI = "defi"
    STABLECOINS = "stablecoins"
    MACRO = "macro"
    NEWS = "news"
    REGULATION = "regulation"
    WHALES = "whales"
    RWA = "rwa"
    KNOWLEDGE = "knowledge"


class FetchStatus(StrEnum):
    """Why a fetch returned nothing. Providers never raise into business logic."""

    OK = "OK"
    NOT_CONFIGURED = "NOT_CONFIGURED"        # API key missing
    BLOCKED_BY_SOURCE = "BLOCKED_BY_SOURCE"  # anti-bot / 403 - we stop, we never bypass
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    NO_DATA = "NO_DATA"
    DISABLED = "DISABLED"

    @property
    def user_message(self) -> str:
        return {
            "OK": "ok",
            "NOT_CONFIGURED": "UNAVAILABLE - provider not configured",
            "BLOCKED_BY_SOURCE": "UNAVAILABLE - source blocks automated access",
            "RATE_LIMITED": "UNAVAILABLE - rate limited",
            "NETWORK_ERROR": "UNAVAILABLE - network error",
            "PARSE_ERROR": "UNAVAILABLE - could not parse source response",
            "NO_DATA": "UNAVAILABLE - source returned no data",
            "DISABLED": "UNAVAILABLE - provider disabled in configuration",
        }[self.value]


class TrendDirection(StrEnum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    RANGE = "RANGE"
    UNDETERMINED = "UNDETERMINED"


class MarketStructure(StrEnum):
    HH_HL = "HH_HL"          # higher highs + higher lows -> bullish structure
    LH_LL = "LH_LL"          # lower highs + lower lows -> bearish structure
    MIXED = "MIXED"
    RANGE = "RANGE"
    UNDETERMINED = "UNDETERMINED"


class ConfirmationState(StrEnum):
    FORMING = "FORMING"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"


class Horizon(StrEnum):
    SHORT = "short"    # 1h -> 24h
    MEDIUM = "medium"  # days -> weeks
    LONG = "long"      # weeks -> months


class Direction(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    INCONCLUSIVE = "INCONCLUSIVE"   # evidence insufficient - not the same as neutral


class LegalStatus(StrEnum):
    """A proposal must never be presented as adopted law."""

    ADOPTED = "ADOPTED"
    PROPOSED = "PROPOSED"
    RUMOR = "RUMOR"
    POLITICAL_STATEMENT = "POLITICAL_STATEMENT"
    CONSULTATION = "CONSULTATION"
    VOTE_SCHEDULED = "VOTE_SCHEDULED"
    VOTE_HELD = "VOTE_HELD"
    REGULATORY_DECISION = "REGULATORY_DECISION"
    ENFORCEMENT = "ENFORCEMENT"
    UNCERTAIN = "UNCERTAIN"

    @property
    def is_binding(self) -> bool:
        return self in (
            LegalStatus.ADOPTED,
            LegalStatus.REGULATORY_DECISION,
            LegalStatus.ENFORCEMENT,
        )


class RiskLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class AlertImportance(StrEnum):
    INFO = "INFO"
    WATCH = "WATCH"
    IMPORTANT = "IMPORTANT"
    CRITICAL = "CRITICAL"


class AlertKind(StrEnum):
    ETF_INFLOW_SPIKE = "ETF_INFLOW_SPIKE"
    ETF_OUTFLOW_SPIKE = "ETF_OUTFLOW_SPIKE"
    FUNDING_EXTREME = "FUNDING_EXTREME"
    OPEN_INTEREST_SPIKE = "OPEN_INTEREST_SPIKE"
    BREAKOUT = "BREAKOUT"
    RSI_DIVERGENCE = "RSI_DIVERGENCE"
    MAJOR_REGULATORY_NEWS = "MAJOR_REGULATORY_NEWS"
    FOMC_TODAY = "FOMC_TODAY"
    CPI_TODAY = "CPI_TODAY"
    WHALE_MOVEMENT = "WHALE_MOVEMENT"
    STABLECOIN_LIQUIDITY_SHIFT = "STABLECOIN_LIQUIDITY_SHIFT"
    HIGH_CONTRADICTION = "HIGH_CONTRADICTION"
    MARKET_REGIME_CHANGE = "MARKET_REGIME_CHANGE"


class Reliability(StrEnum):
    """Attached to every whale signal - and to anything heuristic."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNVERIFIED = "UNVERIFIED"
