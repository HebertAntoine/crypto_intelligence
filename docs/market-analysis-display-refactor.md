# Refonte de l'affichage de l'analyse marché

Date : 19/09/2026. Aucun moteur, score, seuil ni donnée n'a été supprimé ou modifié.
Le veto NO_MEASURABLE_EDGE → ATTENDRE reste actif. Seules la présentation et
l'interprétation affichée changent.

## Où vit la présentation

`backend/crypto_intel/engines/decision_presentation.py` lit les familles déjà
scorées et produit :

- par famille, `extra.view` : sections groupées (emoji, titre, verdict, lignes
  compactes, phrase, « pourquoi » court), `lecture` (2–3 points), `changes`
  (2–4 déclencheurs), ligne d'accueil (`home`), libellé de confiance et
  problèmes de données ;
- par décision, `summary` : phrase de marché, tendance, qualité d'entrée,
  risque, 3 raisons maximum, 5 familles d'accueil, validation séparée,
  libellé de confiance, problèmes de données.

`decision_gates.decide` l'appelle en dernier ; le résultat est sérialisé dans
`HorizonDecision.to_dict()["summary"]`.

## Règles appliquées

| § | Règle | Mise en œuvre |
|---|---|---|
| 1 | Tendance ≠ entrée ≠ risque | trois champs distincts ; RSI ≥ 70 = « Momentum étiré » (🟠), jamais « Favorable » |
| 2 | Accueil : 3 raisons max | classées par |poids × score| de la famille, la validation exclue |
| 3 | 5 familles, 1 info clé | Technique, Dérivés, Macro, ETF & spot, Baleines & on-chain |
| 4, 8 | Priorités dynamiques | macro P1 taux réel / DXY / 2 ans, P2 VIX / Nasdaq / 10 ans, P3 le reste ; une publication de moins de 5 jours passe en P1 ; funding ≥ 85e centile et levier encombré passent en P1 |
| 5 | Page technique | Tendance & structure, Momentum, Volatilité (Bollinger en expansion ≠ resserrées), Performance sur une ligne ; une résistance déjà franchie est signalée comme telle |
| 6 | Dérivés | « Positionnement & levier » d'abord ; l'OI seul est « contexte » ; base et DVOL secondaires ; liquidations sur une ligne |
| 7 | ETF & spot | lecture globale ; désaccord ETF / spot = « 🟠 Flux global mitigé » et le titre ne dit plus « Les capitaux entrent » |
| 9 | Inflation | « +0,3 % m/m · +2,4 % sur un an », indice brut en détail |
| 10 | Dates | « Données : août 2026 · Publication : 15/09 (estimée) · Actualisé il y a 6 h » |
| 11 | Pourquoi ça compte | une phrase sur la carte, le texte complet au toucher |
| 14 | Scores | « Confiance élevée / moyenne / faible » ; chiffres au toucher ; qualité affichée seulement en cas de problème |
| 15 | Validation | « 🧪 Validation — Aucun avantage statistique robuste détecté : prudence renforcée. », séparée des raisons |
| 16 | Devises | niveaux techniques libellés en $ (paire USDT), prix d'en-tête en € |

Les liquidations n'ont aucune source connectée : elles gardent leur ligne
« ⚪ Source indisponible » mais ne déclenchent plus « Données partielles » à
chaque lecture.

## Tests

- `tests/unit/test_decision_presentation.py` (9 tests) couvre : RSI étiré en
  tendance haussière, Bollinger en expansion, niveaux en $, résistance franchie,
  OI en contexte, désaccord ETF / spot, priorités macro selon la récence,
  période ≠ publication, validation séparée des raisons.
- Tests Flutter mis à jour pour les sections groupées, la fiche de mesure et
  les libellés d'état.
