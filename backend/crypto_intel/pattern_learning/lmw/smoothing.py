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


def _gaussian_weights(distance: np.ndarray, bandwidth: float) -> np.ndarray:
    """Noyau gaussien. Le facteur constant se simplifie dans la normalisation."""
    return np.exp(-0.5 * (distance / bandwidth) ** 2)


def kernel_smooth(values: np.ndarray, bandwidth: float) -> np.ndarray:
    """Régression à noyau de Nadaraya-Watson, noyau **symétrique**.

    Chaque point lissé est une moyenne pondérée de toute la série, les poids
    décroissant avec la distance temporelle. Rétrospectif par construction:
    la valeur en `t` dépend d'observations postérieures à `t`.
    """
    n = len(values)
    if n == 0 or bandwidth <= 0:
        return values.astype(float)
    positions = np.arange(n, dtype=float)
    smoothed = np.empty(n, dtype=float)
    for i in range(n):
        weights = _gaussian_weights(positions - positions[i], bandwidth)
        total = weights.sum()
        smoothed[i] = float(values @ weights / total) if total > 0 else values[i]
    return smoothed


def causal_kernel_smooth(values: np.ndarray, bandwidth: float) -> np.ndarray:
    """Le même lissage, mais borné au passé.

    Seules les observations `s ≤ t` pèsent. Le résultat est un filtre
    asymétrique: il retarde les extrema, ce qui est le prix honnête d'un
    calcul qu'on pouvait réellement faire à l'instant `t`.
    """
    n = len(values)
    if n == 0 or bandwidth <= 0:
        return values.astype(float)
    positions = np.arange(n, dtype=float)
    smoothed = np.empty(n, dtype=float)
    for i in range(n):
        distance = positions[: i + 1] - positions[i]
        weights = _gaussian_weights(distance, bandwidth)
        total = weights.sum()
        smoothed[i] = (
            float(values[: i + 1] @ weights / total) if total > 0 else values[i]
        )
    return smoothed


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
