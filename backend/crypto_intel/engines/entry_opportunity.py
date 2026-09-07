"""EntryOpportunity: how favourable the current configuration looks.

This is NOT "the best time to buy", and the wording is chosen carefully to
avoid implying it. The state answers a narrower question: relative to what the
data shows, is the current configuration more or less favourable than usual?

Two things are always displayed together and never merged:

  ENTRY OPPORTUNITY   a description of the configuration
  MEASURED EDGE       whether anything here has been shown to predict returns

A FAVOURABLE configuration alongside NO_MEASURABLE_EDGE is the normal case and
means exactly what it says: the setup looks like ones people describe as good,
and we have not demonstrated that such setups actually work.

Invalidation comes first. Before describing why a configuration looks
favourable, the engine states what would objectively prove the reading wrong.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..core import labels_fr
from ..core.enums import Asset, Timeframe
from ..logging_setup import get_logger

log = get_logger("engines.entry_opportunity")

MAX_FACTORS = 5


# The enums stay the internal truth; only their rendering is translated, and
# the tables live in one place so a state cannot be translated in one producer
# and leak raw from another. This file used to carry its own six-entry
# location table against a nine-state enum, and `AT_RANGE_TOP` reached a user.
_LOCATION_FR = labels_fr.LOCATION_FR
_STRUCTURE_FR = labels_fr.STRUCTURE_SENTENCE_FR
_VOLATILITY_FR = labels_fr.VOLATILITY_SENTENCE_FR


class EntryOpportunityState(StrEnum):
    VERY_UNFAVORABLE = "VERY_UNFAVORABLE"
    UNFAVORABLE = "UNFAVORABLE"
    NEUTRAL = "NEUTRAL"
    FAVORABLE = "FAVORABLE"
    VERY_FAVORABLE = "VERY_FAVORABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class OpportunityFactor(BaseModel):
    name: str
    contribution: float          # -100..+100
    detail: str
    source: str = "structure"
    is_measured_edge: bool = False


class EntryOpportunityAssessment(BaseModel):
    asset: str
    timeframe: str
    state: EntryOpportunityState = EntryOpportunityState.INSUFFICIENT_DATA
    score: float | None = None
    factors: list[OpportunityFactor] = Field(default_factory=list)
    why_now: list[str] = Field(default_factory=list)
    invalidation: str = ""
    measured_edge_state: str = "NO_MEASURABLE_EDGE"
    measured_edge_note: str = ""
    missing: list[str] = Field(default_factory=list)
    statement: str = ""
    disclaimer: str = (
        "EntryOpportunity describes how the current configuration compares to normal "
        "conditions. It is not a claim that this is a good price, and it is not a "
        "recommendation to act. Read it alongside the measured edge, which is shown "
        "separately and is usually NO_MEASURABLE_EDGE."
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EntryOpportunityEngine:
    """Combine structure, derivatives and volatility into a described state."""

    def assess(
        self,
        asset: Asset,
        timeframe: Timeframe = Timeframe.H4,
        as_of: datetime | None = None,
    ) -> EntryOpportunityAssessment:
        from ..engines.edge import EdgeEngine
        from ..engines.leverage import CrowdingLevel, FundingBand, LeverageCrowdingEngine
        from ..engines.volatility import VolatilityRegimeEngine
        from ..structure.location import LocationState, StructuralLocationEngine
        from ..structure.market_structure import MarketStructureEngine

        out = EntryOpportunityAssessment(asset=asset.value, timeframe=timeframe.value)
        factors: list[OpportunityFactor] = []

        # --- invalidation first, before any favourable-sounding language ----
        location = StructuralLocationEngine().assess(asset, timeframe, as_of)
        out.invalidation = location.invalidation or (
            "no validated range, so no objective structural invalidation can be stated"
        )

        # 1. Higher-timeframe structure.
        higher = {
            Timeframe.M15: Timeframe.H4, Timeframe.H1: Timeframe.D1,
            Timeframe.H4: Timeframe.D1, Timeframe.D1: Timeframe.W1,
        }.get(timeframe, Timeframe.D1)
        structure = MarketStructureEngine().assess(asset, higher, as_of)
        if structure.state.value == "BULLISH_STRUCTURE":
            factors.append(OpportunityFactor(
                name="higher timeframe structure",
                contribution=30.0,
                detail=(
                    f"Structure {higher.value} haussière "
                    f"({' '.join(structure.labels)})"
                ),
            ))
        elif structure.state.value == "BEARISH_STRUCTURE":
            factors.append(OpportunityFactor(
                name="higher timeframe structure",
                contribution=-30.0,
                detail=(
                    f"Structure {higher.value} baissière "
                    f"({' '.join(structure.labels)})"
                ),
            ))
        elif structure.state.value == "RANGE_STRUCTURE":
            # Un range est un état structurel mesuré, pas une donnée absente.
            # Le classer en `missing` faisait apparaître « Lecture structurelle
            # incomplète » alors que la structure était parfaitement lue: elle
            # ne penchait simplement d'aucun côté.
            factors.append(OpportunityFactor(
                name="higher timeframe structure",
                contribution=0.0,
                detail=(
                    f"Structure {higher.value} en range "
                    f"({' '.join(structure.labels)})"
                ),
            ))
        else:
            out.missing.append(
                f"structure {higher.value} indéterminée "
                f"({_STRUCTURE_FR.get(structure.state.value, 'état inconnu')})"
            )

        # 2. Structural location. Descriptive: near a bottom is a cheaper place
        # within the range, which says nothing about whether the range holds.
        location_contributions = {
            LocationState.AT_RANGE_BOTTOM: 35.0,
            LocationState.NEAR_RANGE_BOTTOM: 25.0,
            LocationState.LOWER_THIRD: 12.0,
            LocationState.MID_RANGE: 0.0,
            LocationState.UPPER_THIRD: -12.0,
            LocationState.NEAR_RANGE_TOP: -25.0,
            LocationState.AT_RANGE_TOP: -35.0,
            LocationState.ABOVE_RANGE: -5.0,
            LocationState.BELOW_RANGE: -20.0,
        }
        if location.state in location_contributions:
            zone = (
                location.detected_range.bottom_zone
                if location.state in (
                    LocationState.AT_RANGE_BOTTOM, LocationState.NEAR_RANGE_BOTTOM,
                    LocationState.LOWER_THIRD,
                ) else location.detected_range.top_zone
            ) if location.detected_range else None
            quality = (
                f" (qualité de zone {zone.quality.score:.0f}/100)" if zone else ""
            )
            factors.append(OpportunityFactor(
                name="structural location",
                contribution=location_contributions[location.state],
                # En français: cette phrase arrive telle quelle à l'écran, et
                # « 4h price is near range top » y était lisible.
                detail=(
                    f"En {timeframe.value}, le prix est "
                    f"{_LOCATION_FR.get(location.state.value, location.state.value)}"
                    f"{quality}"
                ),
            ))
        else:
            out.missing.append(
                f"aucun range validé sur l'unité {timeframe.value}"
            )

        # 3. Funding: an extreme reading is a stretched condition, not a signal.
        leverage = LeverageCrowdingEngine()
        funding = leverage.funding_context(asset, as_of)
        if funding.band is FundingBand.EXTREME_POSITIVE:
            factors.append(OpportunityFactor(
                name="funding stretched",
                contribution=-18.0, source="derivatives",
                detail=(
                    f"Funding au {funding.percentile:.0f}e centile de son "
                    "historique : coût de portage tendu"
                ),
            ))
        elif funding.band is FundingBand.EXTREME_NEGATIVE:
            factors.append(OpportunityFactor(
                name="funding depressed",
                contribution=12.0, source="derivatives",
                detail=(
                    f"Funding au {funding.percentile:.0f}e centile de son "
                    "historique : coût de portage inhabituellement bas"
                ),
            ))
        elif funding.band is FundingBand.NEUTRAL and funding.percentile is not None:
            factors.append(OpportunityFactor(
                name="funding normalised",
                contribution=8.0, source="derivatives",
                detail=(
                    f"Funding dans sa normale, au {funding.percentile:.0f}e "
                    "centile de son historique"
                ),
            ))
        elif funding.percentile is not None:
            # NEGATIVE et POSITIVE sont des lectures mesurées. Les faire tomber
            # dans le cas « indisponible » produisait la contradiction visible
            # à l'écran: le funding affichait p24 pendant que l'explication
            # disait « funding percentile unavailable ».
            leaning = (
                "sous" if funding.band is FundingBand.NEGATIVE else "au-dessus de"
            )
            factors.append(OpportunityFactor(
                name="funding leaning",
                contribution=4.0 if funding.band is FundingBand.NEGATIVE else -4.0,
                source="derivatives",
                detail=(
                    f"Funding {leaning} sa médiane, au "
                    f"{funding.percentile:.0f}e centile"
                ),
            ))
        else:
            out.missing.append(
                "historique de funding insuffisant pour situer le niveau actuel"
            )

        # 4. Crowding raises the cost of being wrong, whatever the direction.
        crowding = leverage.crowding(asset, as_of)
        if crowding.level is CrowdingLevel.EXTREME:
            factors.append(OpportunityFactor(
                name="crowding extreme",
                contribution=-25.0, source="derivatives",
                detail=(
                    f"Encombrement dérivé {crowding.score}/100. L'open interest "
                    "a deux côtés : aucune direction n'en est déduite."
                ),
            ))
        elif crowding.level is CrowdingLevel.LOW:
            factors.append(OpportunityFactor(
                name="crowding low",
                contribution=12.0, source="derivatives",
                detail=f"Encombrement dérivé faible, {crowding.score}/100",
            ))

        # 5. Volatility compression: a description of conditions, not direction.
        volatility = VolatilityRegimeEngine().assess(asset, as_of)
        if volatility.regime in ("VERY_LOW", "LOW"):
            factors.append(OpportunityFactor(
                name="volatility compressed",
                contribution=8.0, source="volatility",
                detail=(
                    f"Volatilité réalisée "
                    f"{_VOLATILITY_FR.get(volatility.regime, 'inconnue')}, au "
                    f"{volatility.atr_percentile}e centile : les mouvements sont "
                    "petits, dans les deux sens"
                ),
            ))
        elif volatility.regime == "VERY_HIGH":
            factors.append(OpportunityFactor(
                name="volatility elevated",
                contribution=-10.0, source="volatility",
                detail=(
                    f"Volatilité réalisée "
                    f"{_VOLATILITY_FR.get(volatility.regime, 'inconnue')} : "
                    "mouvements plus amples, dans les deux sens"
                ),
            ))

        if not factors:
            out.state = EntryOpportunityState.INSUFFICIENT_DATA
            out.statement = (
                f"No factor could be measured for {asset.value} on {timeframe.value}; "
                "the configuration is INSUFFICIENT_DATA, not neutral."
            )
            return out

        out.factors = sorted(factors, key=lambda f: -abs(f.contribution))
        out.score = round(
            sum(f.contribution for f in factors) / max(len(factors), 1), 1
        )
        out.state = (
            EntryOpportunityState.VERY_FAVORABLE if out.score >= 22 else
            EntryOpportunityState.FAVORABLE if out.score >= 10 else
            EntryOpportunityState.NEUTRAL if out.score > -10 else
            EntryOpportunityState.UNFAVORABLE if out.score > -22 else
            EntryOpportunityState.VERY_UNFAVORABLE
        )

        out.why_now = [
            f"{f.detail}" for f in out.factors[:MAX_FACTORS]
        ]

        # The edge verdict, kept strictly separate and never folded into score.
        edge = EdgeEngine().assess(asset)
        out.measured_edge_state = edge.state.value
        out.measured_edge_note = edge.statement[:220]

        out.statement = (
            f"{asset.value} {timeframe.value} configuration is {out.state.value} "
            f"({out.score:+.0f}). Measured edge: {out.measured_edge_state}. "
            + (
                "The configuration resembles setups traders describe as favourable, but "
                "no relationship of this kind has been shown to predict returns, so this "
                "is a description rather than evidence."
                if out.measured_edge_state != "POSITIVE_EDGE" else
                "A measured edge exists; see the edge panel for its size and stability."
            )
        )
        if out.missing:
            out.statement += f" Not included: {'; '.join(out.missing)}."
        return out
