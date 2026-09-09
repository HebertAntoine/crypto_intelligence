"""D'où vient chaque source, et ce qu'on a le droit d'en faire.

Le registre est **vérifié**, pas déclaratif: chaque licence ci-dessous a été
lue sur la source officielle — fichier `LICENSE` via l'API GitHub, champ
`licenseName` via l'API Kaggle, carte de modèle via l'API Hugging Face — et
non recopiée depuis une description.

La règle par défaut est le refus. Un dépôt public sans licence n'accorde aucun
droit d'usage: le droit d'auteur s'applique en l'absence de mention, pas
l'inverse. `BLOCKED_PENDING_LICENSE` est donc l'état initial, et il faut une
vérification pour en sortir.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .ontology import MethodFamily


class SourceKind(StrEnum):
    IMAGE_DATASET = "IMAGE_DATASET"
    OHLC_DATASET = "OHLC_DATASET"
    RULE_ENGINE = "RULE_ENGINE"
    PRETRAINED_MODEL = "PRETRAINED_MODEL"
    ACADEMIC_REFERENCE = "ACADEMIC_REFERENCE"


class LicenceStatus(StrEnum):
    """Ce qu'on a le droit de faire, et rien de plus."""

    TRAIN_ALLOWED = "TRAIN_ALLOWED"
    VALIDATION_ALLOWED = "VALIDATION_ALLOWED"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    BLOCKED_PENDING_LICENSE = "BLOCKED_PENDING_LICENSE"


@dataclass(slots=True, frozen=True)
class DatasetSource:
    """Une source, avec sa provenance établie."""

    id: str
    name: str
    kind: SourceKind
    source_url: str
    #: Le point exact vérifié — commit, version de jeu, date de modèle.
    version: str
    #: Licence lue sur la source, pas déduite.
    licence: str
    licence_verified: bool
    licence_evidence: str
    status: LicenceStatus
    #: Comment le moteur trouve ses figures. `None` pour un jeu de données.
    method_family: MethodFamily | None = None
    pattern_classes: tuple[str, ...] = ()
    sample_count: int | None = None
    raw_data_available: bool = False
    geometry_available: bool = False
    #: Ce qui empêche de s'en servir, ou ce à quoi il faut faire attention.
    caveats: tuple[str, ...] = ()
    notes: str = ""

    @property
    def usable(self) -> bool:
        return self.status is not LicenceStatus.BLOCKED_PENDING_LICENSE

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "kind": self.kind.value,
            "source_url": self.source_url, "version": self.version,
            "licence": self.licence,
            "licence_verified": self.licence_verified,
            "licence_evidence": self.licence_evidence,
            "status": self.status.value,
            "method_family": self.method_family.value if self.method_family else None,
            "pattern_classes": list(self.pattern_classes),
            "sample_count": self.sample_count,
            "raw_data_available": self.raw_data_available,
            "geometry_available": self.geometry_available,
            "caveats": list(self.caveats),
            "notes": self.notes,
        }


SOURCES: dict[str, DatasetSource] = {}


def _register(source: DatasetSource) -> None:
    SOURCES[source.id] = source


_register(DatasetSource(
    id="tysoncung_crypto_chart_patterns",
    name="crypto-chart-patterns (Tyson Cung)",
    kind=SourceKind.RULE_ENGINE,
    source_url="https://github.com/tysoncung/crypto-chart-patterns",
    version="commit 1601b0c8, 2026-05-05",
    licence="MIT",
    licence_verified=True,
    licence_evidence=(
        "fichier LICENSE lu via l'API GitHub: « MIT License / Copyright (c) "
        "2024 Tyson Cung »"
    ),
    status=LicenceStatus.TRAIN_ALLOWED,
    method_family=MethodFamily.SMOOTHED_EXTREMA,
    pattern_classes=(
        "HEAD_SHOULDERS", "INVERSE_HEAD_SHOULDERS", "DOUBLE_TOP",
        "DOUBLE_BOTTOM", "ASCENDING_TRIANGLE", "DESCENDING_TRIANGLE",
        "SYMMETRICAL_TRIANGLE", "RISING_WEDGE", "FALLING_WEDGE",
        "BULL_FLAG", "BEAR_FLAG", "ASCENDING_CHANNEL", "DESCENDING_CHANNEL",
        "HORIZONTAL_CHANNEL", "CUP_HANDLE",
    ),
    raw_data_available=True,
    geometry_available=True,
    caveats=(
        "argrelextrema d'ordre 1 sur une moyenne mobile traînante de 3 barres: "
        "un extremum n'est connu qu'une fois la barre suivante imprimée, donc "
        "1 barre de look-ahead. Acceptable pour comparer des FORMES, jamais "
        "pour produire une observation datée.",
        "extrema calculés sur les CLÔTURES; nos pivots utilisent hauts et bas. "
        "Les pivots ne coïncideront pas exactement, et la comparaison doit "
        "tolérer cet écart plutôt que le compter comme un désaccord.",
        "famille SMOOTHED_EXTREMA, voisine de notre CAUSAL_PIVOTS: un accord "
        "est une confirmation FAIBLE, les erreurs seront corrélées.",
    ),
    notes=(
        "Seule source à la fois licenciée, en Python, et travaillant sur "
        "Binance aux mêmes unités que nous. Description GitHub trompeuse "
        "(« deep learning »): requirements.txt ne contient que pandas, numpy, "
        "scipy, matplotlib."
    ),
))

_register(DatasetSource(
    id="kaggle_human_labeled_ohlcv",
    name="Human Labeled OHLCV Stock Market Data",
    kind=SourceKind.OHLC_DATASET,
    source_url=(
        "https://www.kaggle.com/datasets/barathanaslan/"
        "human-labeled-synthetic-stock-market-data"
    ),
    version="version 3, mise à jour 2025-03-26",
    licence="CC BY 4.0",
    licence_verified=True,
    licence_evidence=(
        "API Kaggle, champ licenseName: « Attribution 4.0 International "
        "(CC BY 4.0) »"
    ),
    status=LicenceStatus.VALIDATION_ALLOWED,
    pattern_classes=("HORIZONTAL_LEVEL", "RAY_LINE"),
    raw_data_available=True,
    geometry_available=True,
    caveats=(
        "séries SYNTHÉTIQUES — le sous-titre officiel dit « synthetically "
        "generated » et l'un des tags est `synthetic`. Ne peut pas mesurer une "
        "performance sur BTC.",
        "annote des lignes et des rayons, pas des figures chartistes: utile "
        "pour supports, résistances et trendlines, pas pour un double sommet.",
    ),
    sample_count=1219,
    notes="9,5 Mo au total. 343 téléchargements, 4 votes.",
))

_register(DatasetSource(
    id="michaelsboost_candleedge",
    name="CandleEdge",
    kind=SourceKind.RULE_ENGINE,
    source_url="https://github.com/michaelsboost/CandleEdge",
    version="commit 75761e26, 2026-05-25",
    licence="MIT",
    licence_verified=True,
    licence_evidence=(
        "fichier LICENSE lu via l'API GitHub: « The MIT License (MIT) / "
        "Copyright (c) 2026 Michael Schwartz »"
    ),
    status=LicenceStatus.REFERENCE_ONLY,
    method_family=MethodFamily.CANDLE_RULES,
    caveats=(
        "application NAVIGATEUR (langage HTML/JS). L'intégrer à un pipeline "
        "Python demanderait de réécrire ses règles — auquel cas ce n'est plus "
        "un moteur indépendant, c'est notre code inspiré du sien.",
        "sa fonction principale — la suite historique d'une figure — recouvre "
        "ce que nous avons déjà construit en PHASE C et 37B.",
    ),
    notes="Créé et poussé le même jour. 4 étoiles.",
))

_register(DatasetSource(
    id="przemyslawbak_ohlc_candlestick_patterns",
    name="OHLC_Candlestick_Patterns",
    kind=SourceKind.RULE_ENGINE,
    source_url="https://github.com/przemyslawbak/OHLC_Candlestick_Patterns",
    version="commit 1c24789c, 2026-07-20",
    licence="MIT",
    licence_verified=True,
    licence_evidence=(
        "fichier LICENSE lu via l'API GitHub: « MIT License / Copyright (c) "
        "2026 bakunet »"
    ),
    status=LicenceStatus.REFERENCE_ONLY,
    method_family=MethodFamily.CANDLE_RULES,
    caveats=(
        "écrit en C#: aucune exécution directe depuis notre pipeline.",
        "couvre la famille CANDLESTICK_PATTERN, pas les structures. Il n'a "
        "rien à comparer avec ce que produit notre moteur structurel.",
    ),
    notes="37 figures haussières, 37 baissières, plus 9+9+2 formations OHLC.",
))

_register(DatasetSource(
    id="zeta_zetra_chart_patterns",
    name="zeta-zetra/chart_patterns",
    kind=SourceKind.RULE_ENGINE,
    source_url="https://github.com/zeta-zetra/chart_patterns",
    version="commit 44f8baa3, 2024-07-08",
    licence="AUCUNE",
    licence_verified=True,
    licence_evidence="API GitHub: champ `license` = null. Aucun fichier LICENSE.",
    status=LicenceStatus.BLOCKED_PENDING_LICENSE,
    method_family=MethodFamily.CAUSAL_PIVOTS,
    pattern_classes=(
        "DOUBLE_TOP", "DOUBLE_BOTTOM", "BULL_FLAG", "BEAR_FLAG",
        "HEAD_SHOULDERS", "INVERSE_HEAD_SHOULDERS", "SYMMETRICAL_TRIANGLE",
        "BULL_PENNANT", "BEAR_PENNANT",
    ),
    caveats=(
        "sans licence explicite, le droit d'auteur s'applique: aucun droit "
        "d'usage, de copie ni de modification n'est accordé. Un dépôt public "
        "n'est pas un dépôt libre.",
        "même famille de méthode que la nôtre: même si la licence arrivait, "
        "son accord resterait une confirmation faible.",
    ),
    notes=(
        "La perte la plus regrettable: Python, 121 étoiles, et exactement nos "
        "familles. Une issue demandant l'ajout d'une licence débloquerait la "
        "meilleure source du lot."
    ),
))

_register(DatasetSource(
    id="foduu_yolov8_stockmarket",
    name="FODUU stockmarket-pattern-detection-yolov8",
    kind=SourceKind.PRETRAINED_MODEL,
    source_url=(
        "https://huggingface.co/foduucom/stockmarket-pattern-detection-yolov8"
    ),
    version="dernière modification 2025-04-02",
    licence="non déclarée, et AGPL-3.0 héritée d'Ultralytics",
    licence_verified=True,
    licence_evidence=(
        "API Hugging Face: aucun champ `license` dans la carte du modèle. "
        "Ultralytics déclare que l'AGPL-3.0 couvre les modèles produits par "
        "son code d'entraînement."
    ),
    status=LicenceStatus.BLOCKED_PENDING_LICENSE,
    method_family=MethodFamily.VISION_MODEL,
    pattern_classes=(
        "INVERSE_HEAD_SHOULDERS", "HEAD_SHOULDERS", "DOUBLE_TOP",
        "DOUBLE_BOTTOM", "SYMMETRICAL_TRIANGLE", "StockLine",
    ),
    sample_count=9800,
    caveats=(
        "contamination AGPL-3.0: s'en servir imposerait de publier le code "
        "source complet de l'œuvre dérivée — donc ce projet entier.",
        "le point dépasse cette source: entraîner NOTRE modèle visuel avec "
        "Ultralytics le rendrait AGPL aussi. torchvision (BSD) ou timm "
        "(Apache-2.0) évitent le problème.",
        "6 classes seulement, dont `StockLine` qui n'est pas une figure. "
        "mAP@0,5 = 0,614.",
    ),
    notes="429 likes, 27 545 téléchargements par mois.",
))

_register(DatasetSource(
    id="roboflow_chart_patterns",
    name="Roboflow — jeux de figures chartistes",
    kind=SourceKind.IMAGE_DATASET,
    source_url="https://universe.roboflow.com/",
    version="NON VÉRIFIÉE",
    licence="NON VÉRIFIÉE",
    licence_verified=False,
    licence_evidence=(
        "universe.roboflow.com répond HTTP 403 à toute requête automatisée; "
        "api.roboflow.com répond HTTP 401. La voie légitime est l'API avec une "
        "clé de compte, qui n'a pas été créée."
    ),
    status=LicenceStatus.BLOCKED_PENDING_LICENSE,
    caveats=(
        "aucun contournement n'a été tenté, conformément à la consigne.",
        "plusieurs jeux homonymes existent, de tailles très différentes "
        "(43, 1 455 images observés): se tromper de jeu serait facile, et les "
        "chiffres annoncés (3 498 / 9 900 images) restent invérifiés.",
    ),
))

_register(DatasetSource(
    id="stock_pattern_analysis",
    name="Stock-Pattern-Analysis",
    kind=SourceKind.OHLC_DATASET,
    source_url="inconnu",
    version="NON IDENTIFIÉE",
    licence="INCONNUE",
    licence_verified=False,
    licence_evidence=(
        "recherche GitHub sur plusieurs formulations: quatre dépôts homonymes "
        "trouvés, tous à 0 étoile et sans licence, aucun ne correspondant à la "
        "description (OHLC 5 minutes avec vérité terrain sur 4 figures)."
    ),
    status=LicenceStatus.BLOCKED_PENDING_LICENSE,
    caveats=("source non identifiée: il faut son URL exacte.",),
))

_register(DatasetSource(
    id="lo_mamaysky_wang_2000",
    name="Lo, Mamaysky & Wang (2000) — Foundations of Technical Analysis",
    kind=SourceKind.ACADEMIC_REFERENCE,
    source_url="https://www.nber.org/papers/w7613",
    version="Journal of Finance 55(4), 1705-1765",
    licence="article; version de travail NBER w7613 en accès libre",
    licence_verified=True,
    licence_evidence="référence bibliographique vérifiée (NBER, Wiley, IDEAS)",
    status=LicenceStatus.REFERENCE_ONLY,
    method_family=MethodFamily.KERNEL_SMOOTHING,
    caveats=("méthodologie à réimplémenter; aucun code à copier.",),
    notes=(
        "Régression à noyau non paramétrique, puis extraction d'extrema, puis "
        "appariement. Famille de méthode DIFFÉRENTE de la nôtre — c'est ce qui "
        "en ferait une baseline réellement informative."
    ),
))
