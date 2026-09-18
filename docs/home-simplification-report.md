# Home BTC / ETH / SOL — simplification radicale

## 1. Audit de la home existante

| Élément affiché | Verdict | Décision |
|---|---|---|
| Actif + prix (`_AssetHeader`) | conforme | conservé |
| Horizons 24 h / 7 j / 30 j | conforme | conservé |
| Grande carte verdict | **4 métriques** dont « Mouvement att. » et « Confiance » | ramené à 3 |
| Phrase du verdict | `_decisionHeadline` restituait « direction · amplitude » | remplacée par une phrase qui explique |
| Note de cohérence (`_CoherenceNote`) | bloc de texte supplémentaire sous la carte | repliée dans la phrase du verdict |
| « Pourquoi ? » | liste **scindée en deux groupes** + titre « CE QUI RESTE FAVORABLE » | une seule liste |
| Ligne de raison | pastille numérotée + badge à **4 lignes** (fraîcheur, direction, tendance, impact) | icône + titre + une phrase + **un** badge |
| « Ce qui ferait changer » | **deux cartes côte à côte** (acheter / vendre) | une seule, nommée d'après le verdict |
| « À surveiller » | date + titre + compte à rebours + fournisseur + badge + bouton déplier | jour + sujet, 3 lignes, sans doublon |
| Bouton « Voir les détails » | sur la home | descendu d'un niveau |

## 2. Retiré de la home

- **Confiance** — moyenne pondérée jamais calibrée contre les résultats. Elle décrit l'état du modèle, pas le marché.
- **Mouvement attendu** — une amplitude, que le lecteur confondait avec une direction.
- **Compte à rebours et nom du fournisseur** sur chaque échéance.
- **Note de fraîcheur** (`ACTUEL` / `PÉRIMÉ`) et **grade d'impact** sur chaque badge.
- **Tendance** (`EN AMÉLIORATION`) en troisième ligne de badge.
- **Second groupe de raisons** sous un titre séparé.
- **Seconde colonne de conditions** (« Pour passer à vendre » sous un verdict ATTENDRE).
- **Bouton d'accès à l'analyse complète.**

## 3. Déplacé en sous-page

Rien n'a été supprimé de l'application.

| Contenu | Nouvel emplacement |
|---|---|
| Confiance, amplitude attendue | feuille « Détails complets » |
| Scénarios, contexte marché, 5 familles, volatilité implicite, lecture par unité de temps | « Détails complets », atteinte depuis « Voir tout » |
| Chiffres bruts des flux, fraîcheur, fournisseur, chaîne causale | feuille de détail d'une raison, ouverte au clic |
| Calendrier complet | page événement |
| Conditions de l'autre direction | analyse complète |

## 4. Nouvelle hiérarchie

```
Actif + prix
Horizons
┌ EST-CE LE BON MOMENT POUR ACHETER ?
│ ATTENDRE
│ <phrase qui dit ce qui manque>
│ Risque · Horizon · Signaux
└
POURQUOI ?          (3–4 raisons, un badge chacune)
CE QUI FERAIT PASSER À ACHETER   (3 max)
À SURVEILLER        (3 max, jour + sujet)
```

Rien d'autre.

## 5. Règle de sélection des raisons

Inchangée côté moteur, déjà conforme : chaque facteur reçoit une contribution
calculée depuis son amplitude, sa pertinence, sa fraîcheur et sa proximité,
puis la liste est triée par contribution décroissante et coupée à quatre.
Aucune catégorie n'est câblée : si le pétrole pèse peu et les ETF beaucoup,
les ETF passent devant. Deux catalyseurs au maximum, et seulement si le moteur
sait expliquer leur mécanisme — une adjudication ordinaire reste dans
« À surveiller » plutôt que de déplacer une raison explicable.

Le badge suit une règle stricte : un catalyseur non encore publié porte
**À SURVEILLER**, jamais DÉFAVORABLE. Le décider d'avance reviendrait à parier
sur son issue.

## 6. Règle de sélection des événements

Tri par importance puis par proximité — l'ordre chronologique enterrait le FOMC
derrière trois adjudications de bons du Trésor. Trois lignes au maximum. Tout
événement déjà argumenté sous « Pourquoi ? » est retiré : la home ne dit pas
deux fois la même chose sous deux formes.

## 7. Mock réel — BTC

Relevé sur les snapshots livrés, pas rédigé à la main.

```
Bitcoin · BTC                              67 691,98 €  +1,68 % (24 h)
24 h    7 j    30 j

EST-CE LE BON MOMENT POUR ACHETER ?
ATTENDRE
Les signaux actuels ne donnent pas encore un avantage suffisamment
clair pour prendre position.

Risque          Horizon         Signaux
ÉLEVÉ           7 jours         Favorables

POURQUOI ?                                              Voir tout
🔎  Pression acheteuse au comptant                     FAVORABLE
    Les achats au marché dominent actuellement les ventes.
📈  Entrées nettes sur les ETF                         FAVORABLE
    Les entrées restent positives sur 20 séances, mais les 5
    dernières sont négatives.
📊  Tendance court terme porteuse                      FAVORABLE
    1 échelle haussière contre 0
🪙  Positionnement sur les dérivés                     NEUTRE
    Aucun changement de positionnement marqué.

CE QUI FERAIT PASSER À ACHETER
1  « Adjudication du Trésor américain (2 ans) » : issue plus
   favorable que ce qui était valorisé.

À SURVEILLER
Mercredi   Revenus et dépenses des ménages américains
```

## 8. Mock réel — ETH

```
EST-CE LE BON MOMENT POUR ACHETER ?
ATTENDRE
Les signaux se contredisent et aucune confirmation ne se dégage
pour l’instant.

Risque          Horizon         Signaux
ÉLEVÉ           7 jours         Mitigés

POURQUOI ?                                              Voir tout
🔎  Pression acheteuse au comptant                     FAVORABLE
📈  Entrées nettes sur les ETF                         FAVORABLE
🪙  Coût du levier                                     DÉFAVORABLE
🪙  Positionnement sur les dérivés                     NEUTRE

CE QUI FERAIT PASSER À ACHETER
1  Macro : inversion des conditions de liquidité mesurée sur les
   séries officielles.
2  Positionnement : reprise durable des positions à levier
   accompagnée d’une hausse du prix.
3  « Adjudication du Trésor américain (2 ans) » : issue plus
   favorable que ce qui était valorisé.
```

## 9. Mock réel — SOL

```
EST-CE LE BON MOMENT POUR ACHETER ?
ATTENDRE
Les signaux actuels ne donnent pas encore un avantage suffisamment
clair pour prendre position.

Risque          Horizon         Signaux
ÉLEVÉ           7 jours         Favorables

POURQUOI ?                                              Voir tout
🔎  Pression acheteuse au comptant                     FAVORABLE
🪙  Coût du levier                                     FAVORABLE
🪙  Positionnement sur les dérivés                     NEUTRE
    Le prix monte pendant que les positions à levier se ferment:
    des vendeurs à découvert se rachètent, ce qui ne confirme pas
    une tendance acheteuse.
📊  Compression de volatilité                          À SURVEILLER
    Pas de compression marquée.
```

## 10. Défauts trouvés pendant le travail

- **La carte se contredisait elle-même.** « Signaux : Favorables » apparaissait
  au-dessus de « les conditions ne sont pas encore assez favorables ». Les deux
  étaient exacts, la juxtaposition était absurde : ce qui manque n'est pas la
  qualité des signaux, c'est un avantage mesurable. La phrase le dit maintenant.
- **Chiffres bruts sur la home.** « 20 séances: +1 751.7 M$ ; 5 dernières
  séances: -623.8 M$ » — chaque chiffre est vrai et aucun n'aide à décider s'il
  faut regarder de plus près. Le sens des deux fenêtres est l'information ; les
  montants sont restés dans le détail.
- **Pluriel de gabarit affiché tel quel.** « 1 échelle(s) haussière(s) contre 0 »
  se lit comme une chaîne inachevée. La première regex de correction ne
  déclenchait pas : `\w` ne couvre pas les lettres accentuées, et « échelle »
  commence par é.
- **L'analyse complète devenait injoignable.** Retirer le bouton de la home
  orphelinait la feuille qui contient les scénarios, les cinq familles et la
  volatilité implicite. Elle est désormais atteinte depuis « Voir tout ».
- **La note de cohérence allait disparaître avec le bloc.** Elle porte deux cas
  d'honnêteté — vendre alors que le fond est haussier, acheter alors qu'il est
  baissier. Repliée dans la phrase du verdict plutôt que perdue.

## 11. Vérification

- 370 tests Flutter passants, analyzer sans avertissement.
- 1795 tests backend passants — le moteur n'a pas été touché.
- Nouveaux tests : les trois questions présentes, absence de 18 termes de
  jargon, quatre raisons maximum, exactement un badge par raison, trois
  échéances maximum, aucun doublon entre « Pourquoi ? » et « À surveiller »,
  absence de chiffres bruts et de pluriels de gabarit, absence de débordement à
  360 px, et le fait qu'un verdict ATTENDRE nomme toujours son obstacle.
- Les trois mocks ci-dessus sont des relevés d'écran, pas des exemples rédigés.

## 12. Limite assumée

`ExpectedMovement` et la confiance quittent la home mais restent dans la feuille
de détail : ils n'ont pas été supprimés du moteur, conformément à la consigne de
ne simplifier que ce que l'utilisateur voit.
