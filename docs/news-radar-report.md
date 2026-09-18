# Radar autonome d'actualité marché — rapport

## 1. Audit préalable

L'audit demandé avant toute écriture de code a porté sur les 49 points de la
mission. Résultat par catégorie :

| Élément | État constaté | Suite donnée |
|---|---|---|
| Déduplication d'événements | **EXISTE** — `future_events/deduplication.py` (`signature`, `canonicalise`, `deduplicate`, `_merge`) | Réutilisé tel quel, non réécrit |
| Étapes législatives (13) | **EXISTE** — `RegulatoryStage` | Réutilisé |
| Hiérarchie de sources A→E | **EXISTE** — `FutureEventSourceTier`, `SourceTier` | Réutilisé, relié au radar |
| Score de pertinence | **EXISTE** — `EventRelevanceEngine` (plancher d'affichage 30) | Conservé, complété par l'attention |
| `expires_at` | **PARTIEL** — colonne présente en base, aucune logique de décroissance | Cycle de vie complet ajouté |
| Matérialité | **PARTIEL** — mot présent dans `future_decision.py`, aucun filtre | Filtre explicite ajouté |
| Calendriers banques centrales | **PARTIEL** — Fed seule | BCE et BoJ ajoutées |
| `ATTENTION_LEVEL` | **ABSENT** | Créé |
| Décroissance / `relevance_peak` | **ABSENT** | Créé |
| Regroupement d'événements | **ABSENT** | Créé |
| Section `news_radar` dans le health | **ABSENT** | Créée |

Rien n'a été recréé de ce qui existait.

## 2. Le principe appliqué

Une actualité n'est pas un signal directionnel. « Réunion de la Fed demain »
ne veut dire ni haussier ni baissier : cela veut dire qu'il faut surveiller, et
que la direction n'est pas encore connue.

Le code sépare donc deux notions qui ne se rencontrent jamais :

- `AttentionLevel` — NONE, LOW, MODERATE, HIGH, CRITICAL. Calculé à partir de
  la catégorie, de la proximité et de l'ampleur de la surprise. Aucune de ces
  entrées n'est directionnelle et la fonction ne peut produire aucune direction.
- `EventDirection` — FAVORABLE, NEUTRAL, UNFAVORABLE, MIXED, UNKNOWN. Reste
  `UNKNOWN` jusqu'à ce qu'un résultat existe et puisse être comparé à ce qui
  était attendu.

Aucune règle du type « baisse de taux = haussier » n'a été écrite. La direction
vient uniquement de l'écart entre le résultat publié et le consensus. Quand le
résultat va dans un sens et que les flux vont dans l'autre, le verdict est
`MIXED` : le dire est plus utile que choisir l'un des deux et cacher l'autre.

## 3. Ce qui disparaît tout seul

Une page qui accumule cesse de répondre à « qu'est-ce qui compte maintenant ».
Chaque élément porte donc son propre calendrier :

- la fenêtre de décroissance dépend de la catégorie — 12 h pour un chiffre de
  taux, 72 h pour un changement de règle, parce qu'un texte continue de compter
  pendant que le marché en tire les conséquences ;
- passé la moitié de la fenêtre, l'élément passe en `DIGESTING` ; au bout, en
  `EXPIRED` et son attention retombe à `NONE` ;
- une actualité **non programmée** — la majorité des actualités — suit le même
  cycle. C'est un défaut trouvé en test : sans cela, une dépêche sans date de
  calendrier ne serait jamais sortie de l'affichage.

Sur les données réelles : 114 événements suivis, 85 expirés automatiquement,
11 retenus pour la home.

## 4. Le filtre de matérialité

Mentionner Bitcoin n'est pas une qualification. Le filtre demande qu'un fait
soit identifiable — une décision, un vote, un chiffre, un incident — et écarte
ce qui ne fait qu'anticiper (« pourrait », « selon les analystes », « top 5 »,
« prévision de prix »). Une source sociale ne franchit jamais ce filtre : elle
reste une piste à confirmer auprès d'une source primaire, jamais une entrée.

Un élément non confirmé a une contribution de décision strictement nulle et une
attention plafonnée à `LOW`, quoi qu'il annonce.

## 5. Banques centrales ajoutées

La Fed n'est pas la seule source de liquidité mondiale. La BoJ est sans doute
celle qui compte le plus pour la crypto : le yen finance une large part du
portage mondial, et un changement de son coût peut forcer des débouclages qui
touchent tous les actifs risqués.

Deux distinctions que le code refuse de confondre, parce que les ignorer produit
des affirmations fausses avec assurance :

- le Conseil des gouverneurs de la BCE tient aussi des réunions **non**
  monétaires, qui ne fixent aucun taux ;
- une réunion de politique monétaire de la BCE dure deux jours et la décision
  tombe le **second**. S'ancrer au premier place l'événement un jour trop tôt,
  systématiquement.

Même logique pour la BoJ, dont la réunion s'étale sur deux jours : l'événement
est ancré au dernier. La BoJ ne publie aucune heure officielle, donc l'heure
retenue est marquée `time_is_approximate` et rien en aval ne la traite comme
officielle.

Sources : pages publiées par les institutions elles-mêmes. Aucune protection
contournée, aucune date écrite en dur — 19 décisions BCE et 16 réunions BoJ
sont lues à chaque rafraîchissement.

## 6. Ce que le health montre désormais

Une section `news_radar` compte les éléments suivis, affichés, expirés et non
confirmés, et isole le seul état qui pourrit en silence : un événement dont
l'heure est passée et dont personne n'a lu le résultat. La ligne est en base
récente, l'information est absente — c'est exactement ce qu'un contrôle de
fraîcheur ne voit pas. Cet état dégrade désormais le rapport et lève
`EVENT_RESULT_MISSING`.

## 7. Défauts trouvés et corrigés en cours de route

- **Actualités non programmées jamais expirées** — le cycle de vie ne
  s'appliquait qu'aux événements ayant une date de calendrier.
- **Échelle d'attention saturée** — 76 événements `CRITICAL` d'un coup, parce
  que la catégorie primait sur la distance. Une réunion dans cinq mois était
  traitée comme urgente. La proximité impose maintenant un plafond : tout ce qui
  est critique en même temps revient à n'avoir rien de critique.
- **Éléments expirés gardant leur attention** — ce qui a cessé de compter
  retombe à `NONE`.
- **Amplitude silencieusement ignorée** — le modèle d'événement expose
  `magnitude_effect`, pas `expected_movement` ; le mot-clé était accepté sans
  erreur et l'amplitude retombait à sa valeur par défaut.
- **Appariement d'identifiants défaillant** — le moteur de pertinence indexe sur
  `event.id`, le magasin porte aussi un identifiant canonique. L'enrichissement
  aurait échoué sans bruit. Les deux clés sont désormais enregistrées.
- **Isolation de test rompue** — le résumé du radar lisait la base de
  production depuis un test unitaire.

## 8. Limites assumées

- `directional_effect` du modèle historique vaut `NEUTRAL` par défaut, ce qui se
  lit « aucun effet attendu » alors que la vérité est « direction inconnue ».
  L'énum est partagée par tout le projet ; plutôt que de la modifier au milieu de
  cette mission, les événements portent `direction_known: False` et le radar
  porte le véritable `UNKNOWN`. À reprendre proprement.
- La comparaison résultat/consensus est fournie en entrée : le radar enregistre
  l'écart, il ne lit pas encore les publications lui-même.
- BoE et PBoC ne sont pas couvertes. La page de la BoE redirige et demande un
  traitement séparé ; elle n'a pas été ajoutée pour pouvoir dire qu'elle existe.
- Le rafraîchissement post-événement reste à faire : un chiffre publié à 14 h 30
  attend encore le passage suivant.

## 9. Vérification

- 1793 tests backend passants, 15 ignorés.
- 48 tests nouveaux : séparation attention/direction, ancrage au second jour
  BCE, ancrage au dernier jour BoJ, matérialité, expiration automatique,
  saturation de l'échelle, appariement des identifiants.
- `ruff` sans avertissement.
- Radar vérifié sur la base réelle, pas sur des fixtures.
