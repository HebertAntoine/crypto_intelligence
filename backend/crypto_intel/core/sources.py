"""Source hierarchy: what may override what.

The rule this encodes is simple and non-negotiable. A tutorial explaining
Solana activity cannot override what the Solana RPC reports. A trader saying
"BTC is at 92k" cannot override the exchange price. A YouTube macro take
cannot override FRED.

Educational and human sources are genuinely valuable - they teach vocabulary,
tolerances, and what an experienced eye looks at - but they are claims about
how to read data, never data themselves. Keeping that boundary in the type
system means it cannot be blurred by accident later.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class SourceTier(IntEnum):
    """Lower number wins. Ordering is the whole point of this enum."""

    BLOCKCHAIN_NATIVE = 1      # Solana RPC, Ethereum JSON-RPC, official institutions
    OFFICIAL_API = 2           # exchange APIs, FRED/ALFRED, issuer filings
    SPECIALIST_PROVIDER = 3    # CoinGecko, DefiLlama, Coinglass
    RESEARCH_LITERATURE = 4    # papers, methodology references
    HUMAN_ANALYSIS = 5         # trader videos, personal courses, annotations
    GENERAL_MEDIA = 6          # news, commentary

    @property
    def is_primary_data(self) -> bool:
        """Tiers 1-3 carry measurements. Tiers 4-6 carry claims about them."""
        return self <= SourceTier.SPECIALIST_PROVIDER

    @property
    def label(self) -> str:
        return {
            SourceTier.BLOCKCHAIN_NATIVE: "blockchain / protocol native",
            SourceTier.OFFICIAL_API: "official API or documentation",
            SourceTier.SPECIALIST_PROVIDER: "specialist data provider",
            SourceTier.RESEARCH_LITERATURE: "research or educational literature",
            SourceTier.HUMAN_ANALYSIS: "human trader analysis",
            SourceTier.GENERAL_MEDIA: "general media or commentary",
        }[self]


# Known providers mapped to their tier. Anything absent is treated as
# GENERAL_MEDIA, which is the safest default: it can never override anything.
PROVIDER_TIERS: dict[str, SourceTier] = {
    "solana_rpc": SourceTier.BLOCKCHAIN_NATIVE,
    "ethereum_rpc": SourceTier.BLOCKCHAIN_NATIVE,
    "bitcoin_rpc": SourceTier.BLOCKCHAIN_NATIVE,
    "blockchain_info": SourceTier.BLOCKCHAIN_NATIVE,
    "blockchair": SourceTier.BLOCKCHAIN_NATIVE,
    "fred": SourceTier.OFFICIAL_API,
    "alfred": SourceTier.OFFICIAL_API,
    "binance": SourceTier.OFFICIAL_API,
    "binance_futures": SourceTier.OFFICIAL_API,
    "bybit": SourceTier.OFFICIAL_API,
    "bybit_backfill": SourceTier.OFFICIAL_API,
    "okx": SourceTier.OFFICIAL_API,
    "coinbase": SourceTier.OFFICIAL_API,
    "yahoo": SourceTier.OFFICIAL_API,
    "stooq": SourceTier.OFFICIAL_API,
    "coingecko": SourceTier.SPECIALIST_PROVIDER,
    "defillama": SourceTier.SPECIALIST_PROVIDER,
    "coinglass": SourceTier.SPECIALIST_PROVIDER,
    "farside": SourceTier.SPECIALIST_PROVIDER,
    "goodcrypto": SourceTier.RESEARCH_LITERATURE,
    "personal_course": SourceTier.RESEARCH_LITERATURE,
    "lexa_moon": SourceTier.HUMAN_ANALYSIS,
    "trader_analysis": SourceTier.HUMAN_ANALYSIS,
    "user_annotation": SourceTier.HUMAN_ANALYSIS,
}


def tier_for(provider: str) -> SourceTier:
    return PROVIDER_TIERS.get((provider or "").lower(), SourceTier.GENERAL_MEDIA)


@dataclass(slots=True)
class SourceClaim:
    """Something a source asserts, tagged with where it came from."""

    provider: str
    statement: str
    value: Any = None
    metric: str | None = None

    @property
    def tier(self) -> SourceTier:
        return tier_for(self.provider)

    @property
    def is_measurement(self) -> bool:
        return self.tier.is_primary_data


def can_override(challenger: str, incumbent: str) -> bool:
    """May `challenger`'s value replace `incumbent`'s?

    Strictly lower tier only. Equal tiers do not override each other - that is
    a disagreement to surface, not to silently resolve.
    """
    return tier_for(challenger) < tier_for(incumbent)


def resolve_conflict(claims: list[SourceClaim]) -> dict[str, Any]:
    """Pick the authoritative claim and describe what was overruled.

    Never silently discards the losers: a tutorial contradicting the RPC is
    itself information worth seeing, so both sides come back.
    """
    if not claims:
        return {"status": "NO_CLAIMS"}

    ordered = sorted(claims, key=lambda c: c.tier)
    winner = ordered[0]
    same_tier = [c for c in ordered[1:] if c.tier == winner.tier]
    overruled = [c for c in ordered[1:] if c.tier > winner.tier]

    result: dict[str, Any] = {
        "status": "RESOLVED",
        "authoritative": {
            "provider": winner.provider, "tier": int(winner.tier),
            "tier_label": winner.tier.label, "value": winner.value,
            "statement": winner.statement,
        },
        "is_measurement": winner.is_measurement,
        "overruled": [
            {
                "provider": c.provider, "tier": int(c.tier),
                "tier_label": c.tier.label, "value": c.value,
                "reason": (
                    f"{c.tier.label} cannot override {winner.tier.label}"
                ),
            }
            for c in overruled
        ],
    }

    if same_tier:
        result["status"] = "DISAGREEMENT_AT_SAME_TIER"
        result["conflicting_peers"] = [
            {"provider": c.provider, "value": c.value} for c in same_tier
        ]
        result["note"] = (
            "Two sources of equal authority disagree. This is reported rather "
            "than resolved: picking one arbitrarily would hide the conflict."
        )
    return result
