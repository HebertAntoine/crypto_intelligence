# Opportunité d'achat et pression du marché

Deux blocs de la page « Aujourd'hui » répondent à des questions différentes.
« Est-ce une opportunité d'achat ? » évalue la configuration. « Qui achète, qui
vend » décrit les flux. Ils sont volontairement séparés : un marché peut être
acheté par les institutions sans que la configuration d'entrée soit bonne.

## Architecture

```
sources  →  moteurs déterministes  →  facteurs structurés
         →  moteur de décision     →  explication structurée
         →  [reformulation optionnelle]  →  UI
```

La décision est calculée côté backend et transmise telle quelle. Le frontend ne
la recalcule pas : deux implémentations parallèles finiraient par diverger, et
c'est exactement ce qui s'était produit avec la fraîcheur.

`provenance.llm_used` vaut `false`. Aucun modèle de langage n'est branché
aujourd'hui, et l'emplacement prévu ne pourra que reformuler : il ne reçoit pas
« analyse BTC et décide », il reçoit la décision et ses raisons.

## Ce que le moteur ne fait pas

`BuyOpportunityDecisionEngine` ne calcule aucun indicateur. Il consomme
`EntryOpportunityEngine`, `EdgeEngine`, `UncertaintyEngine`,
`LeverageCrowdingEngine`, `MarketStructureEngine`, `MarketRegimeEngine`,
le calendrier macro et la pression du marché. Créer un second système
concurrent aurait produit deux vérités.

## La règle centrale : « pas de preuve » n'est pas « non »

`NO_MEASURABLE_EDGE` signifie qu'aucune relation n'a franchi les filtres. Cela
ne dit rien de la direction du prix.

L'écran répondait NON dès qu'aucun avantage n'était démontré, ce qui se lisait
comme une lecture baissière. Un marché fortement haussier, une entrée neutre et
aucun edge donnent maintenant **ATTENDRE**.

| EntryOpportunity | État de départ |
| --- | --- |
| VERY_FAVORABLE | VERY_FAVORABLE |
| FAVORABLE | FAVORABLE |
| NEUTRAL | WAIT |
| UNFAVORABLE / VERY_UNFAVORABLE | UNFAVORABLE |
| INSUFFICIENT_DATA | INSUFFICIENT_DATA |

## Garde-fous

Un garde-fou ne fait que descendre dans la sévérité. Aucun ne rend la lecture
plus favorable.

| Condition | Plafond |
| --- | --- |
| Aucun avantage démontré | empêche seulement VERY_FAVORABLE ; FAVORABLE reste possible |
| Événement macro critique ≤ 24 h | WAIT |
| Incertitude ≥ 60/100 | WAIT |
| Entrées critiques périmées | WAIT |
| Encombrement extrême | UNFAVORABLE |
| Entrée critique absente | INSUFFICIENT_DATA |

Le dernier n'est pas un plafond mais une suppression : sans prix ni bougies, la
question n'a pas de réponse.

## Facteurs

Chaque facteur porte `id`, `category`, `title`, `short_text`, `raw_value`,
`normalized_value`, `polarity`, `importance`, `confidence`, `evidence_level`,
`timeframe`, `source`, `as_of`, `freshness`, `available`.

Polarités : `POSITIVE`, `WAIT`, `NEGATIVE`, `NEUTRAL`, `MISSING`.

`DecisionFactorRanker` classe sur l'importance, l'ampleur normalisée, la
confiance, le niveau de preuve, la fraîcheur et la proximité d'événement. Cinq
au plus par groupe : au-delà, les raisons qui pèsent se noient dans celles qui
ne pèsent pas. Les doublons de titre sont écartés — deux moteurs signalant la
même lacune donnaient l'impression de deux problèmes.

## Données absentes

Une composante indisponible est **retirée du calcul et affichée comme absente**,
jamais comptée comme neutre : ignorer n'est pas équilibrer. La carte affiche
le nombre de composantes mesurées sur les cinq familles prévues.

Aujourd'hui : les baleines exigent un fournisseur on-chain payant qui n'est pas
configuré, et les flux spot/exchange un connecteur absent. Aucune estimation
n'est fabriquée.

## Données synthétiques

La base contient des observations enregistrées avec la source des fixtures,
ingérées quand `MOCK_MODE` était actif. Sans filtre elles se présentent comme
n'importe quelle mesure : « Liquidité stablecoin : expansion » a figuré parmi
les facteurs positifs d'une décision de production, sourcée
« MOCK FIXTURES (synthetic) ».

Toute famille dont une observation déclare une source `MOCK`, `SYNTHETIC` ou
`FIXTURE` est traitée comme absente. Un test interroge l'endpoint réel et
échoue si une telle source pèse.

## Macro

Les échéances viennent de `config/macro_calendar.yaml` : des dates publiées à
l'avance. Un événement passé est ignoré, un événement lointain n'impose rien.
Rien n'évoque la Fed si le calendrier est vide — un test le vérifie en
inspectant l'intégralité du texte produit.

## Pression du marché

Composantes : institutions (flux ETF spot, Farside), levier (funding
perpétuel), positionnement (prix × open interest), baleines.

Le curseur est la moyenne pondérée par qualité et confiance des composantes
**disponibles** uniquement. Le funding
n'est pas traduit mécaniquement en pression vendeuse : un funding négatif dit
que les shorts paient, ce qui est aussi un terrain de short squeeze. La
conséquence dépend du triplet prix / OI / funding.

## Exemples mesurés

Le résultat est recalculé depuis les observations du moment. Aucune valeur de
prix, de flux ou de funding n'est documentée en dur ici : les exemples datés
deviendraient trompeurs dès la collecte suivante.

**SOL** — pas d'ETF spot, donc la composante institutionnelle est absente par
nature et non par panne. Pas de DVOL non plus : la volatilité repose sur l'ATR
réalisé.

## Tests

`tests/unit/test_buy_opportunity.py` — 35 tests. Les scénarios de la
spécification : haussier près du bas de range → opportunité ; haut de range avec
FOMC à 8 h → attente ; cassure baissière avec encombrement extrême →
défavorable ; entrées critiques absentes → données insuffisantes. Plus :
aucun garde-fou ne remonte l'état, aucune source synthétique ne pèse, aucune
mention de la Fed sans événement, aucune direction de baleine sans fournisseur.

## Limites

- Sans backend joignable, l'app lit les instantanés analytiques embarqués. Le
  prix, lui, continue d'être alimenté directement par le WebSocket Kraken.
- Le texte de certains facteurs vient de moteurs anglophones et n'est pas
  encore traduit à la source (`structural location`, `invalidation`).
- Aucun reformulateur n'est branché ; les phrases sont assemblées depuis les
  états.
- Les baleines et les flux spot resteront absents tant qu'aucun fournisseur
  n'est configuré. C'est une limite de données, pas de code.
