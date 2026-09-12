# Amélioration des patterns — consensus indépendant et validation prospective

Date d'exécution : 11 septembre 2026. Les nombres ci-dessous proviennent des
données locales BTC, ETH et SOL. Aucun seuil n'a été choisi à partir des
rendements futurs.

## Résultat honnête

Le résultat prédictif validé reste **1 combinaison sur 23** en quotidien :
`BTC double_top`, horizon 14 jours. Assouplir les filtres augmenterait ce nombre
artificiellement ; cela n'améliorerait pas le modèle.

Trois contrôles ont donc été ajoutés :

1. un comparateur causal indépendant inspiré de Lo–Mamaysky–Wang, fondé sur un
   lissage à noyau puis un appariement à des templates déclarés ;
2. un consensus un-à-un entre ce comparateur et le moteur de pivots de
   production, avec recouvrement temporel IoU >= 0,35 ;
3. un audit de rendement qui retire globalement les fenêtres se chevauchant
   entre BTC, ETH et SOL, puis compare chaque résultat à l'actif dans le même
   régime de marché causal.

L'accord améliore la confiance dans la **géométrie**. Il ne devient jamais une
probabilité de hausse ou de baisse.

## Consensus mesuré

| Unité | Accords indépendants | Détections comparables | Taux d'accord |
|---|---:|---:|---:|
| 1 jour | 18 | 267 | 6,7 % |
| 4 heures | 116 | 1 660 | 7,0 % |
| 1 heure | 395 | 7 129 | 5,5 % |
| **Total** | **529** | **9 056** | **5,8 %** |

Les 529 accords sont le sous-ensemble géométrique de meilleure qualité. Le
comparateur couvre maintenant les 13 familles effectivement émises par le
moteur : la couverture comparable passe de 3 664/9 056 à 9 056/9 056, soit
**100 %**. Les triples sommets/creux, wedges et bull/bear flags ont ajouté 76
accords (+16,8 %). Le taux baisse parce que 5 392 détections jusque-là ignorées
sont désormais réellement mises à l'épreuve ; il ne faut pas interpréter ce
dénominateur plus strict comme une régression.

## Vérification des rendements

Le consensus ne produit pas d'amélioration stable en quotidien ou en 4 h. En
1 h, les quatre horizons sont maintenant recomptés avec une seule fenêtre
globale à la fois, même si plusieurs actifs déclenchent ensemble :

| Horizon | N indépendant | Taux sens théorique | Rendement moyen | Excès vs même régime |
|---|---:|---:|---:|---:|
| 24 h | 314 | 52,23 % | +0,060 % | +0,081 % |
| 48 h | 293 | 54,61 % | +0,411 % | +0,446 % |
| 72 h | 265 | 55,47 % | +0,881 % | +0,906 % |
| 168 h | 194 | 48,97 % | -0,020 % | +0,096 % |

À 72 h, la p-valeur brute de l'excès est 0,0479, mais ce résultat **ne survit
pas** à la correction des quatre horizons explorés. Le verdict global est donc
`NO_MEASURABLE_EDGE`. L'excès est positif dans 6 années sur 9 seulement, donc
la stabilité est également classée `MIXED`. Il reste exploratoire et n'est pas
activé dans le signal de production.

Le précédent N=291 supprimait les recouvrements séparément par actif. Il
comptait donc encore comme indépendants des signaux BTC, ETH et SOL partageant
la même fenêtre future. La règle corrigée est identique dans l'audit et dans
l'expérience prospective. Sur les seules familles de la règle v1, elle donne
230 fenêtres à 72 h, 54,8 % de réussite et +0,707 % de rendement directionnel
moyen.

Le bull flag étendu atteint 68,0 % à 72 h, mais seulement sur 25 observations.
Cette lecture a été trouvée pendant l'exploration : elle est insuffisante et ne
devient ni un signal ni une conclusion.

Le test séparé des seules figures déjà confirmées par cassure donne **zéro
avantage validé**. La confirmation n'a donc pas été utilisée comme raccourci.

## Expérience prospective

Le candidat 1 h / 72 h est enregistré sous
`pattern_consensus__1h__textbook_direction__h72`. Seules les occurrences
postérieures à son horodatage d'enregistrement sont acceptées ; aucun résultat
historique ne peut faire mûrir l'expérience.

- cible : rendement dans le sens théorique après 72 barres de 1 h ;
- actifs : BTC, ETH et SOL ;
- minimum : 200 nouvelles observations ;
- rythme estimé : 25 observations indépendantes par an après suppression des
  fenêtres de 72 h qui se chevauchent entre actifs ;
- durée estimée avant conclusion : environ 8 ans avec seulement BTC, ETH et
  SOL. Ajouter davantage d'actifs liquides est le moyen propre de réduire ce
  délai ; compter des fenêtres corrélées comme indépendantes ne l'est pas.

Le scheduler met à jour cette expérience toutes les heures après la collecte
OHLCV. Elle ne place aucun ordre et ne produit aucune recommandation.
La liste des familles de cette expérience est gelée dans le code : ajouter de
nouveaux templates ne peut plus changer silencieusement une hypothèse déjà
enregistrée.

## Reproductibilité

```bash
python -m crypto_intel.cli pattern-consensus
python -m crypto_intel.cli research-patterns
python -m crypto_intel.cli research-patterns --confirmed-only
```

Artefacts produits :

- `data/research/pattern_consensus.json`
- `data/research/pattern_consensus_validation.json`
- `data/research/pattern_validation.json`
- `data/research/pattern_validation_confirmed.json`
- `data/research/live_experiments.json`

La correction FDR de `research-patterns` porte désormais réellement sur la
famille complète actifs × patterns × horizons. Auparavant, le code accordait
implicitement un budget de faux positifs séparé à chaque actif alors que le
rapport annonçait une correction globale.
