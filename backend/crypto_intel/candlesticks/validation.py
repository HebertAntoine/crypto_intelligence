"""Une figure correctement reconnue apporte-t-elle une information ?

C'est une question **différente** de celles déjà tranchées, et les confondre
serait l'erreur principale que ce module existe pour éviter :

* la **fréquence d'apparition** — mesurée par le test de permutation. Elle dit
  si la forme est un produit de l'arithmétique. Elle ne dit rien de la suite.
* la **validité de reconnaissance** — la bougie correspond-elle à sa
  définition. Vérifiée par les tests de forme.
* l'**avantage prédictif** — ce que le prix fait ensuite. C'est ici, et
  seulement ici.

Trois précautions gouvernent la mesure.

**Comparer à ce qu'il faut.** Un marteau apparaît par définition après une
baisse. Comparer ses rendements à ceux de toutes les bougies du marché
mesurerait surtout le rebond qui suit une baisse — un effet réel, mais qui
n'appartient pas au marteau. Chaque occurrence est donc appariée à des
situations **comparables sans la figure** : même actif, même unité, même
régime de volatilité, même direction et même ampleur de tendance préalable.

**Choisir le sens avant de regarder.** `EXPECTED_DIRECTION` est déclaré dans la
taxonomie, hors de ce module. Lire un rendement négatif après un marteau comme
« la figure marche à l'envers » reviendrait à choisir l'hypothèse après avoir
vu le résultat.

**Le futur ne sert qu'à l'évaluation.** Aucune valeur calculée ici n'entre dans
la reconnaissance. Les rendements sont mesurés strictement APRÈS la barre de
détection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..logging_setup import get_logger
from ..research.stats import benjamini_hochberg, excursions, forward_returns
from ..structure.patterns import PatternEdgeState
from .taxonomy import EXPECTED_DIRECTION, CandlestickPattern

log = get_logger("candlesticks.validation")

#: Horizons mesurés, en barres.
HORIZONS = (1, 3, 5, 10, 20)

#: Combien de contrôles appariés on cherche par occurrence.
CONTROLS_PER_EVENT = 10

#: Tolérances d'appariement. Deux situations sont « comparables » quand leur
#: volatilité et leur tendance préalable se ressemblent à cette précision.
#:
#: Ce sont des choix. Trop serré, on ne trouve aucun contrôle; trop lâche, on
#: compare un marteau après -3 ATR à une bougie quelconque après -0,2 ATR, et
#: la différence mesurée est celle des contextes, pas celle des figures.
ATR_PERCENTILE_TOLERANCE = 0.15
TREND_TOLERANCE_ATR = 0.5

#: Seuils de taille d'échantillon. Un résultat très net sur sept cas n'est pas
#: un résultat.
INSUFFICIENT_BELOW = 30
EXPLORATORY_BELOW = 100

#: Niveau de la correction pour tests multiples.
FDR_ALPHA = 0.05


@dataclass(slots=True)
class HorizonResult:
    """Ce qu'on observe à un horizon donné, figure contre contrôles."""

    horizon: int
    n_events: int
    n_controls: int
    event_mean: float | None = None
    event_median: float | None = None
    control_mean: float | None = None
    control_median: float | None = None
    difference: float | None = None
    effect_size: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    survives_fdr: bool = False
    event_mfe: float | None = None
    event_mae: float | None = None
    control_mfe: float | None = None
    control_mae: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_bars": self.horizon,
            "n_events": self.n_events,
            "n_controls": self.n_controls,
            "event_mean_pct": self.event_mean,
            "event_median_pct": self.event_median,
            "control_mean_pct": self.control_mean,
            "control_median_pct": self.control_median,
            "difference_pct": self.difference,
            "effect_size_cohens_d": self.effect_size,
            "ci95_low": self.ci_low,
            "ci95_high": self.ci_high,
            "p_value": self.p_value,
            "survives_fdr": self.survives_fdr,
            "event_mfe_pct": self.event_mfe,
            "event_mae_pct": self.event_mae,
            "control_mfe_pct": self.control_mfe,
            "control_mae_pct": self.control_mae,
        }


@dataclass(slots=True)
class PatternEvidence:
    """Le dossier complet d'une figure, sur un actif et une unité."""

    pattern: str
    symbol: str
    timeframe: str
    detector_version: str
    expected_direction: int
    n_occurrences: int
    horizons: list[HorizonResult] = field(default_factory=list)
    edge_state: PatternEdgeState = PatternEdgeState.NOT_YET_TESTED
    sample_status: str = "INSUFFICIENT_DATA"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "taxonomy": "CANDLESTICK_PATTERN",
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "detector_version": self.detector_version,
            "expected_direction": self.expected_direction,
            "n_occurrences": self.n_occurrences,
            "sample_status": self.sample_status,
            "edge_state": self.edge_state.value,
            "horizons": [h.to_dict() for h in self.horizons],
            "note": self.note,
        }


def _sample_status(n: int) -> str:
    if n < INSUFFICIENT_BELOW:
        return "INSUFFICIENT_DATA"
    if n < EXPLORATORY_BELOW:
        return "EXPLORATORY"
    return "TESTABLE"


def build_context_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Les variables d'appariement, calculées pour chaque barre.

    Toutes causales: elles ne décrivent que ce qui précède la barre. Un
    appariement qui utiliserait le futur choisirait des contrôles en fonction
    de leur résultat, ce qui inverserait la question posée.
    """
    from ..engines.technical import indicators as ind
    from .anatomy import TREND_LOOKBACK

    atr = ind.atr(frame["high"], frame["low"], frame["close"], 14)
    close = frame["close"]
    context = pd.DataFrame(index=frame.index)
    context["atr"] = atr
    # Percentile glissant de l'ATR: « quel régime de volatilité », sans
    # utiliser la distribution complète, qui contiendrait l'avenir.
    context["atr_percentile"] = atr.rolling(250, min_periods=50).rank(pct=True)
    prior = (close.shift(1) - close.shift(1 + TREND_LOOKBACK)) / atr
    context["trend_atr"] = prior
    return context


def _matched_controls(
    context: pd.DataFrame,
    event_positions: set[int],
    position: int,
    rng: np.random.Generator,
    wanted: int = CONTROLS_PER_EVENT,
) -> list[int]:
    """Des barres comparables, sans la figure.

    L'appariement se fait sur le régime de volatilité et sur la tendance
    préalable — les deux variables qui, laissées libres, expliqueraient à elles
    seules l'essentiel d'une différence de rendement.

    Les barres portant une figure sont exclues du vivier: un contrôle qui est
    lui-même un marteau ne contrôle rien.
    """
    row = context.iloc[position]
    atr_pct, trend = row["atr_percentile"], row["trend_atr"]
    if not np.isfinite(atr_pct) or not np.isfinite(trend):
        return []

    candidates = context.index[
        (context["atr_percentile"] - atr_pct).abs().le(ATR_PERCENTILE_TOLERANCE)
        & (context["trend_atr"] - trend).abs().le(TREND_TOLERANCE_ATR)
    ]
    positions = [
        context.index.get_loc(when) for when in candidates
    ]
    pool = [p for p in positions if p != position and p not in event_positions]
    if not pool:
        return []
    if len(pool) <= wanted:
        return pool
    return list(rng.choice(pool, size=wanted, replace=False))


def evaluate_pattern(
    frame: pd.DataFrame,
    detections: list[Any],
    pattern: CandlestickPattern,
    symbol: str,
    timeframe: str,
    detector_version: str,
    seed: int = 20260909,
) -> PatternEvidence:
    """Le dossier d'une figure: ses rendements contre ceux de ses contrôles."""
    direction = EXPECTED_DIRECTION.get(pattern, 0)
    occurrences = [d for d in detections if d.pattern is pattern]
    evidence = PatternEvidence(
        pattern=pattern.value, symbol=symbol, timeframe=timeframe,
        detector_version=detector_version, expected_direction=direction,
        n_occurrences=len(occurrences),
        sample_status=_sample_status(len(occurrences)),
    )
    if direction == 0:
        evidence.note = (
            "Indecision figure: theory attributes no direction, so a "
            "directional return would have no meaning. Not evaluated."
        )
        return evidence
    if not occurrences:
        return evidence

    context = build_context_frame(frame)
    returns = forward_returns(frame["close"], list(HORIZONS))
    positions = {
        frame.index.get_loc(d.detected_at) for d in occurrences
        if d.detected_at in frame.index
    }
    all_event_positions = {
        frame.index.get_loc(d.detected_at) for d in detections
        if d.detected_at in frame.index
    }
    rng = np.random.default_rng(seed)

    control_positions: list[int] = []
    for position in sorted(positions):
        control_positions.extend(
            _matched_controls(context, all_event_positions, position, rng)
        )

    for horizon in HORIZONS:
        column = returns[f"fwd_{horizon}"].to_numpy()
        mfe, mae = excursions(frame["high"], frame["low"], frame["close"], horizon)
        event_vals = _directional(column, sorted(positions), direction)
        control_vals = _directional(column, control_positions, direction)
        result = HorizonResult(
            horizon=horizon,
            n_events=len(event_vals), n_controls=len(control_vals),
        )
        if len(event_vals) >= 2 and len(control_vals) >= 2:
            _fill(result, event_vals, control_vals)
            result.event_mfe = _mean_at(mfe, sorted(positions))
            result.event_mae = _mean_at(mae, sorted(positions))
            result.control_mfe = _mean_at(mfe, control_positions)
            result.control_mae = _mean_at(mae, control_positions)
        evidence.horizons.append(result)

    _apply_fdr(evidence)
    evidence.edge_state = _edge_state(evidence)
    return evidence


def _directional(column: np.ndarray, positions: list[int], direction: int) -> np.ndarray:
    """Les rendements, orientés dans le sens que la théorie annonce.

    Multiplier par le signe attendu permet de comparer une figure haussière et
    une figure baissière sur la même échelle: positif veut dire « la théorie a
    eu raison », dans les deux cas.
    """
    values = [column[p] * direction for p in positions if p < len(column)]
    array = np.array(values, dtype=float)
    return array[np.isfinite(array)]


def _mean_at(series: pd.Series, positions: list[int]) -> float | None:
    values = [series.iloc[p] for p in positions if p < len(series)]
    finite = [v for v in values if np.isfinite(v)]
    return round(float(np.mean(finite)), 4) if finite else None


def _fill(result: HorizonResult, events: np.ndarray, controls: np.ndarray) -> None:
    result.event_mean = round(float(np.mean(events)), 4)
    result.event_median = round(float(np.median(events)), 4)
    result.control_mean = round(float(np.mean(controls)), 4)
    result.control_median = round(float(np.median(controls)), 4)
    result.difference = round(result.event_mean - result.control_mean, 4)

    # Welch: les deux échantillons n'ont ni la même taille ni la même variance.
    _, p_value = stats.ttest_ind(events, controls, equal_var=False)
    result.p_value = round(float(p_value), 6) if np.isfinite(p_value) else None

    pooled = np.sqrt((np.var(events, ddof=1) + np.var(controls, ddof=1)) / 2)
    if pooled > 0:
        result.effect_size = round(float(result.difference / pooled), 4)

    # Intervalle sur la DIFFÉRENCE, pas sur la moyenne de l'événement: c'est la
    # différence qui répond à la question posée.
    se = np.sqrt(
        np.var(events, ddof=1) / len(events) + np.var(controls, ddof=1) / len(controls)
    )
    if np.isfinite(se) and se > 0:
        margin = 1.96 * se
        result.ci_low = round(float(result.difference - margin), 4)
        result.ci_high = round(float(result.difference + margin), 4)


def _apply_fdr(evidence: PatternEvidence) -> None:
    """Correction pour tests multiples, au sein d'une figure.

    La correction globale — toutes figures, tous actifs, toutes unités — est
    appliquée par l'orchestrateur, qui seul voit l'ensemble des tests.
    """
    p_values = [h.p_value for h in evidence.horizons]
    for horizon, survives in zip(
        evidence.horizons, benjamini_hochberg(p_values, FDR_ALPHA), strict=True
    ):
        horizon.survives_fdr = survives


def _edge_state(evidence: PatternEvidence) -> PatternEdgeState:
    """L'état d'avantage, à partir de ce qui a été mesuré.

    Réutilise l'énumération du projet plutôt que d'en créer une: elle couvre
    déjà exactement ces cas.
    """
    if evidence.sample_status == "INSUFFICIENT_DATA":
        return PatternEdgeState.INSUFFICIENT_DATA
    surviving = [
        h.difference for h in evidence.horizons
        if h.survives_fdr and h.difference is not None
    ]
    if not surviving:
        return PatternEdgeState.NO_MEASURABLE_EDGE
    signs = {1 if value > 0 else -1 if value < 0 else 0 for value in surviving}
    if len(signs) > 1:
        # Des horizons qui se contredisent ne décrivent pas un avantage.
        return PatternEdgeState.UNSTABLE
    positive = surviving[0] > 0
    if evidence.sample_status == "EXPLORATORY":
        # Assez pour regarder, pas assez pour conclure.
        return PatternEdgeState.INSUFFICIENT_DATA
    return PatternEdgeState.POSITIVE_EDGE if positive else PatternEdgeState.NEGATIVE_EDGE


# --- hors-échantillon et correction globale --------------------------------
#
# Les seuils de `candlestick_v1` sont gelés: rien n'est réglé sur ces
# résultats. Le découpage chronologique ne sert donc pas à choisir des
# paramètres mais à répondre à une question plus simple et plus dure: le signe
# observé sur la période ancienne tient-il sur la période récente ?
#
# Une figure dont l'effet s'inverse entre les deux n'a pas d'avantage; elle a
# une coïncidence.

#: Part de l'historique réservée à chaque fenêtre.
TRAIN_SHARE = 0.50
VALIDATION_SHARE = 0.25


@dataclass(slots=True)
class WalkForwardResult:
    """La même figure, mesurée sur trois périodes disjointes."""

    pattern: str
    symbol: str
    timeframe: str
    horizon: int
    train: float | None = None
    validation: float | None = None
    test: float | None = None
    n_train: int = 0
    n_validation: int = 0
    n_test: int = 0

    @property
    def sign_holds(self) -> bool | None:
        """Le signe est-il le même sur les trois fenêtres ?

        `None` quand une fenêtre est vide: on ne peut pas dire qu'un signe
        tient si on ne l'a pas observé.
        """
        values = [self.train, self.validation, self.test]
        if any(v is None for v in values):
            return None
        signs = {np.sign(v) for v in values if v is not None}
        return len(signs) == 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern, "symbol": self.symbol,
            "timeframe": self.timeframe, "horizon_bars": self.horizon,
            "train_mean_pct": self.train, "n_train": self.n_train,
            "validation_mean_pct": self.validation, "n_validation": self.n_validation,
            "test_mean_pct": self.test, "n_test": self.n_test,
            "sign_holds_out_of_sample": self.sign_holds,
        }


def walk_forward(
    frame: pd.DataFrame,
    detections: list[Any],
    pattern: CandlestickPattern,
    symbol: str,
    timeframe: str,
    horizon: int,
) -> WalkForwardResult:
    """Le rendement directionnel de la figure, par tranche chronologique."""
    direction = EXPECTED_DIRECTION.get(pattern, 0)
    result = WalkForwardResult(
        pattern=pattern.value, symbol=symbol, timeframe=timeframe, horizon=horizon
    )
    if direction == 0 or frame.empty:
        return result

    column = forward_returns(frame["close"], [horizon])[f"fwd_{horizon}"].to_numpy()
    positions = sorted(
        frame.index.get_loc(d.detected_at)
        for d in detections
        if d.pattern is pattern and d.detected_at in frame.index
    )
    n = len(frame)
    train_end = int(n * TRAIN_SHARE)
    validation_end = int(n * (TRAIN_SHARE + VALIDATION_SHARE))

    windows = {
        "train": [p for p in positions if p < train_end],
        "validation": [p for p in positions if train_end <= p < validation_end],
        "test": [p for p in positions if p >= validation_end],
    }
    for name, group in windows.items():
        values = _directional(column, group, direction)
        setattr(result, f"n_{name}", len(values))
        if len(values) >= 2:
            setattr(result, name, round(float(np.mean(values)), 4))
    return result


def apply_global_fdr(all_evidence: list[PatternEvidence], alpha: float = FDR_ALPHA) -> None:
    """Correction sur l'ENSEMBLE des tests, toutes figures confondues.

    Vingt figures, cinq horizons, trois actifs, cinq unités: plusieurs
    centaines de tests. Corriger figure par figure laisserait passer, par
    construction, une poignée de faux positifs — et ce sont exactement ceux
    qu'on aurait envie de retenir.
    """
    flat: list[tuple[HorizonResult, float | None]] = [
        (horizon, horizon.p_value)
        for evidence in all_evidence
        for horizon in evidence.horizons
    ]
    verdicts = benjamini_hochberg([p for _, p in flat], alpha)
    for (horizon, _), survives in zip(flat, verdicts, strict=True):
        horizon.survives_fdr = survives
    for evidence in all_evidence:
        evidence.edge_state = _edge_state(evidence)
