# Hiérarchie causale et explication dynamique de la décision

## 1. Audit de l'existant

| Brique | État trouvé | Suite donnée |
|---|---|---|
| `EventRiskGate` | Pèse importance CRITICAL, proximité (fenêtre relative à l'horizon), amplitude, incertitude de marché, dérogation « favorable dans tous les scénarios » | Conservé. **Manquait l'exposition de l'actif** : ajoutée |
| `EventRiskEngine` / `event_proximity` | Proximité horizon-relative | **Bug corrigé** : un événement du calendrier déjà publié décroissait depuis sa *détection* (souvent des semaines avant) — une décision Fed publiée il y a 4 h pesait déjà zéro |
| `MarketCausalGraph`, groupes d'indépendance | Existent, au niveau des 5 familles | Réutilisés tels quels ; la déduplication fine se fait au niveau des facteurs |
| `SignalConvergence`, `ContradictionResolver` | Existent | Inchangés |
| `MarketExpectationEngine`, `EventSurpriseEngine` | Existent, sans mapping « baisse = haussier » | Les probabilités de marché nourrissent la question « ce que le marché attend » |
| `market_radar.attention_for` | Attention absolue dans le temps (la veille = CRITICAL) | Réutilisé pour l'attention des événements |
| `event_relevance.asset_impact` | Table catégorie × actif | Réutilisée pour la pertinence par actif (événements **et** facteurs macro) |
| Facteurs normalisés (`FactorAssessment`) | Direction, impact, confiance, fraîcheur, disponibilité | Source unique des facteurs de la hiérarchie |
| `WhaleAnalyzer` | Calculé à chaque analyse, **jamais transmis à la décision** | Branché hier ; corrigé aujourd'hui (voir §6) |
| Hiérarchie par niveaux, importance effective, rôles | **Absents** | Créés dans `engines/decision_hierarchy.py` |
| Explication causale | **Absente** — la home affichait « Confirmation encore insuffisante » | Générée par le moteur à partir des facteurs classés |

## 2. Ce qui manquait réellement

1. Un niveau par information (régime, flux, fragilité, confirmation).
2. Un poids qui dépend du moment, pas de la catégorie seule.
3. Une déduplication : Fed → taux → crédit, ou ETF → spot, comptés comme plusieurs causes.
4. Des rôles : cause principale, secondaires, confirmations, contradictions, amplificateurs, conséquences, risques d'invalidation.
5. Un texte qui dit la cause, sa conséquence et ce que la décision attend.

## 3. Logique de hiérarchisation

**Niveaux** — 1 régime (taux, énergie, crédit, banques centrales, inflation, emploi, réglementation), 2 flux (ETF, spot, baleines), 3 fragilité (levier, funding, options), 4 confirmation (structure technique, volatilité).

**Importance effective**

```
structurel × proximité × amplitude × surprise × confiance × fraîcheur × pertinence actif × horizon
```

- *Structurel* : poids du niveau ; pour un événement, poids de son type × son importance. Une adjudication du Trésor vaut 0,35, un CPI 0,95, une décision Fed 1,0.
- *Proximité* : 1 pour une mesure actuelle ; pour un événement, décroissance relative à l'horizon (hors horizon = 0).
- *Surprise* : avant publication, 1 si rien n'est valorisé, moins si le marché a déjà tranché ; après publication, 0,4 si conforme, jusqu'à 1 si l'écart est net.
- *Horizon* : un **niveau** de taux est un régime lent — 0,55 sur 24 h, 1 sur 30 j. Le levier et la technique pèsent plus sur 24 h. Les événements ne sont pas pondérés ici : leur proximité le fait déjà.

**Déduplication** — chaque facteur appartient à une grappe causale. Un seul membre compte pleinement ; les autres deviennent des *conséquences* à 25 %. La cause en amont mène dès qu'elle pèse au moins la moitié du plus fort : l'ETF mène le spot, pas l'inverse. Une décision de banque centrale publiée rejoint la grappe des taux qu'elle a fait bouger. Sept adjudications du Trésor comptent comme une seule.

**Rôles** — le plus lourd est le facteur principal. Viennent ensuite : les événements à venir (risques d'invalidation), la fragilité **tendue** (amplificateurs — un levier sain reste en contexte), les facteurs opposés à la lecture dominante (contradictions), la technique alignée (confirmations), le reste (secondaires). Un seuil de 0,10 sépare les facteurs principaux du contexte.

**Lecture** — POSITIVE, NEGATIVE, MIXED, NEUTRAL, UNKNOWN ; la fragilité n'y vote pas ; un événement non publié non plus. Couverture < 40 % des lectures attendues → INSUFFICIENT_DATA.

**Ce qui ne change jamais** — l'attention n'est pas une direction. Un événement à venir a une direction UNKNOWN. Après publication, seule une direction explicitement fournie (`overall_direction`) est reprise : aucune règle « baisse de taux = haussier ». La hiérarchie **explique** la décision ; elle ne la prend pas.

## 4. Home finale

1. Actif, prix, horizons.
2. Carte verdict : ATTENDRE / ACHETER / VENDRE, puis *« Facteur principal : 💵 Taux US — taux qui pèsent »*, puis Risque · Horizon · Tendance (la tendance est la lecture de la hiérarchie : elle ne peut plus contredire le texte dessous).
3. 🔎 *Pourquoi attendre ?* — le paragraphe du moteur, 4 à 5 lignes, chacune « cause : conséquence », la dernière disant ce que la décision attend.
4. 📌 *Facteurs principaux* — 4 au plus, dans l'ordre du moteur, chacun avec un statut coloré (🔴 🟠 🟡 🟢 ⚪️). Une ligne 🐋 toujours présente. « Voir l'analyse complète ». Chaque facteur ouvre une fiche : que se passe-t-il, pourquoi c'est important, ce que le marché attend, ce qui invaliderait la lecture, source.
5. 👀 *À surveiller* — le calendrier, sans répéter un événement déjà parmi les facteurs principaux.

Retirés de la home : la liste plate de raisons, « Confirmation encore insuffisante », « Pour passer à acheter », l'indicateur baleines séparé (fondu dans les facteurs).

## 5. Exemples réels (export du 18/09/2026, 23 h 25)

### BTC

**24h** — WAIT · lecture MIXED · couverture 70%

```
Facteur principal : 🪙 Spot — Acheteurs dominants

🪙 Les acheteurs dominent au comptant, ce que confirment les entrées sur les ETF : la demande immédiate est réelle.
💵 En sens inverse, les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
⚪️ Crédit, Baleines : donnée indisponible, la lecture est moins complète.
⏳ Aucun de ces signaux n'a encore montré d'avantage mesurable sur l'historique : pas d'entrée tant qu'un avantage ne se confirme pas.

🪙 Spot             Acheteurs dominants   (poids 0.52, niveau 2)
💵 Taux US          Taux qui pèsent   (poids 0.36, niveau 1)
🐋 Baleines        Donnée indisponible
```

**7d** — WAIT · lecture MIXED · couverture 70%

```
Facteur principal : 💵 Taux US — Taux qui pèsent

💵 Les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
💸 En sens inverse, les ETF enregistrent des entrées nettes, ce que confirment les achats au comptant : la demande institutionnelle soutient le prix.
⚪️ Crédit, Baleines : donnée indisponible, la lecture est moins complète.
⏳ Aucun de ces signaux n'a encore montré d'avantage mesurable sur l'historique : pas d'entrée tant qu'un avantage ne se confirme pas.

💵 Taux US          Taux qui pèsent   (poids 0.52, niveau 1)
💸 ETF              Flux favorables   (poids 0.41, niveau 2)
🐋 Baleines        Donnée indisponible
```

**30d** — WAIT · lecture MIXED · couverture 70%

```
Facteur principal : 💵 Taux US — Taux qui pèsent

💵 Les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
💸 En sens inverse, les ETF enregistrent des entrées nettes, ce que confirment les achats au comptant : la demande institutionnelle soutient le prix.
📈 Inflation PCE dans 12 j : elle est la mesure d'inflation suivie par la Fed et peut déplacer les anticipations de taux.
⚪️ Crédit, Baleines : donnée indisponible, la lecture est moins complète.
⏳ L'entrée est différée jusqu'à la publication (Inflation PCE, dans 12 j) : l'écart avec les attentes et la réaction du marché décideront de la suite.

💵 Taux US          Taux qui pèsent   (poids 0.65, niveau 1)
💸 ETF              Flux favorables   (poids 0.36, niveau 2)
📈 Inflation PCE    Bloque l'entrée • dans 12 j   (poids 0.33, niveau 1)
🐋 Baleines        Donnée indisponible
```

### ETH

**24h** — WAIT · lecture MIXED · couverture 70%

```
Facteur principal : 🪙 Spot — Acheteurs dominants

🪙 Les acheteurs dominent au comptant, ce que confirment les entrées sur les ETF : la demande immédiate est réelle.
💵 En sens inverse, les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
⚪️ Crédit, Baleines : donnée indisponible, la lecture est moins complète.
⏳ Aucun de ces signaux n'a encore montré d'avantage mesurable sur l'historique : pas d'entrée tant qu'un avantage ne se confirme pas.

🪙 Spot             Acheteurs dominants   (poids 0.52, niveau 2)
💵 Taux US          Taux qui pèsent   (poids 0.36, niveau 1)
🐋 Baleines        Donnée indisponible
```

**7d** — WAIT · lecture MIXED · couverture 70%

```
Facteur principal : 💵 Taux US — Taux qui pèsent

💵 Les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
💸 En sens inverse, les ETF enregistrent des entrées nettes, ce que confirment les achats au comptant : la demande institutionnelle soutient le prix.
⚪️ Crédit, Baleines : donnée indisponible, la lecture est moins complète.
⏳ Aucun de ces signaux n'a encore montré d'avantage mesurable sur l'historique : pas d'entrée tant qu'un avantage ne se confirme pas.

💵 Taux US          Taux qui pèsent   (poids 0.52, niveau 1)
💸 ETF              Flux favorables   (poids 0.41, niveau 2)
🐋 Baleines        Donnée indisponible
```

**30d** — WAIT · lecture MIXED · couverture 70%

```
Facteur principal : 💵 Taux US — Taux qui pèsent

💵 Les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
💸 En sens inverse, les ETF enregistrent des entrées nettes, ce que confirment les achats au comptant : la demande institutionnelle soutient le prix.
📈 Inflation PCE dans 12 j : elle est la mesure d'inflation suivie par la Fed et peut déplacer les anticipations de taux.
⚪️ Crédit, Baleines : donnée indisponible, la lecture est moins complète.
⏳ L'entrée est différée jusqu'à la publication (Inflation PCE, dans 12 j) : l'écart avec les attentes et la réaction du marché décideront de la suite.

💵 Taux US          Taux qui pèsent   (poids 0.65, niveau 1)
💸 ETF              Flux favorables   (poids 0.36, niveau 2)
📈 Inflation PCE    Bloque l'entrée • dans 12 j   (poids 0.33, niveau 1)
🐋 Baleines        Donnée indisponible
```

### SOL

**24h** — WAIT · lecture MIXED · couverture 57%

```
Facteur principal : 🪙 Spot — Acheteurs dominants

🪙 Les acheteurs dominent au comptant : la demande immédiate est réelle.
💵 En sens inverse, les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
⚪️ Crédit, ETF, Baleines : donnée indisponible, la lecture est moins complète.
⏳ Aucun de ces signaux n'a encore montré d'avantage mesurable sur l'historique : pas d'entrée tant qu'un avantage ne se confirme pas.

🪙 Spot             Acheteurs dominants   (poids 0.36, niveau 2)
💵 Taux US          Taux qui pèsent   (poids 0.36, niveau 1)
🐋 Baleines        Donnée indisponible
```

**7d** — WAIT · lecture MIXED · couverture 57%

```
Facteur principal : 💵 Taux US — Taux qui pèsent

💵 Les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
🪙 En sens inverse, les acheteurs dominent au comptant : la demande immédiate est réelle.
⚪️ Crédit, ETF, Baleines : donnée indisponible, la lecture est moins complète.
⏳ Aucun de ces signaux n'a encore montré d'avantage mesurable sur l'historique : pas d'entrée tant qu'un avantage ne se confirme pas.

💵 Taux US          Taux qui pèsent   (poids 0.52, niveau 1)
🪙 Spot             Acheteurs dominants   (poids 0.41, niveau 2)
🐋 Baleines        Donnée indisponible
```

**30d** — WAIT · lecture MIXED · couverture 57%

```
Facteur principal : 💵 Taux US — Taux qui pèsent

💵 Les taux américains restent élevés : ils rendent les actifs risqués moins attractifs.
🪙 En sens inverse, les acheteurs dominent au comptant : la demande immédiate est réelle.
📈 Inflation PCE dans 12 j : elle est la mesure d'inflation suivie par la Fed et peut déplacer les anticipations de taux.
⚪️ Crédit, ETF, Baleines : donnée indisponible, la lecture est moins complète.
⏳ L'entrée est différée jusqu'à la publication (Inflation PCE, dans 12 j) : l'écart avec les attentes et la réaction du marché décideront de la suite.

💵 Taux US          Taux qui pèsent   (poids 0.65, niveau 1)
🪙 Spot             Acheteurs dominants   (poids 0.36, niveau 2)
📈 Inflation PCE    Bloque l'entrée • dans 12 j   (poids 0.33, niveau 1)
🐋 Baleines        Donnée indisponible
```

Ce que ces sorties montrent :

- **Les horizons ne sont plus identiques.** Sur 24 h, le spot mène ; sur 7 et 30 j, le niveau des taux.
- **La Fed, la BCE et la BoJ n'apparaissent pas**, et c'est exact : les prochaines réunions (29 octobre) sont au-delà de 30 jours.
- **Sur 30 j, le PCE dans 12 jours bloque l'entrée** — il apparaît en rouge « Bloque l'entrée », pas en jaune.
- Partout, le verdict ATTENDRE est tenu par l'absence d'avantage mesurable (`NO_MEASURABLE_EDGE`), et le texte le dit dans ces termes.

## 6. Défauts trouvés et corrigés

- **`event_proximity`** faisait décroître un événement publié depuis sa date de détection.
- **L'ETF disparaissait** derrière le spot, dans la même grappe, parce que le spot pesait légèrement plus.
- **Trois horizons identiques** : le niveau de taux avait le même poids sur 24 h que sur 30 j.
- **« Options : Pas d'excès de levier »** — libellé faux, et une fragilité absente occupait une place principale.
- **L'événement qui bloque l'entrée s'affichait en jaune** « À l'agenda ».
- **La tendance de la carte verdict contredisait le paragraphe** (« Plutôt favorable » au-dessus d'une lecture mitigée).
- **Baleines** : la confiance de l'analyseur est sur 0–100 et était passée telle quelle à un champ 0–1 ; et l'analyseur lit un dépôt net comme baissier dès −12 de score. Désormais la taille du mouvement fixe l'impact, et une direction exige que le stock détenu par les plateformes bouge dans le même sens.
- **`EventRiskGate`** : un événement critique sur un autre réseau (incident Solana) bloquait une décision Bitcoin.
- **Emojis en contour sur iPhone** : Flutter web utilise par défaut une police emoji monochrome. `useColorEmoji: true` est activé dans `app/web/flutter_bootstrap.js`.
- **Passage de 19 h sauté** : il tombait pendant une passe légère, trouvait le verrou pris et s'arrêtait sans relance avant 7 h. La passe complète attend désormais le verrou (15 min max).
- **Export effacé en cours d'écriture** : chaque export supprimait tout staging autre que le sien ; la passe légère effaçait ainsi celui d'un export concurrent. Seul un staging de plus de 2 h est supprimé.
- **Fichiers `.staging/` versionnés** par un commit intermédiaire : retirés et ignorés.

## 7. Tests

`tests/unit/test_decision_hierarchy.py` — les 12 scénarios demandés et les défauts trouvés :

| Test | Vérifie |
|---|---|
| 1 | Fed dans 8 h prioritaire sur une technique haussière (poids > 2×) |
| 2 | Fed dans 29 j n'écrase pas un flux ETF exceptionnel, sur 7 j comme sur 30 j |
| 3 | BoJ demain : CRITICAL + UNKNOWN, 🇯🇵 |
| 4 | BCE publiée : surprise nette > 1,8 × résultat conforme ; toujours sans direction inventée |
| 5 | Petit transfert de baleine hors des facteurs principaux |
| 6 | Transfert massif vers une plateforme : attention élevée, direction UNKNOWN, jamais SELL (y compris via le moteur de décision) |
| 7 | Funding extrême = amplificateur, ne fait pas voter la lecture |
| 8 | Fed dans 8 h + technique haussière : WAIT, et le texte dit « différée » et « réaction du marché » |
| 9 | Marché sain + avantage mesuré : BUY, sans phrase générique ; sans avantage, WAIT nommant sa cause |
| 10 | Fed → taux → crédit comptés une fois ; ETF → spot aussi ; 7 adjudications = 1 |
| 11 | Données opposées → MIXED |
| 12 | Données majeures absentes → couverture < 40 % → INSUFFICIENT_DATA |

S'y ajoutent l'horizon (la même Fed absente sur 24 h, principale sur 7 j), l'exposition de l'actif dans le gate, la cause en tête de grappe, le levier calme en contexte, le niveau de taux selon l'horizon, l'événement bloquant affiché comme tel, les baleines (`test_whale_indicator.py`), le staging concurrent (`test_atomic_export.py`).

Côté Flutter : l'explication affichée est celle du moteur **ligne pour ligne** ; les facteurs sont dans l'ordre du moteur ; 4 au plus ; un seul statut coloré chacun ; aucun jargon ; la fiche répond aux quatre questions ; la source n'est jamais un nom de famille ; pas de débordement à 360 px.

**Résultats** : backend 1827 passés, 15 ignorés ; Flutter 380 passés ; ruff et analyzer propres.

## 8. Preuves du branchement

`FutureEvent` + facteurs normalisés → `build_hierarchy` dans `FutureDecisionEngine.decide`, **pour chaque horizon** → champ `hierarchy` de `FutureDecision.to_dict` → endpoint `/future/{asset}` → snapshots exportés (vérifié sur les 9 fichiers) → `FutureHierarchyRead` en Dart → home. Le test « the reasoning is the engine's, line for line » échoue si l'écran écrit une seule ligne que le moteur n'a pas produite.

## 9. Données encore manquantes

- **Baleines** : aucune source configurée (Whale Alert, Glassnode et CryptoQuant exigent une clé payante). L'indicateur affiche ⚪️ « Donnée indisponible ».
- **Crédit** : `FRED_API_KEY` absente, écarts de crédit indisponibles.
- **ETF SOL** : aucune série de flux.
- **Dollar (DXY)** : non mesuré — la chaîne Fed → taux → dollar s'arrête aux taux.
- **Probabilités de marché** : présentes seulement quand un fournisseur (CME FedWatch) en publie ; sinon la fiche le dit.
- **Direction après publication** : aucune source ne fournit encore l'écart résultat/consensus signé ; un événement publié reste UNKNOWN tant qu'on ne le lui fournit pas.
