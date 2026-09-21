# Refonte de la lisibilité et de l'interprétation

La couche d'interprétation a été refaite, pas le moteur. Les moteurs (familles, verrous de décision, niveaux, événements) sont inchangés, à deux bugs de sens près (§6). Ce qui change, c'est ce que l'utilisateur voit, dans quel ordre, et avec quels mots.

```
moteurs (scores, verrous, niveaux, événements)
      ↓
engines/interpretation.py   ← nouvelle couche, déterministe, sans LLM
      ↓
UI (Home, pages famille, « Pourquoi le marché bouge »)
```

## 1. Audit de l'existant

| Élément | Où | Constat | Décision |
|---|---|---|---|
| Résumé de décision | `engines/decision_presentation.summarize` | phrase, tendance, entrée, risque, 3 raisons, familles | conservé ; `reading` ajouté à côté |
| Conditions du moteur | `HorizonDecision.to_buy / to_worsen` | réelles mais jargonnantes (« EMA20 », « taux réel ») | traduites (`plain()`), jamais inventées |
| Niveaux | extra technique `support / resistance (+ explication)` | venus du moteur de structure | seuls chiffres de niveau affichés |
| Événements | `EventCandidate` | sans date exploitable | champ `at` ajouté → « demain 20:00 » |
| Verrou bloquant | `gates` (UNCERTAINTY / NO_MEASURABLE_EDGE…) | souvent la vraie raison d'attendre, peu visible | expliqué en clair et affiché dans « ce qu'on attend » |
| Historique de décision | `history/decisions.py` | état « opportunité » seulement | verdict par horizon enregistré (`future`), `decision_streak` |
| Familles affichées | 5 (Technique, Dérivés, Flux spot, Macro, Cycle) | on-chain déjà masqué sur la Home | **aucune famille ajoutée** |
| « Pourquoi le marché bouge » | `engines/market_explanation.py` | titres « BTC — catalyseur propre », « Participation — … » | titres traduits ; macro et dérivés par la même couche |

**Déplacé dans les détails** (toujours accessible sous « Détails ») : centiles bruts, funding 8 h, prime des futures, rang historique de l'open interest, pente de courbe, taux effectifs.

## 2. La lecture (`summary.reading`)

| Champ | Contenu | Règle |
|---|---|---|
| `verdict` | ACHETER / ATTENDRE / VENDRE | lu dans le moteur, jamais modifié |
| `headline` | ce que fait le marché, puis ce qui retient la décision | construite à partir de la carte de prudence dominante |
| `waiting_for` | 1 à 3 conditions concrètes | **jamais vide quand le verdict est ATTENDRE** |
| `why` | 3 cartes au plus : ce qui se passe → ce que ça signifie → à surveiller | pour ATTENDRE, les freins passent avant les soutiens |
| `change_mind` | 🟢 pour devenir plus positif / 🔴 pour devenir plus prudent (2 au plus chacun) | niveaux réels et conditions du moteur uniquement |
| `invalidation` | « Cette lecture ne serait plus valable si… » | seulement si un support ou une résistance réel existe |
| `contradictions` | « Les signaux restent partagés », avec les points positifs et les points de prudence | jamais moyennées en silence |
| `families` | 3 cartes traduites au plus par famille | importance dynamique : Important maintenant, À surveiller, Secondaire |
| `data` / `market` | fiabilité des données ≠ clarté du marché | deux lectures séparées, jamais un score unique |
| `decision_history` | « Attendre depuis 2 jours », avec l'évolution | à partir des lectures enregistrées ; « depuis au moins » quand l'historique est plus court |

## 3. Garde-fous « ne rien inventer »

- Un chiffre n'apparaît que s'il vient d'un moteur : niveau de structure, date du calendrier, centile de l'historique, flux ETF daté.
- Sans niveau fiable, la carte l'indique : « Pas de niveau fiable — aucun niveau n'est inventé ».
- Une résistance doit être au-dessus du **prix actuel** et un support en dessous. Le prix du plus court horizon est transmis aux autres : à 30 jours, la dernière clôture journalière ne fait plus apparaître un niveau déjà franchi.
- Aucune probabilité n'est produite, et un test le vérifie.
- Fed et publications macro :
  - l'attente du marché s'affiche si elle existe, sinon « indisponible » ;
  - la lecture précise que c'est l'écart avec les attentes qui compte, pas le sens de la décision ;
  - l'événement est suivi de « la réaction du marché ». Un événement passé n'est pas une confirmation.
- Une donnée ancienne est signalée (ex. « ETF : séance du 18 sept., donnée ancienne »).
- Les noms suivent l'actif : Bitcoin, Ether, Solana.

## 4. Écran

**Home**, dans l'ordre de lecture :
1. verdict, avec la phrase traduite ;
2. 👀 Ce qu'on attend ;
3. 🔎 Pourquoi attendre ?, contradictions comprises ;
4. 🔀 Ce qui changerait la lecture, avec l'invalidation ;
5. Données 🟢 / Marché 🟠, horizon, heure de mise à jour et historique de la décision ;
6. « Pourquoi le marché bouge » ;
7. les familles, avec leur constat traduit ;
8. le calendrier.

**Pages famille** : « 🎯 L'essentiel » (3 cartes au plus), puis « Détails » avec les données complètes.

Composants dans `app/lib/widgets/reading_widgets.dart` ; modèles dans `app/lib/api/reading_models.dart`.

## 5. Critères d'acceptation

| Critère | État |
|---|---|
| Les 5 familles retravaillées (cartes traduites) | ✅ |
| Aucune famille ajoutée | ✅ |
| Métriques techniques inutiles déplacées dans les détails | ✅ |
| Termes techniques traduits (funding, open interest, RSI, moyenne mobile, taux réels, stablecoins…) | ✅ |
| ATTENDRE dit toujours ce qui est attendu | ✅ (testé) |
| Événements macro datés quand l'heure existe | ✅ (heure de Paris) |
| Niveaux affichés venant réellement des moteurs | ✅ (testé, y compris le côté du prix) |
| Données périmées identifiables | ✅ |
| Qualité des données distincte de la certitude du marché | ✅ |
| Contradictions conservées | ✅ |
| Aucun chiffre ni aucune probabilité inventés | ✅ (testé) |
| 2 à 4 facteurs principaux | ✅ (3 au plus) |
| « Pourquoi cela compte ? » et « Que surveiller ? » sur chaque carte | ✅ |
| « Ce qui changerait la lecture » quand des conditions fiables existent | ✅ |
| Horizons 24 h / 7 j / 30 j non mélangés | ✅ (« Lecture à 7 jours ») |
| Interface principale légère, détails dans les sous-pages | ✅ |

## 6. Bugs corrigés au passage

- **Nasdaq inversé.** Dans la liste des mouvements macro notables, les textes « forte hausse » et « forte baisse » étaient intervertis. Une hausse de +2,8 % s'affichait « Nasdaq en forte baisse → aversion au risque ».
- **Stablecoins.** La condition de retournement était fixe (« un recul durable »). Quand l'offre recule déjà, la condition pour acheter devenait l'inverse de ce qu'il faut. Elle dépend maintenant du sens actuel.
- **Événements passés.** La synthèse listait comme « à venir » des événements déjà passés. L'export statique refusait donc toute publication depuis 15:30, y compris les rafraîchissements automatiques. Ils sont maintenant filtrés.

## 7. Reste à faire

- La page Cycle a sa propre mise en page : sa carte traduite est utilisée sur la Home, mais pas encore en tête de la page Cycle.
- Scénarios haussier / neutre / baissier : le moteur fournit des scénarios. Leur traduction en trois lignes conditionnelles, sans probabilité, est une prochaine étape.
- Alertes « la condition qui bloquait vient d'être levée » : l'historique enregistré le permet désormais ; le déclencheur reste à brancher.
- Les dossiers SEC cités comme « actualité propre » (ex. « 424B3 ») restent techniques.
