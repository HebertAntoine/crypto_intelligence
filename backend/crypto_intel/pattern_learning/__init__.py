"""Ce qui vient de l'extérieur, et sous quelles conditions.

Ce paquet ne détecte rien et ne décide rien. Il tient deux registres:

* **l'ontologie** — un nom canonique par figure, et les correspondances depuis
  les vocabulaires étrangers. Sans elle, comparer nos détections à celles d'un
  autre moteur reviendrait à comparer des chaînes de caractères;
* **les sources** — d'où vient chaque jeu de données ou moteur, sous quelle
  licence, et ce qu'on a le droit d'en faire.

Rien n'entre dans l'entraînement ou dans la production sans provenance établie.
Un dépôt public n'est pas un dépôt libre.
"""

from .ontology import (
    METHOD_FAMILIES,
    STRUCTURAL_PATTERNS,
    MethodFamily,
    StructuralPatternName,
    canonical,
    is_candlestick_name,
)
from .sources import SOURCES, DatasetSource, LicenceStatus, SourceKind

__all__ = [
    "METHOD_FAMILIES",
    "SOURCES",
    "STRUCTURAL_PATTERNS",
    "DatasetSource",
    "LicenceStatus",
    "MethodFamily",
    "SourceKind",
    "StructuralPatternName",
    "canonical",
    "is_candlestick_name",
]
