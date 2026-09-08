"""Contrôles indépendants de ce que les détecteurs produisent.

Ce paquet ne détecte rien. Il vérifie. La séparation est le point: un
détecteur qui se valide lui-même ne prouve rien, puisqu'il réutiliserait le
raisonnement qui a produit l'erreur.

Les niveaux sont distincts et ne se mélangent jamais:

  1. VALIDITÉ GÉOMÉTRIQUE   la figure dessinée est-elle cohérente avec les
                            bougies ? (`internal_geometry`)
  2. VALIDITÉ STRUCTURELLE  la figure a-t-elle un sens dans son contexte ?
  3. COMPARAISON EXTERNE    d'autres moteurs voient-ils la même chose ?
  4. VALIDATION HISTORIQUE  precision/recall sur un jeu annoté
  5. AVANTAGE STATISTIQUE   la forme précède-t-elle quelque chose ?

Une réponse au niveau 1 ne dit rien des niveaux suivants.
"""

from .internal_geometry import (
    GeometryValidation,
    validate_geometry,
)

__all__ = ["GeometryValidation", "validate_geometry"]
