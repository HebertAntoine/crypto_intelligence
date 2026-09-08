# Page « Aujourd'hui » v2 — le cockpit

La page ne devait pas être reconstruite, et ne l'a pas été. Le design, la carte
BTC/ETH/SOL, le prix live, la séparation prix live / heure d'analyse, le moteur
de décision, « voir pourquoi », « qui achète qui vend », la provenance et les
règles anti-mock sont ceux d'avant. Ce qui a changé est ce que la page répond
et dans quel ordre.

Objectif : répondre en moins de dix secondes à huit questions. Où va le marché,
où est le prix, est-ce intéressant maintenant, pourquoi, qu'est-ce qui ferait
changer la décision, qu'est-ce qui arrive, sur quelles données cela repose, et
qu'est-ce qui est réellement démontré.

## 1. Audit avant modification

| Élément affiché | Moteur | Rôle réel dans la décision |
| --- | --- | --- |
| Prix | `market_price_snapshot`, puis Kraken WebSocket dans l'app | aucun : contexte |
| Ligne « analyse calculée à » | `analysis` de `/today` | cadre la fraîcheur |
| Ligne « RÉGIME » | `reconstruct_regime` sur bougies 1J | direction |
| Panneau opportunité | `BuyOpportunityDecisionEngine` | la décision |
| Qui achète, qui vend | `assess_pressure` | contexte, jamais un signal |
| Familles | `core/usability` | ce que la page a le droit d'affirmer |

Constat : le régime, l'incertitude et la décision étaient là ; la **localisation
structurelle** ne l'était pas, alors que `StructuralLocationEngine` la calculait
déjà et que c'est elle qui sépare BTC de ETH aujourd'hui. Les catalyseurs
étaient chargés (`upcoming_macro`) mais non affichés. La couverture des données
n'existait pas.

REUSE > EXTEND > REPLACE : aucun moteur concurrent n'a été créé. Les seuls
nouveaux modules sont un instantané qui rassemble les moteurs existants
(`analysis_context`), une projection de présentation (`today_view`) et un
enregistreur d'historique de verdict (`history/decisions`).

## 2. Composants réutilisés

`StructuralLocationEngine`, `RangeIntelligenceEngine`, `MarketStructureEngine`,
`TechnicalAnalysisEngine` (niveaux par clustering de swings), `MacroAnalyzer`,
`VolatilityRegimeEngine`, `ImpliedVolatilityEngine`, `LeverageCrowdingEngine`,
`EdgeEngine`, `UncertaintyEngine`, `EntryTimingEngine`,
`EntryOpportunityEngine`, `assess_pressure`, `BuyOpportunityDecisionEngine`,
`core/usability`.

## 3. Direction / Timing / Edge

Trois lectures indépendantes, sur une ligne, jamais fusionnées en un score.

```
DIRECTION            TIMING        AVANTAGE
FORTEMENT HAUSSIÈRE  ATTENDRE      AUCUN AVANTAGE DÉMONTRÉ
```

C'est la combinaison la plus fréquente de ce système et elle est parfaitement
cohérente. Le bloc porte la phrase qui le dit, et un test tient la propriété.

Une distinction a été ajoutée : « aucune relation testée » (`INSUFFICIENT_DATA`
avec zéro étude) n'est pas « aucun avantage démontré » (des relations testées,
aucune survivante). Les confondre laisserait un actif jamais étudié emprunter
la crédibilité d'un résultat négatif abouti.

## 4. Position structurelle

`StructuralPositionBar` place le prix entre le bas et le haut du range 4H, avec
le milieu en repère et le pourcentage écrit.

**La barre n'existe que si le range existe.** Quand la structure n'est pas un
range, le bloc nomme la structure trouvée. Fabriquer des bornes pour remplir la
barre donnerait une fausse précision, alors qu'une structure sans range est une
information exacte qu'il suffit d'énoncer.

Un prix sorti du range est borné pour le dessin seulement : la lecture brute
reste lisible, parce qu'un prix au-dessus du range n'est pas « à 100 % ».

## 5. Support et résistance

Le support le plus proche en dessous et la résistance la plus proche au-dessus,
avec leur distance en pourcentage, issus du clustering de swings 4H. Rien n'est
placé à la main ; quand le clustering ne retient aucun niveau, le bloc disparaît
au lieu d'afficher un zéro. Les distances sont mesurées contre le prix live
quand il est connu, contre le prix d'analyse sinon.

## 6. Contexte immédiat

Quatre lectures au plus : position, volatilité, encombrement, prochaine
échéance. Au-delà ce n'est plus un contexte, c'est un tableau de bord.

## 7-9. Catalyseurs

Trois échéances au plus, triées par importance publiée puis par proximité, sur
sept jours avec priorité 24-72 h. Chaque entrée porte son type, son importance,
sa date programmée, les actifs concernés et sa source
(`config/macro_calendar.yaml`).

Ce n'est pas un flux d'actualité : seules des échéances programmées et sourcées
y entrent. Un événement majeur à moins de 24 h ajoute un bandeau ; la décision
reste au `BuyOpportunityDecisionEngine`, qui applique déjà son garde-fou. Rien
n'est décidé dans Flutter.

## 10-12. Ce qui ferait changer la décision

Deux facteurs favorables, deux défavorables, et une troisième catégorie
distincte pour les changements de structure.

La troisième existe parce qu'un changement de structure n'a pas de signe. Une
cassure du haut de range invalide le range sans dégrader le marché ; la ranger
parmi les dégradations faisait lire une cassure haussière comme une mauvaise
nouvelle. C'est le défaut corrigé plus tôt, et un test l'empêche de revenir.

Les phrases sont formulées comme des conditions — « le timing deviendrait plus
favorable avec… », « la lecture serait dégradée par… » — jamais comme des
prévisions.

## 13-17. Couverture des données

Distincte de l'incertitude, et affichée comme telle. Quatre classes
(`EXPECTED_AND_AVAILABLE`, `EXPECTED_BUT_MISSING`, `NOT_APPLICABLE`,
`UNAVAILABLE_BY_DESIGN`), les deux dernières hors du dénominateur, et un
comptage séparé de disponible / récent / périmé / manquant : une donnée peut
être présente et trop ancienne pour décrire le présent.

Par actif : SOL n'est pénalisé ni pour le DVOL, que Deribit ne publie pas pour
lui, ni pour un ETF spot qui n'existe pas.

## 18-19. Âge de l'analyse et dérive du prix

Deux couches, deux horodatages, un écart explicite. Le seuil (1,5 %) vient du
backend et la sévérité est graduée : `NONE`, `NOTABLE`, `SEVERE`. Une dérive
faible n'est pas signalée ; au-delà du seuil, la page dit que l'analyse est à
actualiser.

## 20-22. Unités de temps et contradictions

1S / 1J / 4H / 1H, chaque ligne avec sa flèche **et** son mot — la couleur et la
flèche seules ne sont lisibles ni par tout le monde ni par un lecteur d'écran.

L'alignement est descriptif : `ALIGNÉ`, `PARTIELLEMENT ALIGNÉ`, `DIVERGENT`, et
jamais transformé en avantage. Toutes les unités en range est un alignement, pas
un alignement partiel.

Une contradiction importante — régime haussier contre structure hebdomadaire
baissière, ou sources de pression opposées — affiche « LECTURE MIXTE » et
s'explique au clic.

## 23. Volatilité

Réalisée et implicite restent séparées : l'une décrit ce qui s'est produit,
l'autre ce que les options font payer. Elles ne sont jamais additionnées, et
l'implicite dit pourquoi elle est absente quand elle l'est.

## 24-25. Avantage

Conservé, mais réduit visuellement. Le détail (n brut, n effectif, MDE,
rendement médian, taux de réussite) va dans la feuille, pas sur la carte.
L'absence d'avantage démontré ne dit pas que le prix va baisser, et le bloc le
dit.

## 26-28. Pression, ETF, positionnement

Sur la carte : l'état, le score, et « 3/5 familles disponibles ». Au clic : la
décomposition complète, chaque famille avec son score normalisé, son poids, son
apport reproductible au total, sa source, son horodatage, et pour une source
absente la raison de son absence — jamais un zéro.

ETF, funding, open interest et encombrement s'affichent en mots ; les valeurs
brutes restent dans Preuves.

## 29-30. Décision et phrase

Les six états validés, sans synonyme. La phrase est assemblée
déterministiquement à partir du régime, de la position structurelle et du
garde-fou qui a réellement plafonné l'état. Aucun modèle ne l'écrit, et elle ne
peut dire que ce que l'instantané contient.

## 31-34. Hiérarchie et compacité

Ordre : actif et prix, heure d'analyse et dérive, direction/timing/avantage,
décision, position structurelle et niveaux, pression. Puis, dépliable :
contexte immédiat, catalyseurs, conditions de changement, unités de temps,
couverture, dernier changement.

Une carte développée à la fois. Trois actifs entièrement déroulés donnaient une
page de plusieurs écrans où la comparaison BTC/ETH/SOL — la raison d'être de
cette liste — devenait impossible.

## 37-38. Dernier changement de lecture

Lu uniquement dans des instantanés enregistrés au moment où ils étaient
courants (`history/decisions.py`, travail planifié `decision_track` toutes les
trente minutes). Rien n'est reconstruit après coup : rejouer un moteur sur les
bougies d'aujourd'hui répond à ce que nous dirions maintenant, pas à ce que nous
avons dit alors. Sans historique suffisant, le bloc n'apparaît pas.

## 40-42. Source de vérité et performance

Tout vient d'un même `AnalysisContextSnapshot` et partage son `analysis_id`.
Flutter présente, le backend calcule ; un test interdit tout seuil de décision
numérique dans la vue.

`/today` reste un seul appel. L'instantané est calculé une fois par changement
d'entrée et servi depuis un cache : 3,3 s à froid, 18 ms ensuite. Le prix garde
son canal rapide.

## Tests

Côté backend, `test_today_page.py` (47) et `test_analysis_identity.py` (34)
couvrent les cas demandés au §43 et les non-régressions du §44. Côté client,
`app/test/today_page_test.dart` rend réellement chaque bloc.

## Ce que je n'ai pas validé

Je ne peux pas voir l'application tourner et je ne prétends pas l'avoir validée
visuellement. La revue faite est statique et par widget ; le rendu sur téléphone
reste à vérifier.

## Limites

- L'historique des verdicts est vide tant que le travail planifié n'a pas
  tourné ; « dernier changement » restera absent d'ici là.
- `EdgeEngine` ne trouve aucune étude rattachée à cette base : la page affiche
  « aucune relation testée », ce qui est exact mais signale que la sortie de
  recherche n'y est pas reliée.
- Les alertes (§39) ne sont pas câblées ; l'`AlertEngine` existant devra être
  réutilisé plutôt que doublé.
- Le backend n'est toujours pas déployé.
