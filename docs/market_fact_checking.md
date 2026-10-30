# Vérification déterministe des affirmations

Mise à jour : 2026-10-30
Contrat : `claim-verification/1`

## Portée

Le moteur vérifie une affirmation avec des données déjà stockées et autorisées. Il n'appelle ni réseau ni LLM. Il conserve le texte original et ne corrige jamais silencieusement une entité, une période ou une mesure.

```text
texte / transcription
→ extraction conservatrice
→ modalité : fait, opinion, prévision, causalité
→ résolution de l'entité et de la période
→ preuves point-in-time
→ recalcul de la mesure demandée
→ comparaison
→ statut, confiance, méthode et sources
```

## Contrat `Claim`

Le résultat contient `claim_id`, textes original/normalisé, type, entités, valeur/unité/période/causalité revendiquées, date source, preuves, valeur recalculée, méthode, statut, confiance et notes.

| Statut | Sens |
|---|---|
| `CONFIRMED` | signe et amplitude dans la tolérance |
| `PARTIALLY_CONFIRMED` | direction correcte, amplitude non confirmée |
| `CONTRADICTED` | direction opposée ou écart déterministe |
| `UNVERIFIABLE` | données, période, unité ou preuve causale insuffisantes |
| `AMBIGUOUS` | identité ou série impossible à choisir sans supposition |
| `OUTDATED` | formulation explicitement actuelle réutilisée à une date ultérieure |
| `OPINION` | appréciation personnelle |
| `FORECAST` | conditionnel ou scénario futur |

## Ordre des règles

1. Le conditionnel reste `FORECAST`, même avec un pourcentage.
2. Une opinion reste `OPINION`, même si un nom ambigu est mentionné.
3. Une entité ambiguë bloque le calcul; « Nasdaq » seul ne choisit ni Composite ni Nasdaq-100.
4. Le ticker `SOL` n'est reconnu que sous une forme explicitement capitalisée ou dans un contexte crypto; le nom commun français « sol » n'est pas Solana.
5. Une formulation « aujourd'hui/actuellement » portant sur un actif ou indice devient `OUTDATED` lors d'un replay ultérieur. Pour un claim quantitatif, le moteur peut conserver le recalcul et ses preuves tout en refusant sa réutilisation comme valeur actuelle.
6. Une causalité directe exige une preuve causale explicite; la coïncidence temporelle ne suffit pas.
7. Une variation n'est calculée que si série, unité et période sont univoques.

## Point-in-time et révisions

La limite de preuve vaut `min(source_timestamp, as_of)`. Une observation publiée après l'affirmation ne peut pas la confirmer rétroactivement. La vue point-in-time sélectionne la version et sa provenance connues à cette limite, exclut les révisions ultérieures et ne charge que les bougies déjà closes à cet instant.

Lors d'un test Lexa historique, `as_of` est volontairement la date de la vidéo : une phrase « aujourd'hui » est vérifiée dans son contexte d'origine. Le endpoint sans `as_of` indique, lui, si une affirmation datée reste réutilisable aujourd'hui, sans ouvrir l'accès à des preuves postérieures pour le recalcul historique.

## Mesures quantitatives implémentées

La période actuellement automatisée est mensuelle.

Variation close-to-close :

```text
100 × (dernière clôture disponible / clôture avant la période - 1)
```

Recul depuis le sommet de la période lorsque le texte le demande explicitement :

```text
100 × (clôture courante / plus haute clôture connue de la période - 1)
```

Les preuves identifient les deux observations et leurs rôles. Le moteur ne substitue pas l'une de ces mesures à l'autre.

Tolérance par défaut : maximum entre 0,75 point de pourcentage et 10 % de l'amplitude revendiquée. C'est un paramètre d'ingénierie, pas une marge statistiquement calibrée.

## Entités et extraction

Le catalogue couvre actuellement Nasdaq Composite, Nasdaq-100, Dow Jones Industrial Average, S&P 500, Russell 2000, Nikkei 225, Euro Stoxx 50, BTC, ETH, SOL et Jerome Powell.

L'extracteur retient les variations en pourcentage, causalités explicites et affirmations chiffrées sur indices/personnes nommés. Les niveaux de prix et allocations restent dans le validateur de plan Lexa. Un nom proche mais non exact devient candidat `AMBIGUOUS`; aucune identité n'est affirmée.

Les fact-checks sont écrits dans `extraction.json`, les rapports humain/validation et, après import, dans `extra.fact_checks`. Les claims généraux `MARCHÉ` sont conservés avec chaque actif concerné.

## API

`POST /api/market-intelligence/claims/verify` accepte par exemple :

```json
{
  "text": "Le Dow Jones a perdu 10 % en octobre 2026.",
  "source_timestamp": "2026-10-26T22:00:00Z",
  "as_of": "2026-10-26T22:00:00Z"
}
```

Cette route partage l'absence d'authentification de l'API générale; elle doit rester sur loopback ou derrière un proxy authentifié.

## Limites et validation réelle

- extraction volontairement étroite, sans compréhension libre de toute phrase;
- calcul quantitatif centré sur la période mensuelle;
- catalogue d'entités fini;
- aucune causalité inférée d'une corrélation;
- branchement aux tests/imports Lexa et au endpoint explicite, pas à chaque RSS/article du pipeline général;
- aucune transcription réelle authentifiée n'a été fournie pour la recette. Les deux runs conservés et les fixtures sont explicitement fictifs; ils valident la plomberie, pas la qualité sur une vraie vidéo.
