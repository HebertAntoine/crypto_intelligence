"""Lissage par régression à noyau, en deux variantes qui ne se confondent pas.

Lo, Mamaysky et Wang (2000) lissent la série par régression à noyau avant d'en
extraire les extrema. L'intérêt du lissage n'est pas cosmétique: il décide
quels sommets existent. Un lissage large ne voit que les grandes oscillations,
un lissage étroit voit chaque dent de scie — et donc chaque figure détectée
dépend du lissage autant que du prix.

**Deux variantes, et jamais l'une déguisée en l'autre.**

Le noyau du papier est **symétrique**: la valeur lissée en `t` moyenne des
observations situées avant *et après* `t`. C'est légitime pour une étude
historique, et impossible en direct — à l'instant `t`, les observations
postérieures n'existent pas.

La variante causale n'utilise donc que `s ≤ t`. Ce n'est pas le même filtre:
il est plus lent, décale les extrema, et en trouve moins. Décaler simplement
le résultat du filtre symétrique donnerait les mêmes extrema avec un retard
apparent — et ce serait un mensonge, parce que ces extrema n'auraient pas pu
être calculés à ce moment-là.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# Beyond six standard deviations a Gaussian weight is below 1.6e-8. Keeping
# those terms made the causal filter O(n²) without changing a quoted score.
GAUSSIAN_CUTOFF_SIGMAS = 6.0


def _gaussian_weights(
    distance: NDArray[np.float64], bandwidth: float
) -> NDArray[np.float64]:
    """Noyau gaussien. Le facteur constant se simplifie dans la normalisation."""
    return np.exp(-0.5 * (distance / bandwidth) ** 2)


def kernel_smooth(
    values: NDArray[np.float64], bandwidth: float
) -> NDArray[np.float64]:
    """Régression à noyau de Nadaraya-Watson, noyau **symétrique**.

    Chaque point lissé est une moyenne pondérée de toute la série, les poids
    décroissant avec la distance temporelle. Rétrospectif par construction:
    la valeur en `t` dépend d'observations postérieures à `t`.
    """
    n = len(values)
    if n == 0 or bandwidth <= 0:
        return values.astype(float)
    radius = min(n - 1, int(np.ceil(GAUSSIAN_CUTOFF_SIGMAS * bandwidth)))
    distance: NDArray[np.float64] = np.arange(-radius, radius + 1, dtype=float)
    weights = _gaussian_weights(distance, bandwidth)
    numerator_full = np.convolve(values, weights, mode="full")
    denominator_full = np.convolve(np.ones(n, dtype=float), weights, mode="full")
    numerator = numerator_full[radius:radius + n]
    denominator = denominator_full[radius:radius + n]
    return np.asarray(numerator / denominator, dtype=float)


def causal_kernel_smooth(
    values: NDArray[np.float64], bandwidth: float
) -> NDArray[np.float64]:
    """Le même lissage, mais borné au passé.

    Seules les observations `s ≤ t` pèsent. Le résultat est un filtre
    asymétrique: il retarde les extrema, ce qui est le prix honnête d'un
    calcul qu'on pouvait réellement faire à l'instant `t`.
    """
    n = len(values)
    if n == 0 or bandwidth <= 0:
        return values.astype(float)
    max_lag = min(n - 1, int(np.ceil(GAUSSIAN_CUTOFF_SIGMAS * bandwidth)))
    lags: NDArray[np.float64] = np.arange(max_lag + 1, dtype=float)
    weights = _gaussian_weights(lags, bandwidth)
    # Convolution with weights ordered by lag implements
    # y[t] = sum_lag price[t-lag] * weight[lag].  The denominator handles the
    # shorter history available near the left boundary.
    numerator = np.convolve(values, weights, mode="full")[:n]
    denominator = np.convolve(np.ones(n, dtype=float), weights, mode="full")[:n]
    return np.asarray(numerator / denominator, dtype=float)


def bandwidth_for(n_bars: int, fraction: float) -> float:
    """La largeur de bande, en barres, proportionnelle à la fenêtre.

    Lo-Mamaysky-Wang choisissent la largeur par validation croisée puis la
    multiplient par 0,3, parce qu'une largeur optimale au sens de l'erreur de
    prédiction lisse trop pour laisser subsister des figures. Nous fixons une
    **fraction déclarée de la fenêtre**: c'est plus simple, reproductible, et
    surtout indépendant de la série — une largeur choisie par validation
    croisée sur nos propres données ferait dépendre les figures trouvées des
    données, ce qui compliquerait toute comparaison entre actifs.

    C'est une différence assumée avec le papier, documentée comme telle.
    """
    return max(1.0, n_bars * fraction)
