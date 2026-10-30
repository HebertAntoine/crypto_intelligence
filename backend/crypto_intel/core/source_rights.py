"""Read-time source-rights policy for retained observations.

Provider checks at collection time are necessary but not sufficient.  A row
can outlive a key, a contract or the adapter that created it, so every decision
path re-evaluates the current operator settings before using retained data.

The policy deliberately leaves rows in storage for audit.  It only decides
whether a row may contribute to a current analysis.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .data_integrity import is_production_label, label_tokens

_LEGACY_UNLICENSED_PROVIDERS = frozenset(
    {"yahoo", "yahoo_finance", "yahoo_backfill", "stooq"}
)
_FRED_THIRD_PARTY_SERIES = frozenset({"BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS"})
_FRED_THIRD_PARTY_METRICS = frozenset(
    {"macro.hy_spread", "macro.ig_spread", "macro.vix"}
)
_DENIED_LICENSE_STATUSES = frozenset(
    {"NOT_AUTHORIZED", "UNLICENSED", "EXPIRED", "REVOKED"}
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def source_is_admissible(
    metric: str,
    *,
    source: str,
    provider: str,
    source_url: str | None = None,
    meta: Mapping[str, Any] | None = None,
) -> bool:
    """Whether one retained row may enter a decision under current rights.

    Missing or non-production provenance fails closed.  Unknown *named*
    providers remain usable unless a rule below restricts them: this preserves
    authorised first-party feeds while keeping the policy focused on sources
    whose rights are known to require an explicit operator confirmation.
    """

    source = _text(source)
    provider = _text(provider)
    url = _text(source_url)
    if not source or not provider:
        return False
    if not is_production_label(source) or not is_production_label(provider):
        return False

    details = dict(meta or {})
    labels = {source.lower(), provider.lower(), url.lower()}
    tokens = set().union(*(label_tokens(label) for label in labels if label))

    if (
        labels & _LEGACY_UNLICENSED_PROVIDERS
        or tokens & {"yahoo", "stooq"}
        or "finance.yahoo." in url.lower()
        or "stooq." in url.lower()
    ):
        return False

    license_status = _text(details.get("license_status")).upper()
    if license_status in _DENIED_LICENSE_STATUSES:
        return False

    from ..settings import get_settings

    settings = get_settings()
    joined = " ".join(labels)
    is_coingecko = "coingecko" in joined or "coin gecko" in joined
    if is_coingecko and not (
        settings.coingecko_api_key.strip()
        and settings.coingecko_commercial_use_authorized
        and settings.coingecko_attribution_configured
    ):
        return False

    is_twelve = (
        "twelve_data" in labels
        or "twelvedata" in tokens
        or {"twelve", "data"} <= tokens
    )
    if is_twelve and not (
        settings.twelve_data_api_key.strip()
        and settings.twelve_data_redistribution_authorized
    ):
        return False

    series_id = _text(details.get("series_id")).upper()
    is_fred = "fred" in tokens or "fred.stlouisfed.org" in url.lower()
    if is_fred and not settings.fred_content_use_authorized:
        return False
    fred_third_party = is_fred and (
        series_id in _FRED_THIRD_PARTY_SERIES
        or metric in _FRED_THIRD_PARTY_METRICS
    )
    return not (
        fred_third_party and not settings.fred_third_party_redistribution_authorized
    )


def observation_is_admissible(observation: Any) -> bool:
    """Apply :func:`source_is_admissible` to an ``Observation``-shaped row."""

    try:
        provenance = observation.provenance
        meta = getattr(observation, "meta", {})
        if not isinstance(meta, Mapping):
            return False
        return source_is_admissible(
            str(observation.metric),
            source=_text(provenance.source),
            provider=_text(provenance.provider),
            source_url=getattr(provenance, "source_url", None),
            meta=meta,
        )
    except (AttributeError, TypeError, ValueError):
        return False


def record_is_admissible(metric: str, record: Mapping[str, Any]) -> bool:
    """Apply the same policy to a rich ``macro_series`` history record."""

    nested = record.get("meta")
    details = dict(nested) if isinstance(nested, Mapping) else {}
    for key in ("series_id", "license_status"):
        if record.get(key) is not None:
            details[key] = record[key]
    return source_is_admissible(
        metric,
        source=_text(record.get("source")),
        provider=_text(record.get("provider")),
        source_url=_text(record.get("source_url")) or None,
        meta=details,
    )


def rights_policy_fingerprint() -> dict[str, bool | str]:
    """Non-secret policy state included in analysis cache identities."""

    from ..settings import get_settings

    settings = get_settings()
    return {
        "version": "2026-10-28.1",
        "coingecko_commercial_use_authorized": (
            settings.coingecko_commercial_use_authorized
        ),
        "coingecko_key_configured": bool(settings.coingecko_api_key.strip()),
        "coingecko_attribution_configured": (
            settings.coingecko_attribution_configured
        ),
        "fred_third_party_redistribution_authorized": (
            settings.fred_third_party_redistribution_authorized
        ),
        "fred_content_use_authorized": settings.fred_content_use_authorized,
        "twelve_data_key_configured": bool(settings.twelve_data_api_key.strip()),
        "twelve_data_redistribution_authorized": (
            settings.twelve_data_redistribution_authorized
        ),
    }
