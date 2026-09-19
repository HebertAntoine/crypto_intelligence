# Page « 🔄 Cycle du marché »

Date : 20/09/2026.

## Ce qui a été ajouté

| Élément | Où |
|---|---|
| Moteur de régime de cycle | `backend/crypto_intel/engines/cycle_regime.py` |
| Mesure des cycles passés et annotations | `backend/crypto_intel/engines/cycle_history.py` |
| Archive mensuelle | `backend/crypto_intel/engines/cycle_snapshots.py` + table `cycle_snapshots` |
| Historique BTC depuis 2011 | `backend/crypto_intel/history/btc_long_history.py` (Bitstamp, API publique) |
| Route de la page | `backend/crypto_intel/api/routes_cycle.py` → `/api/cycle/{actif}` |
| Écran | `app/lib/screens/cycle_page.dart` (+ `app/lib/api/cycle_models.dart`) |

La page s'ouvre depuis la ligne « Cycle » de l'accueil et depuis la carte Cycle de l'analyse complète.

## La phase vient des données, pas du calendrier

Le halving est un repère : il n'entre jamais seul dans la décision de phase. Chaque jour est classé à partir de plusieurs dimensions mesurées : position par rapport au record (nouveau sommet, distance, profondeur, ancienneté), structure long terme (sommets et creux sur deux trimestres, moyenne 200 jours et sa pente), momentum long terme (le trimestre courant comparé au précédent : accélère, ralentit, se retourne), régime de volatilité (expansion, contraction, stress) et rebond depuis le plus bas.

Phases : 🔵 Accumulation · 🔵 Récupération · 🟢 Expansion haussière · 🔥 Découverte de prix · 🟠 Transition · 🟠 Distribution possible · 🔴 Bear market · 🔴 Drawdown profond · ⚪ Indéterminé.
Le mot « possible » est obligatoire pour la distribution : elle n'est pas directement observable.

**Hystérésis.** Une nouvelle phase est d'abord *candidate* ; elle ne remplace la phase courante qu'après 15 clôtures. La page affiche donc la phase, la phase candidate et son avancement (par exemple « 11/15 »). Une baisse de 5 % pendant 48 h ne change rien.

**Direction.** Indépendamment de la phase : ↗️ Amélioration, ➡️ Stable, ↘️ Dégradation, d'après l'évolution d'un score de santé sur 30 jours.

## Sans biais rétrospectif

La chronologie est calculée en avant : chaque jour est classé avec les seules barres connues ce jour-là. Un test vérifie qu'ajouter des bougies ultérieures ne modifie aucune classification passée.

Les snapshots mensuels sont écrits une fois et jamais réécrits ; un changement de phase ajoute une ligne au lieu d'en modifier une. Chaque snapshot conserve phase, phase précédente, phase candidate, confiance, preuves, date de calcul, coupure des données et version du moteur.

## Le graphique

Prix BTC depuis le 18/08/2011 (bougies journalières : Bitstamp avant 2017, plateforme habituelle ensuite), échelle logarithmique, ligne prolongée jusqu'au prix du jour avec un repère 📍 Aujourd'hui.
Fond coloré par les phases **calculées**, halvings en lignes verticales ⚡, prochain halving affiché comme *estimation* 📅, 🏆 sommets et 🔻 creux majeurs confirmés a posteriori, 🌍 chocs de marché mesurés (−35 % sur 30 jours). Les bandes trop courtes sont fusionnées pour que le graphique montre les cycles et non les hésitations du classement.

## Cycles précédents (mesurés sur les mêmes bougies)

| Cycle | Sommet après le halving | Amplitude | Repli après le sommet | Durée de baisse | Récupération |
|---|---|---|---|---|---|
| 2012 | +366 j | +9 417 % | −86,9 % | 410 j | 771 j |
| 2016 | +525 j | +2 956 % | −84,1 % | 363 j | 732 j |
| 2020 | +547 j | +706 % | −77,6 % | 376 j | 476 j |
| 2024 | +533 j | +94 % | −54,2 % (en cours) | 268 j | non atteinte |

Une comparaison normalisée (100 au jour du halving) superpose les quatre cycles, avec la mention « comparaison historique, non prédictive ». Aucun calendrier de sommet ou de creux n'est produit : le creux du cycle en cours est affiché comme « plus bas local actuel », jamais comme « le creux ».

## Dans la décision

Le cycle est une famille parmi les six, jamais le moteur principal : poids 2 % à 24 h, 5 % à 7 j, 15 % à 30 j, signal plafonné à ±0,4, et il ne compte jamais comme famille concordante. Un halving récent ne produit pas d'ACHAT, un nouveau record ne produit pas de VENTE.

## BTC / ETH / SOL

BTC a le cycle complet. ETH et SOL affichent « 🔄 Régime crypto » (la phase de BTC) plus leur force relative face à BTC sur 30 jours, avec la mention « ETH n'a pas de halving : son cycle propre n'est pas inventé ».

## Lecture actuelle (20/09/2026)

🔵 Récupération ↗️ Amélioration, depuis 29 jours. 880 jours depuis le halving, −36 % sous le record du 06/10/2025. Motifs : rebond de 40 % depuis le dernier creux majeur, structure de moyen terme qui s'améliore, ancien record non repris.

## Tests

`tests/unit/test_cycle_regime.py` (23 tests) couvre les huit interdits du §26 : le compteur du halving ne fait pas un bull, un halving ne fait pas un ACHAT, un RSI élevé ne termine pas un bull (il n'est même pas une dimension du cycle), un repli ponctuel ne fait pas un bear, un nouveau record ne fait pas une VENTE, une ressemblance n'est pas une prévision, ETH et SOL n'ont pas de cycle de halving propre, et les données futures ne réécrivent pas un snapshot archivé.
`app/test/cycle_page_test.dart` (9 tests) vérifie l'écran, l'absence de prévision et la fusion des bandes.
Backend : 1923 réussis, 15 ignorés. Flutter : 391 réussis.

## Rafraîchissement

Prix : à chaque passe. Phase : réévaluée à chaque analyse, changement confirmé seulement après 15 clôtures. Archive : `crypto-intel.cli cycle-snapshot`, appelée par `scripts/refresh_all.sh`, une fois par mois (plus une ligne supplémentaire en cas de changement de phase).
