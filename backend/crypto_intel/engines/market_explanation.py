"""Why is the market moving?

The decision engine answers "what to do". This answers the question that comes
before it, and it answers with families rather than with one number:

    💰 institutions   regulated products, US and worldwide
    🪙 participation  how much of the market is taking part
    🟣 catalysts      something specific to this asset
    🏦 macro          the financial backdrop
    ⚠️ derivatives    leverage, and what it makes fragile
    📊 technique      structure and momentum

Each family contributes at most one line, and the conclusion is a reading, not
an instruction. Four positive lines do not make a BUY: that verdict has its own
gates, its own thresholds and its own statistical validation, and this module
never bypasses them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.enums import Asset
from .factor_semantics import fr_number
from .pit_view import PointInTimeView


@dataclass(slots=True)
class ExplanationLine:
    emoji: str
    family: str
    title: str
    detail: str
    tone: str  # GREEN | ORANGE | RED | YELLOW | WHITE
    route: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "emoji": self.emoji,
            "family": self.family,
            "title": self.title,
            "detail": self.detail,
            "tone": self.tone,
            "route": self.route,
        }


@dataclass(slots=True)
class MarketExplanation:
    asset: str
    direction: str  # UP | DOWN | FLAT
    question: str
    lines: list[ExplanationLine] = field(default_factory=list)
    conclusion: str = ""
    unexplained: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "question": self.question,
            "lines": [line.to_dict() for line in self.lines],
            "conclusion": self.conclusion,
            "unexplained": self.unexplained,
            "note": (
                "Cette lecture explique le mouvement. Elle ne remplace pas la décision, "
                "qui garde ses propres garde-fous."
            ),
        }


def _direction(view: PointInTimeView, asset: Asset) -> tuple[str, float | None]:
    from ..core.enums import Timeframe

    daily = view.candles(asset.value, Timeframe.D1)
    if len(daily) < 8:
        return "FLAT", None
    change = (float(daily["close"].iloc[-1]) / float(daily["close"].iloc[-8]) - 1) * 100
    return ("UP" if change >= 1 else "DOWN" if change <= -1 else "FLAT"), change


def explain_market(
    view: PointInTimeView,
    asset: Asset,
    *,
    demand: Any = None,
    breadth: Any = None,
    catalysts: Any = None,
    families: dict[str, Any] | None = None,
) -> MarketExplanation:
    """Assemble the families into an explanation of the move under way."""

    direction, change = _direction(view, asset)
    question = {
        "UP": "📈 Pourquoi le marché monte ?",
        "DOWN": "📉 Pourquoi le marché baisse ?",
        "FLAT": "➡️ Pourquoi le marché stagne ?",
    }[direction]
    explanation = MarketExplanation(asset=asset.value, direction=direction, question=question)
    families = families or {}

    if demand is not None and getattr(demand, "state", None) is not None:
        state = demand.state.value
        tone = {
            "STRONG_INFLOW": "GREEN", "INFLOW": "GREEN", "NEUTRAL": "YELLOW",
            "OUTFLOW": "RED", "STRONG_OUTFLOW": "RED", "DIVERGENCE": "ORANGE",
            "INSUFFICIENT_DATA": "WHITE",
        }[state]
        detail = (demand.sentences or ["Flux non mesurés."])[0]
        explanation.lines.append(ExplanationLine(
            "💰", "institutions", f"Institutions — {demand.label.lower()}", detail, tone,
            route="institutions",
        ))

    if breadth is not None and getattr(breadth, "regime", None) is not None:
        tone = {
            "ALTSEASON_CONFIRMED": "GREEN", "BROAD_CRYPTO_RALLY": "GREEN",
            "ALTSEASON_EARLY": "YELLOW", "BTC_LED_RALLY": "ORANGE",
            "ETH_LED_RALLY": "ORANGE", "SELECTIVE_ALT_RALLY": "ORANGE",
            "MIXED": "YELLOW", "RISK_OFF": "RED", "INSUFFICIENT_DATA": "WHITE",
        }[breadth.regime.value]
        explanation.lines.append(ExplanationLine(
            "🪙", "participation", f"Participation — {breadth.label.lower()}",
            (breadth.sentences or [""])[0], tone, route="market",
        ))

    catalyst_list = getattr(catalysts, "catalysts", []) or []
    if catalyst_list:
        first = catalyst_list[0]
        reaction = first.reaction
        tone = "YELLOW"
        if reaction is not None:
            tone = {
                "CATALYST_CONFIRMED_BY_MARKET": "GREEN",
                "CATALYST_REJECTED_BY_MARKET": "RED",
                "CATALYST_ALREADY_PRICED": "YELLOW",
                "CATALYST_MIXED_REACTION": "ORANGE",
                "CATALYST_NOT_PRICED": "WHITE",
                "UNKNOWN": "WHITE",
            }.get(reaction.state.value, "YELLOW")
        detail = f"{first.title} — {first.stage_label.lower()}."
        if reaction is not None:
            detail += f" Marché : {reaction.label.lower()}."
        explanation.lines.append(ExplanationLine(
            {"BTC": "🟠", "ETH": "💎", "SOL": "🟣"}.get(asset.value, "🪙"),
            "catalysts", f"{asset.value} — catalyseur propre", detail, tone, route="catalysts",
        ))

    macro = families.get("macro")
    if macro is not None and getattr(macro, "usable", False):
        tone = "RED" if (macro.score or 0) < -20 else "GREEN" if (macro.score or 0) > 20 else "ORANGE"
        explanation.lines.append(ExplanationLine(
            "🏦", "macro", "Macro", macro.headline or "Conditions financières suivies.",
            tone, route="macro",
        ))
    derivatives = families.get("derivatives")
    if derivatives is not None and getattr(derivatives, "usable", False):
        crowded = str((derivatives.extra or {}).get("crowding", "")) in {
            "CROWDED_LONGS", "CROWDED_SHORTS"
        }
        explanation.lines.append(ExplanationLine(
            "⚠️", "derivatives", "Dérivés",
            derivatives.headline or "Levier suivi.",
            "RED" if crowded else "GREEN", route="derivatives",
        ))
    technical = families.get("technical")
    if technical is not None and getattr(technical, "usable", False):
        explanation.lines.append(ExplanationLine(
            "📊", "technical", "Technique", technical.headline or "Structure suivie.",
            "GREEN" if (technical.score or 0) > 0 else "RED", route="technical",
        ))

    explanation.lines = explanation.lines[:5]
    explanation.conclusion = _conclude(explanation, change)
    explanation.unexplained = not any(
        line.tone in {"GREEN", "RED", "ORANGE"} for line in explanation.lines
    )
    return explanation


def _conclude(explanation: MarketExplanation, change: float | None) -> str:
    """One sentence that names what is confirmed and what is not."""

    supports = [line for line in explanation.lines if line.tone == "GREEN"]
    against = [line for line in explanation.lines if line.tone == "RED"]
    unclear = [line for line in explanation.lines if line.tone in {"ORANGE", "YELLOW", "WHITE"}]
    move = "" if change is None else f"({fr_number(change, 1, signed=True)} % sur 7 jours) "
    if explanation.direction == "UP":
        if len(supports) >= 3 and not against:
            return (
                f"Hausse {move}soutenue par plusieurs familles indépendantes. Cela ne vaut "
                "pas signal d'achat : la décision garde ses propres conditions."
            )
        if against:
            return (
                f"Hausse {move}réelle mais incomplètement confirmée : "
                + ", ".join(line.title.lower() for line in against[:2]) + "."
            )
        return f"Hausse {move}encore peu confirmée : {len(unclear)} familles restent ambiguës."
    if explanation.direction == "DOWN":
        if len(against) >= 2:
            return f"Baisse {move}cohérente avec " + ", ".join(
                line.title.lower() for line in against[:2]) + "."
        return f"Baisse {move}sans explication dominante identifiée."
    return f"Marché sans direction nette {move}: aucune famille ne domine."
