# Intégration des analyses vidéo — LOT 5 : plan de marché et graphique

Date : 07/10/2026.

## 1. Résultat de l'audit

Le dépôt possédait déjà la chaîne locale Lexa : transcription supervisée, extraction vérifiée, analyses et versions immuables, conditions de clôture, notifications et onglet privé. Les manques observés étaient les suivants :

- aucun graphique de bougies annoté dans une fiche d'analyse ;
- une zone était stockée comme un prix unique, sans borne haute ;
- les anciennes entrées déjà traversées pouvaient redevenir une action proposée ;
- l'après-vidéo n'était pas résumé (plus haut, plus bas, niveaux atteints, performance) ;
- la source était affichée en dur comme « Lexa », ce qui empêchait d'identifier proprement un autre analyste ;
- les plans purement descriptifs affichaient « ATTENDRE » au lieu de « AUCUNE ACTION » ;
- les types SELL, WAIT et WATCH n'étaient pas représentés de bout en bout.

### Données réellement disponibles

Aucun fichier vidéo, audio ou sous-titre crypto réel n'est présent dans le dépôt ou dans le répertoire de données local. La base `data/lexa/lexa.db` ne contenait aucune vidéo, analyse ou niveau. Les seuls plans trouvés sont des fixtures explicitement fictives utilisées par les tests.

En conséquence, **aucune analyse réelle n'a été inventée ni importée**. Le système est prêt à recevoir les enregistrements, transcriptions ou saisies manuelles réelles par les voies existantes. Les fixtures ne sont jamais présentées comme des propos d'analyste.

## 2. Modèle enrichi sans perte d'historique

- `lexa_videos.source_name` mémorise l'analyste ou la chaîne de provenance ; « Lexa » reste seulement la valeur par défaut compatible avec l'existant.
- Un niveau possède désormais une borne basse et, pour une zone, une borne haute (`value` + `value_high`).
- Les valeurs originales et corrigées restent distinctes pour les deux bornes.
- Les types couverts sont BUY_ZONE, STRONG_BUY/REINFORCEMENT, TARGET/TAKE_PROFIT, SELL, SUPPORT, RESISTANCE, BREAKOUT, INVALIDATION, CONFIRMATION, WAIT et WATCH.
- Chaque nouvelle vidéo produit toujours une version immuable. Le plan courant et toutes les versions historiques sont livrés séparément au graphique.
- Chaque niveau conserve son horodatage, sa citation, sa provenance et son état de marché.

Le validateur anti-invention exige que les deux bornes d'une zone extraite apparaissent dans la transcription. Si la seconde borne est absente, la zone est rejetée au lieu d'être complétée artificiellement.

## 3. Moteur de décision

La réponse d'une fiche contient maintenant :

- le prix actuel, la variation 24 h et la variation depuis la vidéo ;
- le plus haut et le plus bas depuis la publication ;
- les niveaux touchés et leur date ;
- l'indication qu'une opportunité d'entrée est déjà passée ;
- la performance observée après la première entrée, quand elle est calculable ;
- le statut et l'action à faire maintenant.

Règles importantes :

- une ancienne zone d'entrée déjà touchée n'est jamais reproposée comme achat immédiat ;
- un premier objectif atteint déclenche une prise de profit sans terminer tout le plan si d'autres objectifs subsistent ;
- une analyse sans action explicite produit `AUCUNE ACTION` ;
- un niveau SELL explicite peut produire `VENDRE` ;
- TOUCH, CLOSE et CONFIRMATION restent trois états distincts ;
- pour une condition ABOVE sur une zone, la clôture est comparée à la borne haute ; pour BELOW, à la borne basse ;
- les niveaux analyste, le plan utilisateur et l'interprétation de l'application ne sont jamais fusionnés.

## 4. Graphique interactif

La fiche crypto affiche immédiatement après « Que faire maintenant » un graphique de bougies interactif alimenté par les données Binance spot déjà utilisées par le backend.

Le contrat du graphique transporte au maximum 600 bougies, les niveaux de la version courante, les niveaux de toutes les versions précédentes et les dates de publication. Les annotations portent explicitement leur source et leur provenance.

Filtres disponibles : anciennes analyses, ordres, supports/résistances, confirmations, objectifs et invalidations.

Convention visuelle :

| Élément | Rendu |
|---|---|
| Achat | vert |
| Renforcement | bleu |
| Support / résistance | blanc |
| Objectif / prise de profit | doré |
| Vente / invalidation | rouge |
| Confirmation | jaune |
| Ancienne analyse | gris pointillé |
| Zone | bande colorée entre les deux bornes |
| Date d'analyse | repère vertical |

Le moteur de graphique partagé accepte ces annotations sans modifier les autres écrans lorsque la liste est vide. Les niveaux annotés participent aussi au calcul de l'échelle verticale, afin de ne pas être coupés.

## 5. Interface mobile

La fiche sépare clairement :

1. l'action actuelle ;
2. le graphique et ses filtres ;
3. le prix au moment de la vidéo et le prix actuel ;
4. « Ce qui s'est passé ensuite » ;
5. le plan analyste, le plan utilisateur et la lecture indépendante de l'application ;
6. l'historique immuable.

Les zones sont affichées comme des intervalles, pas comme une moyenne inventée. La saisie manuelle permet de renseigner le nom de la source et une borne haute facultative avec validation. Le rendu a été exercé à 390 × 900 et la suite existante couvre également 360 px.

## 6. Tests de la mission

| Cas demandé | Vérification |
|---|---|
| Ancienne analyse et mouvement déjà passé | aucune ancienne entrée n'est reproposée ; le mouvement et l'opportunité passée sont exposés |
| Analyse actuelle encore active | état courant, prochaine action et niveaux courants restent actifs |
| Zone d'achat puis premier TP atteint | zone touchée, premier TP atteint, prise de profit sans clôture prématurée du plan |
| Une crypto sans action | statut et verdict `AUCUNE ACTION` |
| Deux vidéos successives contradictoires | version précédente immuable, relation CONTRADICTS/REPLACES et historique graphique |
| Support/résistance seulement | niveaux visibles, sans ordre d'achat ou de vente inventé |

Sont aussi testés : validation des deux bornes dans la transcription, provenance des annotations, filtres du graphique, absence de débordement iPhone, changement de capital et séparation USER_PLAN/ANALYST/MARKET_VALIDATION.

Validation du 07/10/2026 :

- analyse statique Dart : aucun problème ;
- tests Flutter complets : **409 réussis** ;
- tests backend Lexa ciblés : **68 réussis, 3 désélectionnés** ;
- Ruff sur les fichiers Python modifiés : réussi.

Les trois tests désélectionnés utilisent `starlette.testclient.TestClient`. Dans cet environnement ils se bloquent dans le portail HTTP avant l'appel de la route ; les routes et services Lexa correspondants sont couverts directement. La passe globale backend a été interrompue lorsqu'un autre test utilisant la même pile HTTP a reproduit ce blocage. Le contrôle mypy du projet reste lui aussi empêché par le parseur configuré, qui refuse une syntaxe Python 3.12 présente dans `numpy/__init__.pyi`.

## 7. Périmètre restant

Il ne reste aucune donnée réelle à intégrer tant que les vidéos, audios ou transcriptions ne sont pas fournis. Lorsqu'ils le seront, l'import doit rester local et supervisé : transcription, extraction, vérification des valeurs contre la source, puis validation/import. Les notifications restent in-app tant qu'aucun fournisseur push n'est configuré.
