# LOT 4 — PatternGeometry : le backend détecte, le frontend dessine

État : livré. Testé, mesuré, et les limites sont nommées ci-dessous.

## Ce que le lot fait

Le graphique dessine désormais les figures que les détecteurs ont trouvées,
à partir de la géométrie que le backend publie — points nommés, droites,
neckline, zones de cassure. Le rendu est **générique** : aucun nom de figure
n'est codé dans l'application. Ajouter la géométrie à un détecteur muet suffit
pour que la figure apparaisse, sans toucher au frontend.

```
détecteur  ──►  PatternGeometry (temps + prix)  ──►  /chart  ──►  peintre
```

Trois interdits tenus, et vérifiés par des tests :

| Interdit | Ce qui le garantit |
|---|---|
| Redétecter une figure côté Flutter | Aucun détecteur dans `app/lib` ; le peintre ne lit que la charge utile |
| Inventer la géométrie manquante | `isDrawable` est faux si la géométrie est vide → rien n'est tracé |
| Afficher une figure sans sa géométrie | Une mention explicite remplace le tracé (voir plus bas) |

## Ce qui a été corrigé en chemin

**Le backend ne servait pas la géométrie.** Le serveur de développement
tournait sur du code antérieur au commit qui ajoute `structural_patterns`.
Redémarré ; les quinze instantanés livrés ont été réexportés. Un test échoue
maintenant si un instantané est exporté par un backend trop ancien.

**La variation de l'en-tête était ambiguë.** `+24,16 %` se lisait comme la
séance du jour alors que c'est l'écart entre la première et la dernière bougie
**visibles** — il change donc quand on zoome. L'en-tête écrit maintenant
« +24,16 % sur la vue ».

**Les étiquettes se recouvraient.** Un registre des rectangles déjà occupés est
tenu pendant chaque peinture ; l'en-tête le réserve en premier, et chaque
étiquette suivante se décale verticalement plutôt que de se poser sur une
autre. Faute de place, elle renonce : l'information reste dans les fiches en
dessous, alors qu'un empilement illisible ne serait nulle part.

**La fiche et le graphique parlaient de figures différentes.** `/structure`
détecte sur tout l'historique conservé, `/chart` sur la seule fenêtre affichée.
Sur SOL 4 h la fiche annonçait « ETE inversée » au-dessus d'un graphique où
elle n'était nulle part. La fiche suit désormais ce qui est dessiné, et les
figures vues hors de la fenêtre sont nommées à part, avec leur portée.

**Le bandeau de confluence débordait de 298 px** sur une largeur de téléphone :
le compte des familles sortait du cadre. Découvert par le test de cohérence,
corrigé.

## Ce qui est réellement dessinable aujourd'hui

Mesuré sur les données du 8 septembre 2026, périodes telles que l'application
les demande :

| Actif | Unité | Figure | Géométrie |
|---|---|---|---|
| ETH | 4 h | `double_top` | 2 points, neckline, zone de cassure |
| ETH | 1 h | `double_top` | 2 points, neckline, zone de cassure |
| ETH | 15 min | `double_top` | 2 points, neckline, zone de cassure |
| SOL | 1 j | `bull_flag` | **aucune** — détectée, non traçable |
| BTC | toutes | — | aucune figure |

BTC ne présente aucune figure sur aucune unité : c'est un résultat, pas une
panne. Pour voir le rendu, il faut ETH.

## Ce qui a été vérifié, et comment

- **14 tests** sur le contrat de géométrie et l'accrochage
  (`app/test/pattern_geometry_test.dart`), écrits contre la charge utile
  réellement produite par le backend, pas une charge inventée.
- **L'accrochage** est prouvé, pas affirmé : un canevas d'enregistrement note
  ce que le peintre dessine, et le test compare la position de chaque sommet à
  celle de la mèche de **sa propre bougie**, avant et après un déplacement et
  un zoom. Un décalage de 3 px fait échouer trois tests.
- **La déduplication** : le backend publie la neckline deux fois (dans
  `trend_lines` et dans son champ dédié). La tracer deux fois l'épaissirait
  sans rien ajouter. Supprimer la déduplication fait échouer le test.
- **31 tests** sur les instantanés livrés : la clé est présente, et tout point
  d'une figure traçable tombe dans la fenêtre dessinée. Retirer la clé d'un
  fichier, ou déplacer un point hors fenêtre, fait échouer le test.
- **4 tests** d'intégration backend sur une série contenant un vrai double
  sommet : la route publie la géométrie, avec des horodatages et jamais des
  index de barres. Vider `structural_patterns` dans la route fait échouer
  deux tests.
- **Totaux** : 271 tests Flutter, 994 tests backend, `dart analyze` propre,
  `ruff check` propre, `flutter build web --release` réussi.

## Ce que je n'ai pas pu vérifier

J'ai regardé le rendu : le graphique est peint dans un fichier image
(`app/test/chart_render_preview_test.dart`, actif seulement si
`PREVIEW_DIR` est défini) et j'ai inspecté les images. Les cercles des sommets
tombent exactement sur les mèches, la neckline est prolongée jusqu'au bord
droit, la zone de cassure encadre bien la figure, et l'étiquette de résistance
ne chevauche plus l'en-tête.

**Mais `flutter test` peint chaque glyphe en rectangle plein** : j'ai vérifié
les positions et l'absence de chevauchement, pas le texte lui-même. Je n'ai
pas lu « SOMMET 1 » à l'écran. Le nombre de lignes de l'en-tête et le nombre
de mots de chaque étiquette correspondent à ce que le code produit, c'est tout
ce que l'image permet d'affirmer.

## Ce qui reste

- **LOT 5** — valider le rendu sur `double_top` en usage réel (ETH), et à
  d'autres périodes que celles exportées.
- **LOT 6** — indicateurs (EMA, Bollinger, RSI, MACD) avec bascules.
- **LOT 7** — plein écran.
- **LOT 8** — remplir `PatternGeometry` **côté backend** dans les détecteurs
  muets : `bull_flag`, `triple_top`, `inverse_head_and_shoulders`,
  `head_and_shoulders`. Tant que ce n'est pas fait, ces figures s'affichent
  avec « le détecteur n'a pas fourni de tracé ».
- **LOT 9** — nouveaux détecteurs. Non commencé, comme demandé.

Deux points relevés hors périmètre, non corrigés :

1. `notes` et `invalidation_rule` des figures sont **en anglais**
   (« two tops within 0.31 ATR of each other »). Ils ne sont pas affichés sur
   le graphique pour cette raison. À traiter avec la traduction du moteur
   « Pourquoi ? » (LOT 2 de ce chantier).
2. Les endpoints `/research/*` mettent plusieurs minutes et bloquent le worker
   unique, ce qui fait échouer `scripts/export_flutter_static_api.py` par
   dépassement de délai. Seuls les quinze instantanés `/chart` ont été
   réexportés, depuis une instance sans planificateur.
