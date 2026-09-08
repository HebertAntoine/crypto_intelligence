"""L'état réel de chaque source, actif par actif, sans interprétation.

Une page correcte suppose des données à jour, et rien ne le vérifiait. Les
séries de funding et d'open interest étaient profondes — sept mille points,
deux mille points — et immobiles depuis un jour : la profondeur n'est pas la
fraîcheur, et aucun contrôle ne faisait la différence.

Ce module répond à une seule question par source : est-elle utilisable
maintenant, et sinon pourquoi. Il ne calcule rien d'analytique et ne masque
rien : `NOT_APPLICABLE` et `UNAVAILABLE` restent deux réponses distinctes,
parce qu'une absence structurelle n'est pas une panne.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..core.enums import Asset, Timeframe


class HealthStatus(StrEnum):
    OK = "OK"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ERROR = "ERROR"


@dataclass(slots=True)
class SourceHealth:
    source: str
    asset: str | None
    status: HealthStatus
    rows: int = 0
    latest: datetime | None = None
    age_hours: float | None = None
    history_days: float | None = None
    expected_every_hours: float | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "asset": self.asset,
            "status": self.status.value, "rows": self.rows,
            "latest": self.latest.isoformat() if self.latest else None,
            "age_hours": (
                None if self.age_hours is None else round(self.age_hours, 1)
            ),
            "history_days": self.history_days,
            "expected_every_hours": self.expected_every_hours,
            "detail": self.detail,
        }


# Cadence de publication réelle de chaque source, en heures. C'est contre elle
# qu'une série est jugée, pas contre une horloge unique: un flux ETF de six
# heures est normal, un prix spot de six minutes ne l'est pas.
_SERIES: dict[str, tuple[str, float]] = {
    "funding.rate": ("FUNDING", 8.0),
    "oi.contracts_bybit": ("OPEN_INTEREST", 24.0),
    "spot.taker_buy_ratio": ("SPOT", 24.0),
    "derivatives.long_account_share": ("ACCOUNTS", 4.0),
    "dvol.index": ("DVOL", 24.0),
}

# Ce qui n'existe pas pour un actif, et pourquoi.
_NOT_APPLICABLE: dict[tuple[str, str], str] = {
    ("SOL", "DVOL"): "Deribit ne publie pas d'indice DVOL pour SOL",
    ("SOL", "ETF"): "aucun ETF spot SOL n'est listé sur les marchés suivis",
}


def _classify(
    latest: datetime | None, cadence_hours: float, rows: int, tolerance: float = 2.5
) -> tuple[HealthStatus, float | None]:
    if latest is None or rows == 0:
        return HealthStatus.UNAVAILABLE, None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - latest).total_seconds() / 3600
    if age < -0.25:
        return HealthStatus.ERROR, age
    return (
        HealthStatus.OK if age <= cadence_hours * tolerance else HealthStatus.STALE
    ), age


def check(asset: Asset) -> list[SourceHealth]:
    """Chaque source qui alimente la page, pour un actif."""
    from ..db import repo
    from ..history import store

    out: list[SourceHealth] = []

    for timeframe, cadence in (
        (Timeframe.D1, 24.0), (Timeframe.H4, 4.0), (Timeframe.H1, 1.0),
    ):
        coverage = store.candle_coverage(asset, timeframe)
        status, age = _classify(coverage.get("end"), cadence, coverage.get("rows", 0))
        out.append(SourceHealth(
            source=f"OHLCV_{timeframe.value.upper()}", asset=asset.value,
            status=status, rows=coverage.get("rows", 0), latest=coverage.get("end"),
            age_hours=age, history_days=coverage.get("days"),
            expected_every_hours=cadence,
        ))

    derivatives = store.derivatives_coverage(asset)
    for metric, (label, cadence) in _SERIES.items():
        reason = _NOT_APPLICABLE.get((asset.value, label))
        if reason:
            out.append(SourceHealth(
                source=label, asset=asset.value,
                status=HealthStatus.NOT_APPLICABLE, detail=reason,
            ))
            continue
        entry = derivatives.get(metric) or {}
        status, age = _classify(entry.get("end"), cadence, entry.get("rows", 0))
        out.append(SourceHealth(
            source=label, asset=asset.value, status=status,
            rows=entry.get("rows", 0), latest=entry.get("end"), age_hours=age,
            history_days=entry.get("days"), expected_every_hours=cadence,
            detail="" if status is not HealthStatus.UNAVAILABLE
            else f"aucune ligne pour {metric}",
        ))

    reason = _NOT_APPLICABLE.get((asset.value, "ETF"))
    if reason:
        out.append(SourceHealth(
            source="ETF", asset=asset.value,
            status=HealthStatus.NOT_APPLICABLE, detail=reason,
        ))
    else:
        rows = repo.get_etf_flows(asset, days=400)
        latest = max((row["date"] for row in rows), default=None)
        # Publié une fois par séance de bourse; le week-end n'est pas une panne.
        status, age = _classify(latest, 24.0, len(rows), tolerance=4.0)
        out.append(SourceHealth(
            source="ETF", asset=asset.value, status=status, rows=len(rows),
            latest=latest, age_hours=age, expected_every_hours=24.0,
        ))

    observations = repo.observation_fingerprint(asset)
    for key, label, cadence in (
        ("observations:onchain.", "ONCHAIN", 24.0),
        ("observations:whale.", "WHALES", 24.0),
        ("observations:macro.", "MACRO", 168.0),
    ):
        rows, last = observations.get(key, [0, None])
        latest = datetime.fromisoformat(last) if last else None
        status, age = _classify(latest, cadence, rows)
        detail = ""
        if label == "WHALES" and status is HealthStatus.UNAVAILABLE:
            detail = (
                "aucun fournisseur d'attribution d'adresses configuré; "
                "cette source demande un abonnement payant"
            )
        out.append(SourceHealth(
            source=label, asset=asset.value, status=status, rows=rows,
            latest=latest, age_hours=age, expected_every_hours=cadence,
            detail=detail,
        ))
    return out


def report() -> dict[str, Any]:
    """L'état complet, pour la ligne de commande comme pour un endpoint."""
    assets = {asset.value: [item.to_dict() for item in check(asset)]
              for asset in Asset.tradables()}
    flat = [item for rows in assets.values() for item in rows]
    counts = {status.value: 0 for status in HealthStatus}
    for item in flat:
        counts[item["status"]] += 1
    # NOT_APPLICABLE n'est pas un défaut: il ne compte pas comme un manque.
    actionable = counts["STALE"] + counts["UNAVAILABLE"] + counts["ERROR"]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "assets": assets,
        "counts": counts,
        "healthy": actionable == 0,
        "note": (
            "NOT_APPLICABLE décrit une source qui n'existe pas pour cet actif; "
            "elle n'est jamais comptée comme une donnée manquante."
        ),
    }
