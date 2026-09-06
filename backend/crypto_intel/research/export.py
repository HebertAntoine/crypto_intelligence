"""Research export: CSV, JSON and Markdown.

Everything that matters travels together - effect size, sample size, p-value,
FDR-corrected significance, out-of-sample behaviour, stability and verdict. A
number without its sample size is not a result, so the exporter never emits one
without the other.

Negative findings are exported alongside positive ones.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..logging_setup import get_logger
from ..settings import get_settings

log = get_logger("research.export")

CSV_COLUMNS = [
    "study", "asset", "signal", "horizon", "split",
    "effect", "effect_type", "n",
    "p_value", "significant_raw", "significant_fdr",
    "stability_score", "monotonic", "oos_stable", "verdict", "note",
]


def flatten_results(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the nested research bundle into flat, exportable rows."""
    rows: list[dict[str, Any]] = []

    # --- score audit -------------------------------------------------------
    for asset_value, asset_result in (bundle.get("audit", {}).get("assets") or {}).items():
        for domain, result in (asset_result.get("domains") or {}).items():
            decomposition = result.get("ic_decomposition") or {}
            rows.append({
                "study": "score_audit", "asset": asset_value, "signal": domain,
                "horizon": result.get("horizon", "7d"), "split": "full",
                "effect": result.get("ic"), "effect_type": "spearman_ic",
                "n": result.get("n", 0),
                "p_value": result.get("p_value"),
                "significant_raw": result.get("significant"),
                "significant_fdr": None,
                "stability_score": result.get("stability_score"),
                "monotonic": result.get("monotonic"),
                "oos_stable": result.get("sign_stable_across_splits"),
                "verdict": result.get("verdict"),
                "note": (
                    f"within-period IC {decomposition.get('mean_within_ic')}"
                    if decomposition.get("assessable") else result.get("reason", "")
                )[:220],
            })

    # --- ETF lag -----------------------------------------------------------
    for asset_value, lag in (bundle.get("etf_lag") or {}).items():
        if not lag.get("available"):
            continue
        for signal, horizons in (lag.get("correlations") or {}).items():
            for horizon, cell in horizons.items():
                rows.append({
                    "study": "etf_lag", "asset": asset_value, "signal": signal,
                    "horizon": horizon, "split": "full",
                    "effect": cell.get("spearman_r"), "effect_type": "spearman_ic",
                    "n": cell.get("n", 0),
                    "p_value": cell.get("p_value"),
                    "significant_raw": cell.get("significant_raw"),
                    "significant_fdr": cell.get("significant"),
                    "stability_score": None, "monotonic": None, "oos_stable": None,
                    "verdict": "USEFUL" if cell.get("significant") else "NO_MEASURABLE_VALUE",
                    "note": "",
                })

    # --- ETF asymmetry ------------------------------------------------------
    for asset_value, asym in (bundle.get("etf_asymmetry") or {}).items():
        if not asym.get("available"):
            continue
        for category, entry in (asym.get("categories") or {}).items():
            if not entry.get("available"):
                continue
            for horizon, cell in entry["horizons"].items():
                rows.append({
                    "study": "etf_asymmetry", "asset": asset_value,
                    "signal": category, "horizon": horizon, "split": "full",
                    "effect": cell.get("edge_vs_baseline"), "effect_type": "edge_vs_baseline_pp",
                    "n": cell.get("n", 0),
                    "p_value": cell.get("p_value"),
                    "significant_raw": cell.get("significant"),
                    "significant_fdr": cell.get("significant_fdr"),
                    "stability_score": None, "monotonic": None,
                    "oos_stable": cell.get("ci_excludes_zero"),
                    "verdict": (
                        "USEFUL" if cell.get("significant_fdr")
                        else "WEAK" if cell.get("ci_excludes_zero")
                        else "NO_MEASURABLE_VALUE"
                    ),
                    "note": f"win {cell.get('win_rate')}%, MFE {cell.get('mfe_median')}, "
                            f"MAE {cell.get('mae_median')}",
                })
        comparison = asym.get("asymmetry") or {}
        if comparison.get("assessable"):
            rows.append({
                "study": "etf_asymmetry", "asset": asset_value,
                "signal": "tail_comparison", "horizon": "all", "split": "full",
                "effect": None, "effect_type": "verdict", "n": 0,
                "p_value": None, "significant_raw": None, "significant_fdr": None,
                "stability_score": None, "monotonic": None, "oos_stable": None,
                "verdict": comparison.get("verdict"),
                "note": comparison.get("conclusion", "")[:220],
            })

    # --- derivatives bands ---------------------------------------------------
    for asset_value, data in (bundle.get("derivatives") or {}).items():
        bands = data.get("percentile_bands") or {}
        if not bands.get("available"):
            continue
        for band_name, band in (bands.get("bands") or {}).items():
            if not band.get("available"):
                continue
            for horizon, cell in band["horizons"].items():
                rows.append({
                    "study": "derivatives_bands", "asset": asset_value,
                    "signal": f"funding:{band_name}", "horizon": horizon, "split": "full",
                    "effect": cell.get("edge_vs_baseline"), "effect_type": "edge_vs_baseline_pp",
                    "n": cell.get("n", 0),
                    "p_value": cell.get("p_value"),
                    "significant_raw": cell.get("significant"),
                    "significant_fdr": cell.get("significant_fdr"),
                    "stability_score": None, "monotonic": None, "oos_stable": None,
                    "verdict": (
                        "WEAK" if cell.get("significant_fdr") else "NO_MEASURABLE_VALUE"
                    ),
                    "note": f"win {cell.get('win_rate')}%",
                })

    # --- regime-conditioned --------------------------------------------------
    for asset_value, data in (bundle.get("regime_conditioned") or {}).items():
        if not data.get("available"):
            continue
        for signal_name, result in (data.get("signals") or {}).items():
            if not result.get("available"):
                continue
            for regime, cell in (result.get("by_regime") or {}).items():
                if not cell.get("available"):
                    continue
                stats = cell.get("signal") or {}
                rows.append({
                    "study": "regime_conditioned", "asset": asset_value,
                    "signal": f"{signal_name}@{regime}", "horizon": result.get("horizon", "7d"),
                    "split": "full",
                    "effect": cell.get("edge_vs_regime"), "effect_type": "edge_vs_regime_pp",
                    "n": cell.get("n", 0),
                    "p_value": stats.get("p_value"),
                    "significant_raw": stats.get("significant"),
                    "significant_fdr": cell.get("significant_fdr"),
                    "stability_score": None, "monotonic": None, "oos_stable": None,
                    "verdict": (
                        "USEFUL" if cell.get("significant_fdr") else "WEAK"
                    ),
                    "note": f"win {stats.get('win_rate')}%",
                })

    # --- feature importance ---------------------------------------------------
    for asset_value, features in (bundle.get("features") or {}).items():
        if not features.get("available"):
            continue
        for entry in features.get("ranking", []):
            rows.append({
                "study": "feature_importance", "asset": asset_value,
                "signal": entry["feature"], "horizon": "7d", "split": "walk_forward",
                "effect": entry.get("ic_7d"), "effect_type": "spearman_ic",
                "n": entry.get("n", 0),
                "p_value": entry.get("p_value_7d"),
                "significant_raw": None,
                "significant_fdr": entry.get("significant_fdr"),
                "stability_score": entry.get("stability_score"),
                "monotonic": entry.get("monotonic_7d"),
                "oos_stable": entry.get("stability_verdict") != "UNSTABLE",
                "verdict": entry.get("verdict"),
                "note": f"usefulness {entry.get('usefulness')}",
            })

    # --- champion vs challenger ------------------------------------------------
    for asset_value, comparison in (bundle.get("champion_challenger") or {}).items():
        if not comparison.get("available"):
            continue
        summary = comparison["summary"]
        rows.append({
            "study": "champion_challenger", "asset": asset_value,
            "signal": "composite", "horizon": "7d", "split": "oos_walk_forward",
            "effect": summary.get("challenger_mean_oos_ic"), "effect_type": "mean_oos_ic",
            "n": summary.get("windows", 0),
            "p_value": None, "significant_raw": None, "significant_fdr": None,
            "stability_score": None, "monotonic": summary.get("challenger_monotonic"),
            "oos_stable": None,
            "verdict": comparison.get("verdict"),
            "note": (
                f"champion {summary.get('champion_mean_oos_ic')} "
                f"({summary.get('champion_wins')} wins) vs challenger "
                f"({summary.get('challenger_wins')} wins)"
            )[:220],
        })

    return rows


def export_csv(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def export_json(bundle: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    return path


def export_markdown(bundle: dict[str, Any], rows: list[dict[str, Any]], path: Path) -> Path:
    """Human-readable summary, negative findings included."""
    lines: list[str] = []
    add = lines.append

    add("# Crypto Intelligence — résultats de recherche")
    add("")
    add(f"Généré le {datetime.now(UTC):%Y-%m-%d %H:%M} UTC")
    add("")
    add("> Tous les résultats sont des descriptions historiques, pas des prédictions. "
        "Un effet est accompagné de sa taille d'échantillon ; sans elle il ne veut rien dire.")
    add("")

    # --- verdicts summary --------------------------------------------------
    add("## Verdicts par actif")
    add("")
    audit = bundle.get("audit", {}).get("assets") or {}
    for asset_value, asset_result in audit.items():
        summary = asset_result.get("summary", {})
        add(f"### {asset_value}")
        add("")
        add("| Domaine | Poids | n | IC 7j | Monotone | Stabilité | Verdict |")
        add("|---|---:|---:|---:|:---:|---:|---|")
        for domain, result in (asset_result.get("domains") or {}).items():
            ic = result.get("ic")
            add(
                f"| {domain} | {result.get('current_weight', 0):.2f} | "
                f"{result.get('n', 0)} | "
                f"{ic:+.3f} | " if ic is not None else
                f"| {domain} | {result.get('current_weight', 0):.2f} | "
                f"{result.get('n', 0)} | — | "
            )
        add("")
        add(f"- Poids sur des domaines **USEFUL** : {summary.get('weight_on_useful', 0):.2f}")
        add(f"- Poids sur des domaines sans valeur mesurable ou instables : "
            f"{summary.get('weight_on_worthless_or_unstable', 0):.2f}")
        add(f"- Poids non mesurable : {summary.get('weight_on_unmeasured', 0):.2f}")
        add("")

    # --- what survives -------------------------------------------------------
    add("## Ce qui survit à la correction pour comparaisons multiples")
    add("")
    survivors = [r for r in rows if r.get("significant_fdr")]
    if survivors:
        add("| Étude | Actif | Signal | Horizon | Effet | n |")
        add("|---|---|---|---|---:|---:|")
        for r in sorted(survivors, key=lambda x: -abs(x.get("effect") or 0))[:30]:
            effect = r.get("effect")
            add(
                f"| {r['study']} | {r['asset']} | {r['signal']} | {r['horizon']} | "
                f"{effect:+.3f} | {r['n']} |" if effect is not None else
                f"| {r['study']} | {r['asset']} | {r['signal']} | {r['horizon']} | — | {r['n']} |"
            )
    else:
        add("Aucun résultat ne survit à la correction FDR.")
    add("")

    # --- negative findings ---------------------------------------------------
    add("## Signaux sans valeur mesurable")
    add("")
    useless = [r for r in rows if r.get("verdict") == "NO_MEASURABLE_VALUE"]
    add(f"{len(useless)} résultat(s) sur {len(rows)} sont classés sans valeur mesurable.")
    add("")
    seen: set[str] = set()
    for r in useless[:25]:
        key = f"{r['asset']}:{r['signal']}"
        if key in seen:
            continue
        seen.add(key)
        add(f"- **{r['asset']} {r['signal']}** ({r['study']}, n={r['n']}) — {r.get('note', '')[:110]}")
    add("")

    # --- champion vs challenger ----------------------------------------------
    add("## Champion vs Challenger")
    add("")
    for asset_value, comparison in (bundle.get("champion_challenger") or {}).items():
        if not comparison.get("available"):
            add(f"- **{asset_value}** : {comparison.get('reason', 'non évalué')}")
            continue
        add(f"- **{asset_value}** : `{comparison['verdict']}` — {comparison['reason']}")
    add("")
    add("> La promotion d'un challenger est une décision humaine. Aucun code "
        "n'applique automatiquement `config/scoring_candidate.yaml`.")
    add("")

    # --- limitations ----------------------------------------------------------
    add("## Limites")
    add("")
    add("Voir `docs/data-limitations.md`. Les principales :")
    add("")
    add("- Une seule histoire du Bitcoin : les fenêtres hors échantillon ne sont pas indépendantes.")
    add("- Open interest limité à ~30 jours par la source.")
    add("- Flux ETF disponibles depuis 2024 seulement, une seule phase de marché.")
    add("- Séries macro révisées : la valeur d'origine n'est pas reconstituable ici.")
    add("- Scores reconstruits : mesurent la logique actuelle, pas ce que le système aurait dit.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_all(bundle: dict[str, Any], directory: Path | None = None) -> dict[str, str]:
    """Write all three formats and return their paths."""
    settings = get_settings()
    directory = directory or (settings.data_dir / "research")
    directory.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
    rows = flatten_results(bundle)

    paths = {
        "csv": str(export_csv(rows, directory / f"research_{stamp}.csv")),
        "json": str(export_json(bundle, directory / f"research_{stamp}.json")),
        "markdown": str(export_markdown(bundle, rows, directory / f"research_{stamp}.md")),
        "csv_latest": str(export_csv(rows, directory / "research_latest.csv")),
        "markdown_latest": str(
            export_markdown(bundle, rows, directory / "research_latest.md")
        ),
    }
    log.info("research_exported", rows=len(rows), directory=str(directory))
    return {**paths, "rows": str(len(rows))}
