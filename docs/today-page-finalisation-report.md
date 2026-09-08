# Page « Aujourd'hui » — passe de fiabilisation

Design inchangé. Le travail porte sur la cohérence mathématique, la cohérence
sémantique, la gestion des données absentes ou périmées, et les derniers
détails de lecture.

---

## A. Fichiers modifiés

| Fichier | Ce qui change |
| --- | --- |
| `config/thresholds.yaml` | **nouveau** : sections `pressure` et `analysis_freshness` — source unique des seuils |
| `backend/crypto_intel/engines/market_pressure.py` | intensité séparée de la couverture, calcul exact, poids effectif, minimum de familles |
| `backend/crypto_intel/engines/today_view.py` | projection de la pression, niveaux mesurés depuis le prix d'analyse, alignement unifié, méthodologie repliable |
| `backend/crypto_intel/engines/analysis_context.py` | `AnalysisFreshness` FRESH/AGING/STALE/EXPIRED, phrases d'âge, verdict actif ou non |
| `backend/crypto_intel/engines/buy_opportunity.py` | `ChangeCondition.direction`, formulations corrigées |
| `backend/crypto_intel/core/labels_fr.py` | « Dans sa normale » → « Dans la norme » |
| `app/lib/api/models.dart` | fraîcheur calculée contre l'horloge du client |
| `app/lib/api/today_page.dart` | intensité, suffisance, poids effectif, sens des conditions, libellés de niveaux |
| `app/lib/widgets/today_blocks.dart` | contribution vs poids effectif, flèche par condition, libellés « Support à » |
| `app/lib/screens/today_screen.dart` | badge de couverture nommé, verdict périmé signalé, méthodologie repliée, icône sans cadre |
| `tests/unit/test_market_pressure.py` | réécrit — 40 tests |
| `tests/unit/test_analysis_freshness.py` | **nouveau** — 19 tests |
| `tests/unit/test_screen_qa.py`, `test_today_page.py` | contrôles croisés et mises à jour |
| `app/test/today_page_test.dart`, `today_layout_test.dart` | états d'intensité, couverture, fraîcheur |
| `app/assets/api_snapshots/*.json` | réexportés |

---

## B. Formule exacte de « Qui achète, qui vend ? »

```
poids_effectif(f) = poids(f) / Σ poids(familles disponibles)
score             = Σ ( score_famille(f) × poids_effectif(f) )
score             = clamp(score, -100, +100)
```

Une seule définition, dans `assess_pressure`. La vue ne recalcule rien : elle
lit `weighted_contribution` et `effective_weight` publiés par le moteur.

**Vérification sur les données réelles (BTC) :**

| Famille | Score | Poids effectif | Contribution |
| --- | --- | --- | --- |
| ETF / Institutions | +98,7 | 0,333 | **+32,89** |
| Spot / agressivité | −60,0 | 0,278 | **−16,68** |
| Dérivés / positionnement | +66,5 | 0,222 | **+14,77** |
| Funding / levier | −6,7 | 0,167 | **−1,12** |
| Baleines | — | — | — (exclue) |

Somme : **+29,86** · score affiché **+29,9**. L'écart de 0,04 est l'arrondi
d'affichage de chaque contribution au centième ; le score est calculé sur les
valeurs non arrondies et la note l'indique dans la feuille de détail.

---

## C. Seuils utilisés

Tous dans `config/thresholds.yaml`, lus par le moteur. Aucun n'est dupliqué
dans un widget.

**Intensité** (sur le score seul) :

| Bande | Libellé |
| --- | --- |
| +60 à +100 | FORTE PRESSION ACHETEUSE |
| +25 à +59 | PRESSION ACHETEUSE |
| −24 à +24 | ÉQUILIBRÉE |
| −59 à −25 | PRESSION VENDEUSE |
| −100 à −60 | FORTE PRESSION VENDEUSE |

**Couverture** (sur le nombre de familles) : 5 → Excellente · 4 → Bonne ·
3 → Partielle · 1-2 → Faible.

**Minimum** : 3 familles. En dessous, aucune intensité n'est annoncée.

**Fraîcheur** : 15 min → FRESH · 1 h → AGING · 3 h → STALE · au-delà → EXPIRED.

Le client porte les mêmes bornes de fraîcheur (il doit juger sans réseau) et
un test backend lit le fichier Dart pour vérifier qu'elles n'ont pas divergé.

---

## D. Renormalisation des poids

Poids théoriques : institutions 0,30 · spot 0,25 · dérivés 0,20 · funding 0,15
· baleines 0,10.

Une famille **indisponible** sort du dénominateur : elle ne vaut ni 0 ni
neutre, et les poids des familles restantes se renormalisent — leur somme
d'effectifs vaut toujours 1. Une famille **sans objet** pour l'actif (aucun ETF
spot SOL) sort en plus du décompte de couverture : SOL lit « 3/4 », pas
« 3/5 ».

Vérifié par test : retirer une famille qui disait la même chose que les autres
ne change pas le score, alors que la compter zéro le ferait baisser.

---

## E. Fraîcheur et hors ligne

Le backend publie `computed_at`, l'état et la phrase. **Le client recalcule
l'état contre sa propre horloge**, et c'est le point décisif : un instantané
embarqué fige « FRESH · il y a 0 min » au moment de son export, et l'app le
lirait tel quel des heures plus tard. La valeur publiée ne sert que de repli
quand l'horodatage manque.

Au-delà du seuil de péremption, le verdict reste lisible et daté mais porte un
bandeau « Analyse à actualiser · 3 h 52 » et n'est plus présenté comme une
décision active.

---

## F. Incohérences trouvées puis corrigées

1. **Intensité et couverture fusionnées.** « +30/100 · 4/5 familles · Forte »
   se lisait « forte pression » alors que « Forte » qualifiait la couverture,
   et le titre lui-même mélangeait les deux (« PRESSION ACHETEUSE PARTIELLE »).
   Deux échelles, deux vocabulaires, aucun mot commun.
2. **Deux définitions d'« apport ».** L'UI affichait « Apport +32,9 · poids
   30 % » : +32,9 contenait déjà le poids. On nomme désormais
   « Contribution : +32,9 · Poids effectif : 33 % ».
3. **Couverture mesurée deux fois.** Le niveau se calculait sur le poids
   pendant que la ligne comptait des familles : SOL affichait « 3/4 » avec un
   niveau calculé à 86 %. Le comptage fait foi.
4. **Niveaux mesurés contre le prix live.** Support et résistance sont
   calculés sur la clôture de l'analyse ; les comparer au prix du moment
   mélangeait deux instants. La distance part du prix de référence, et le
   payload dit lequel.
5. **Vocabulaires en collision.** « Divergent » (alignement) et « LECTURE
   MIXTE » (contradiction) se recouvraient. L'alignement est ALIGNÉE / MIXTE /
   DIVERGENTE ; le badge de contradiction devient « LECTURES OPPOSÉES ».
6. **Flèche unique par groupe.** « Cassure du haut du range » et « retour vers
   le bas du range » portaient la même. Chaque condition porte son sens.
7. **Le carré vide.** Vérifié : les six glyphes d'icônes **sont** présents dans
   la police livrée — ce n'était pas une icône manquante. C'était le cadre :
   un container 47 px bordé et teinté autour d'une icône de 27 px, qui se
   lisait comme un placeholder. Le cadre est retiré, l'icône reste.
8. Textes : « Plus de détails », « Dans la norme », « Support à »,
   « Résistance à », suppression de « enfin ».

---

## G. Tests ajoutés ou modifiés

`tests/unit/test_market_pressure.py` (40) couvre les douze cas demandés :
somme pondérée exacte, exclusion et renormalisation, couverture 3/5, absence
qui ne vaut pas zéro, +30 jamais « forte », +70 forte, −30 vendeuse, bande
neutre, et le cas « aucune famille » qui ne devient jamais 0/100.

`tests/unit/test_analysis_freshness.py` (19) couvre chaque palier d'âge, le cas
exact de la capture (13:24 lu à 17:16 → EXPIRED, verdict inactif), le mode hors
ligne, et le calcul des distances support/résistance depuis le prix de
référence.

`app/test/today_page_test.dart` : intensité contre couverture, l'instantané figé
sur FRESH qui ne trompe pas le client, le poids effectif qui reconstitue la
contribution.

`tests/unit/test_screen_qa.py` : les seuils de fraîcheur du client doivent
égaler ceux du YAML ; l'écran ne compose jamais un verdict de pression.

---

## H. Résultat réel des tests

```
backend : 982 passed, 15 skipped        (pytest)
client  : 164 passed                    (flutter test)
```

## I. Lint et analyse

```
ruff check backend/crypto_intel tests scripts   All checks passed!
dart analyze lib test                            No issues found!
flutter build web --release                      ✓ Built build/web
```

## Parcours des états

| État | Titre | Score | Couverture |
| --- | --- | --- | --- |
| couverture complète | PRESSION ACHETEUSE | +30,0 | 5/5 Excellente |
| couverture partielle | PRESSION ACHETEUSE | +40,0 | 3/5 Partielle |
| une famille indisponible | FORTE PRESSION ACHETEUSE | +80,0 | 4/5 Bonne |
| non applicable (SOL) | PRESSION ACHETEUSE | +30,0 | 4/4 Bonne |
| données insuffisantes | DONNÉES INSUFFISANTES | non annoncé | 2/5 Faible |
| aucune donnée | DONNÉES INSUFFISANTES | — | 0/5 Aucune |

| Âge | État | Verdict actif |
| --- | --- | --- |
| 2 min | FRESH | oui |
| 30 min | AGING | oui |
| 2 h | STALE | non |
| 4 h | EXPIRED | non |

---

## J. Ce que je n'ai pas pu valider

- **Le rendu visuel.** Je ne peux pas voir l'application tourner. Sur le carré
  vide j'ai vérifié ce qui est vérifiable — les glyphes sont dans la police
  livrée — et retiré le cadre qui, lui, ressemblait à un placeholder. Si un
  carré subsiste, ce sera une autre cause.
- **Le rendu de l'icône sur navigateur mobile réel**, distinct du rendu web de
  test.
- **La justesse des données amont** (Farside, Binance, Deribit) au-delà de leur
  fraîcheur et de leur cohérence interne.
- **Le comportement après plusieurs heures d'affichage continu** : la fraîcheur
  est recalculée à chaque rendu, mais rien ne force un rafraîchissement
  périodique de l'écran, donc l'âge se met à jour au prochain rebuild du
  widget.
