# Home : synthèse décisionnelle

La Home raconte la situation, puis laisse approfondir. Aucun moteur n'a été reconstruit : cette refonte agrège, hiérarchise, interprète et présente ce qui existait déjà.

**Règle qui prime sur toutes les autres : une information a une seule place.** La Home montrait la même donnée jusqu'à trois fois — le flux ETF apparaissait dans le résumé, dans « Pourquoi ? », puis dans « Pourquoi le marché monte ? ». Ce qui a été retiré de la page n'a pas été retiré de l'application : c'est déplacé derrière un clic.

## 1. Audit de l'existant, réutilisé tel quel

| Besoin de la mission | Déjà présent | Réutilisé pour |
|---|---|---|
| Décision et verrous | `decision_gates` (gates, `to_buy`, `to_worsen`) | verdict, ce qu'on attend, ce qui changerait la décision |
| Niveaux, structure, RSI | famille technique (moteur de structure) | première phrase du résumé, freins, niveaux |
| Macro par composant, avec signal et delta | famille macro | déclencheurs possibles et freins |
| Flux ETF, séries d'entrées, pression spot | famille flux | phrase « demande institutionnelle », rôle |
| Liquidations, funding, open interest | famille dérivés | amplificateur, levier |
| Cycle | famille cycle | contexte |
| Événements datés, importance, direction | `FutureEvent`, `EventCandidate` | contexte, calendrier, « attention ≠ sens » |
| Traduction en langage clair | `engines/interpretation.py` (refonte précédente) | cartes, détails, familles |
| Sources, fraîcheur, périodes | `MetricReading` | fiche détaillée d'une raison |

Nouveau fichier : `engines/situation.py` (le résumé et les rôles). Rien d'autre n'a été créé côté moteur.

## 2. Ordre de la Home

1. Actif, prix, 24 h / 7 j
2. **Décision** : ACHETER / ATTENDRE / VENDRE / DONNÉES INSUFFISANTES, avec risque, horizon et tendance
3. Une ligne discrète : fiabilité des données · clarté du marché · mise à jour, puis « Attendre depuis 21 h · Historique › »
4. **🧭 Situation actuelle** — 4 lignes (80 mots au plus), puis « Comprendre le mouvement › »
5. **🔎 Pourquoi ?** — 3 raisons compactes : titre, chiffre, une phrase, chevron
6. **🎯 Conditions à surveiller** — 🟢 opportunité, 🔴 invalidation, 📅 l'échéance qui compte
7. **🧩 Lecture du marché** — une ligne de conclusion par famille
8. **👀 À surveiller** — 2 événements au plus, puis « Voir tout »

### Ce qui a quitté la Home

| Bloc | Où il est maintenant |
|---|---|
| Rôles du résumé (déclencheurs, freins, contexte) | « Comprendre le mouvement » |
| « Pourquoi le marché monte ? » | « Comprendre le mouvement » |
| « Ce qui changerait la lecture » | fusionné dans « Conditions à surveiller » |
| « Ce qu'on attend » | fusionné dans « Conditions à surveiller » |
| Grande carte « Attendre depuis… » | une ligne sous la décision, l'historique au clic |
| Cartes « Données fraîches » et « Marché incertain » | la même ligne sous la décision |
| Constat détaillé de chaque famille | la page de la famille |

## 3. Le résumé de la situation

Deux textes sortent du même moteur (`engines/situation.py`) :

- `brief` — ce que la Home affiche : 4 phrases, 80 mots au plus. *Ce que le prix fait → ce qui l'accompagne → ce qui freine → ce qu'on attend.* Quand la place manque, le moteur retire d'abord le deuxième soutien, puis le deuxième frein, puis l'amplificateur ; **ce qu'on attend n'est jamais retiré**.
- `text` et `roles` — le récit complet, derrière « Comprendre le mouvement ».

**Cinq rôles, jamais confondus :**

| Rôle | Ce que c'est | Exemple de formulation |
|---|---|---|
| Déclencheur possible | un facteur macro qui a bougé dans le même sens | « Ce mouvement coïncide avec la détente du pétrole, ce qui réduit la pression inflationniste attendue. » |
| Soutien | de l'argent réel qui va dans le même sens | « Les flux ETF accompagnent le mouvement. » — jamais « le font monter » |
| Amplificateur | un effet mécanique qui prolonge un mouvement déjà en cours | « La fermeture forcée de positions vendeuses (61 M$ sur 24 h) a mécaniquement amplifié la hausse. » |
| Contexte | ce qui entoure : échéance à venir, cycle | « Adjudications du Trésor US dans 21 h » |
| Frein | ce qui empêche la confirmation | « un mouvement déjà étiré, un levier tendu » |

**Règles de langue :**
- « coïncide avec », « s'accompagne de », « peut contribuer à » pour une corrélation ;
- « a mécaniquement amplifié » réservé aux liquidations forcées, où le mécanisme est l'ordre lui-même, et seulement du bon côté (shorts liquidés pendant une hausse) ;
- aucun facteur aligné → « Aucune cause dominante ne ressort des données : plusieurs facteurs coïncident avec le mouvement sans qu'une explication unique puisse être établie » ;
- le mot « parce que » n'apparaît jamais dans le résumé (testé).

## 4. Au clic sur une raison

Une feuille s'ouvre avec :
- l'explication en langage clair ;
- les **données** (valeur, variation, période) ;
- **pourquoi cela compte** ;
- **ce que nous surveillons** ;
- l'**impact sur la décision** (POSITIF / NÉGATIF / MIXTE / INCONNU) et l'**horizon** ;
- la **source**, sa date et sa fraîcheur, avec « ⚠️ non actualisée » au-delà de deux jours.

Tout vient des lectures déjà calculées par les familles ; rien n'est recalculé pour l'affichage, et une mesure sans source n'est pas listée.

## 4 bis. Les conditions : un seul bloc

« Ce qu'on attend » et « Ce qui changerait la lecture » posaient la même question — *à quelle condition la décision bouge ?* — avec deux vocabulaires. Ils sont fusionnés dans « 🎯 Conditions à surveiller » :

- **🟢 Opportunité** : les conditions du moteur et les niveaux réels ;
- **🔴 Invalidation** : ce qui rendrait la lecture fausse ;
- **📅 Événement important** : au plus une échéance, et seulement si le moteur la note au-dessus de son seuil (`EVENT_ON_HOME = 0.3`). Une adjudication du Trésor programmée reste dans le calendrier : être planifiée ne rend pas un événement majeur.

Deux conditions qui nomment le même niveau sont une seule condition : la signature d'une condition est **le côté et le niveau** (`au-dessus de 87 396 $`), pas sa formulation. C'est ce qui faisait afficher « Clôture 4 h de BTC au-dessus de 87 396 $ » puis « BTC clôture (4 h) au-dessus de 87 396 $ » l'une sous l'autre.

## 5. Événements : attention ≠ direction

Chaque échéance porte deux informations distinctes :
- **attention** : critique, élevée, modérée, faible ;
- **sens** : favorable, défavorable, partagé, ou « inconnu tant que le résultat n'est pas publié ».

Une décision de banque centrale peut donc être « Attention critique · sens inconnu ». Aucune règle automatique du type « baisse de taux = hausse » n'existe.

## 5 bis. Nommer la donnée, pas la catégorie

La famille des flux s'appelait « Flux spot », ce qui pouvait se lire comme le marché spot dans son ensemble. Elle mesure les **ETF spot américains** et la **pression acheteuse au comptant** : elle s'appelle maintenant **« ETF & flux au comptant »**.

## 6. La famille 🐋 on-chain

Aucune source on-chain robuste n'est branchée aujourd'hui. Plutôt que de la masquer — ce qui laisserait croire que les baleines ont été mesurées et sont calmes — la carte est affichée et déclarée : « Source non branchée · Rien n'est déduit de l'activité des grandes adresses ». Elle redeviendra une famille mesurée dès qu'une source le permettra.

## 7. Tests

`tests/unit/test_situation.py` :
- le résumé nomme le mouvement, ses coïncidences, l'amplificateur, les freins et la décision ;
- chaque facteur garde son rôle (un amplificateur n'est jamais listé comme déclencheur) ;
- des liquidations du mauvais côté ne sont pas un amplificateur ;
- sans facteur aligné, aucune cause n'est revendiquée ;
- une séance ETF isolée n'est pas une tendance ;
- une échéance attendue est suivie de « puis la réaction du marché » ;
- six phrases au plus, jamais « parce que ».

Pour la simplification :
- le résumé de la Home fait 80 mots au plus et reste plus court que le récit ;
- les flux ETF sont un **soutien**, jamais un déclencheur ;
- deux conditions qui nomment le même niveau sont fusionnées ;
- une adjudication programmée n'atteint pas la Home sans note suffisante ;
- ATTENDRE dit toujours ce qui est attendu, dans le bloc fusionné.

`app/test/home_five_second_test.dart` : le résumé est affiché avant les raisons, les raisons avant les conditions, une raison ouvre ses chiffres et ses sources, **aucun titre de raison n'apparaît deux fois**, et ni le récit, ni « Pourquoi le marché monte ? », ni l'historique ne sont sur la Home.

## 8. Les trois niveaux de lecture

- **10 secondes** : décision, phrase courte, résumé.
- **1 minute** : pourquoi, ce qu'on attend, ce qui changerait la décision.
- **5 à 10 minutes** : chaque raison et chaque famille ouvrent leur page détaillée.

## 9. Le test « est-ce répété ? »

Les redondances trouvées et corrigées en regardant la page rendue :

| Ce qui était affiché deux fois | Correction |
|---|---|
| « Résistance importante — 87 396 $ » comme raison **et** comme conclusion de la famille Technique | une famille n'affiche jamais une carte déjà argumentée dans « Pourquoi ? » ; elle montre sa conclusion suivante |
| « Résistance importante — 87 396 $ » suivi de « 87 396 $ » dans la même tuile | la valeur n'est pas répétée quand le titre la porte déjà |
| Le niveau dans la phrase de décision **et** dans le résumé juste en dessous | la phrase de décision ne porte plus de chiffre : « mais le prix bute sous la résistance » |
| Le niveau dans le résumé **et** dans la condition juste en dessous | un frein qui nomme le niveau attendu est retiré du résumé |
| « Marché : Marché incertain » | le préfixe n'est ajouté que si le libellé ne commence pas déjà par « Marché » |

Deux autres corrections trouvées à l'écran :

- **les niveaux courts** (120 $ pour SOL) échappaient au dédoublonnage, qui ne reconnaissait que les nombres à quatre chiffres et plus ;
- **la lecture macro nommait Bitcoin sur les pages ETH et SOL** (« un dollar fort pèse sur les actifs risqués comme Bitcoin »). La macro est la même pour les trois actifs : elle ne nomme plus aucun d'eux.
- **garde-fou d'export** : un échec de lecture transitoire avait publié une page Cycle dont le graphique avait perdu tous les halvings passés. La page s'affichait quand même, simplement plus pauvre. L'export refuse désormais ce jeu de fichiers.

## 10. Reste à faire

- Les catalyseurs propres à l'actif (réactions de marché déjà mesurées par `asset_catalysts`) ne sont pas encore repris dans le résumé : il faudrait les faire passer jusqu'au moteur de décision.
- Les pages Macro, ETF, Dérivés, On-chain et Technique commencent par « En bref » depuis la refonte précédente ; l'ordre de priorité interne des pages Macro (Fed, inflation, pétrole, taux…) reste à ajuster.
- La page Cycle garde sa mise en page propre.
