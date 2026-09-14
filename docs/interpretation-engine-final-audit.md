# Interpretation engine — audit final

**Date** : 13/09/2026
**Suites exécutées intégralement** : backend `pytest tests/` → **1546 passés, 15 ignorés** ·
Flutter `flutter test` → **336 passés** · `ruff check backend/ tests/` → clean ·
`flutter analyze lib/ test/` → clean.

---

## 1. Architecture avant

Chaque moteur produisait directement le texte destiné à l'écran, et l'écran
complétait ce qu'il ne trouvait pas. Trois conséquences mesurées :

* une même famille était calculée deux fois, par deux chemins différents
  (la direction publiée venait de la composante de pression dominante, le texte
  d'un autre calcul) ;
* l'UI choisissait ses explications par **mot-clé dans le titre**, ce qui la
  rendait dépendante du libellé plutôt que de la donnée ;
* les drapeaux internes (`Bollinger squeeze=False`, `volatilité low`) partaient
  tels quels vers l'écran, qui les traduisait à l'affichage — donc l'UI
  interprétait une valeur financière.

Il n'existait aucun instrument pour mesurer la cohérence de cet ensemble.

## 2. Architecture après

```
RawEvidence (providers, base)
   ↓
moteurs existants (pressure, flows, technical, volatility, events)  ← inchangés
   ↓
factor_semantics.py      → FactorAssessment: direction / trend / impact /
                            confidence / availability / causal_chain /
                            missing_requirements / provider
   ↓
payload API (families.factors)
   ↓
Flutter: rendu seulement — aucune interprétation financière
   ↓
interpretation_validator.py → InterpretationQualityReport (8 dimensions)
```

Point clé : la couche **normalise** ce que les moteurs ont mesuré, elle ne le
recalcule pas avec un second jeu de seuils. `pressure_component_assessment`
reprend la direction et le score produits par `market_pressure` tels quels.

## 3. Bugs trouvés et causes racines

| # | bug | cause racine |
|---|---|---|
| 1 | Un facteur ETF expliqué avec le vocabulaire baleines | le libellé « Flux institutionnels **& baleines** » faisait matcher la branche `baleine` **avant** la branche `etf` dans une recherche par mot-clé |
| 2 | Source affichée = « Positionnement & dérivés » | l'UI utilisait `family.label` faute de fournisseur dans le payload |
| 3 | ETH 24 h : décision SELL sans aucun facteur négatif | le funding portait la direction de la famille et **n'avait aucune interprétation normalisée** — trou de couverture |
| 4 | `spot` et `funding` publiés en `UNKNOWN` alors que mesurés | `_COMPONENT_DIRECTION` mappait le vocabulaire de biais (`BEARISH`) alors que `market_pressure` nomme ses directions côté trader (`SELL`) |
| 5 | `Bollinger squeeze=False` visible par l'utilisateur | le texte était formé dans le moteur en anglais technique, traduit ensuite côté écran |
| 6 | `volatility` en `PARTIAL` sans manque déclaré | la fraîcheur n'était pas transmise à l'évaluateur |
| 7 | `technical` sans chaîne causale ni fournisseur | la branche « aucune échelle exploitable » sortait avant de les renseigner |

Les bugs 1, 2, 5 étaient invisibles au backend ; 3, 4, 6, 7 ont été trouvés par
le validateur, pas par lecture.

## 4. Règles d'interprétation posées

**UNKNOWN ≠ NEUTRAL.** NEUTRAL est une mesure : la donnée a été lue et ne montre
pas de biais. UNKNOWN est un aveu : l'issue n'a pas eu lieu, ou l'instrument ne
parle pas de direction. Une donnée absente n'est ni l'un ni l'autre :
`availability = UNAVAILABLE`.

**Direction ≠ impact ≠ confiance.** Un FOMC vaut `UNKNOWN` + `VERY_HIGH` +
confiance basse sur le sens. Les trois sont des champs distincts, et le
validateur refuse qu'un facteur absent porte un impact élevé.

**L'amplitude ne donne jamais un sens.** Compression de Bollinger et volatilité
implicite portent `impact_on_direction = "NONE"` ; le validateur refuse qu'un
tel facteur soit `POSITIVE` ou `NEGATIVE`. Seule l'asymétrie d'options peut
porter une direction.

**Multi-fenêtres.** Les flux publient une direction (régime 20 séances) **et**
une tendance (fenêtre 5 séances). Un régime contredit par sa fenêtre récente est
plafonné à `MODERATE`.

**Un transfert n'est pas une vente.** Sans signal corroborant, les mouvements de
baleines restent `UNKNOWN` avec le manque déclaré.

**Le funding se lit en percentile**, et un coût très bas n'est pas un signal
d'achat : c'est un état qui accompagne souvent un marché faible.

**Un écart contrats/comptant positif est normal**, pas haussier.

**Périmé n'est jamais fiable** : `STALE` plafonne la confiance à MEDIUM.

## 5. Fichiers et moteurs modifiés

| fichier | rôle |
|---|---|
| `backend/crypto_intel/engines/factor_semantics.py` | couche d'interprétation: 10 évaluateurs, modèle canonique |
| `backend/crypto_intel/engines/interpretation_validator.py` | **nouveau** — validateur + rapport 8 dimensions |
| `backend/crypto_intel/engines/future_context.py` | publication des facteurs, couverture complète, résumé technique en français |
| `backend/crypto_intel/engines/future_decision.py` | `factors` dans le payload |
| `app/lib/api/future_models.dart` | `FutureFactorRead` complet |
| `app/lib/screens/future_analysis_screen.dart` | rendu seul; guidance indexée par clé |
| `tests/unit/test_factor_semantics.py` | 28 tests |
| `tests/unit/test_interpretation_invariants.py` | **nouveau** — 126 tests |
| `app/test/decision_simplification_test.dart` | 3 tests d'interface ajoutés |

Aucun seuil de décision n'a été modifié. Les moteurs de mesure
(`market_pressure`, `institutional_flow`, `volatility`) sont inchangés.

## 6. Tests

**Ajoutés** : les 27 tests nommés du §37, 5 invariants du §38 appliqués aux 9
payloads livrés, 5 tests de mutation du §41, 3 tests d'interface du §39, le scan
textuel du §43.

**Les tests de mutation sont la preuve que le validateur mesure réellement** :
en inversant un signe de flux, en rendant directionnel un facteur indisponible,
en rendant haussière une compression, en associant une donnée périmée à une
confiance élevée, et en effaçant un fournisseur, chaque mutation est détectée et
nommée. Sans eux, « 100 % » pourrait n'être que du vide.

## 7. Score final — mesuré, non déclaré

| dimension | score | contrôles |
|---|---|---|
| semantic_consistency | **100,0 %** | 93 |
| source_integrity | **100,0 %** | 112 |
| freshness_consistency | **100,0 %** | 67 |
| direction_consistency | **100,0 %** | 94 |
| impact_consistency | **100,0 %** | 70 |
| decision_consistency | **100,0 %** | 56 |
| text_consistency | **100,0 %** | 127 |
| horizon_consistency | **100,0 %** | 12 |

**631 contrôles, 0 échec.** Aucune dimension n'est vide.

Progression sur les passes successives : 77,8 % / 82,3 % / 98,2 % sur trois
dimensions en passe 1 → 100 % partout en passe 3, puis deux défauts textuels
trouvés en passe 4 et corrigés en passe 5.

## 8. Audit des 5 familles

| famille | état | sur 9 combinaisons |
|---|---|---|
| Macro & liquidité | AVAILABLE | 9/9 |
| Catalyseurs & réglementation | **UNAVAILABLE**, raison déclarée | 9/9 |
| Flux institutionnels & baleines | AVAILABLE | 9/9 |
| Positionnement & dérivés | AVAILABLE | 9/9 |
| Technique & volatilité | AVAILABLE | 9/9 |

Aucune famille n'est masquée. L'indisponibilité des catalyseurs est publiée avec
sa raison et ne porte aucune direction — traitement correct au sens du §46.

## 9. Données indisponibles, correctement gérées

| donnée | état | conséquence |
|---|---|---|
| Anticipations de marché (CME FedWatch) | UNAVAILABLE — licence commerciale | événements en `UNKNOWN`, confiance réduite de 25 % |
| Catalyseurs réglementaires | UNAVAILABLE | famille déclarée, aucune direction |
| Flux institutionnels SOL | UNAVAILABLE | aucun facteur `flows` publié pour SOL |
| `funding_state` dans le contexte d'analyse | absent | impact du positionnement reste MODERATE |

Aucune de ces absences n'a été comblée par une valeur fabriquée.

## 10. Matrice BTC/ETH/SOL × 24h/7d/30d

#### BTC — 24h · **SELL** (confiance 0.61)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| derivatives | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| technical | **NEGATIVE** | STABLE | MODERATE | LOW | AVAILABLE | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | LOW | LOW | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | MODERATE | MEDIUM | AVAILABLE | Deribit | YES |

#### BTC — 7d · **WAIT** (confiance 0.458)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| flows | **POSITIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | farside | YES |
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| derivatives | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| technical | **POSITIVE** | STABLE | MODERATE | LOW | AVAILABLE | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | MEDIUM | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | MODERATE | MEDIUM | AVAILABLE | Deribit | YES |

#### BTC — 30d · **WAIT** (confiance 0.495)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| flows | **POSITIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | farside | YES |
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| derivatives | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| technical | **NEUTRAL** | UNKNOWN | LOW | MEDIUM | AVAILABLE | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | MEDIUM | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | MODERATE | MEDIUM | AVAILABLE | Deribit | YES |

#### ETH — 24h · **SELL** (confiance 0.56)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| positioning | **NEUTRAL** | STABLE | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| derivatives | **NEUTRAL** | UNKNOWN | LOW | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| technical | **UNKNOWN** | UNKNOWN | LOW | LOW | PARTIAL | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | LOW | LOW | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | MODERATE | MEDIUM | AVAILABLE | Deribit | YES |

#### ETH — 7d · **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| flows | **POSITIVE** | STABLE | HIGH | HIGH | AVAILABLE | farside | YES |
| positioning | **NEUTRAL** | STABLE | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| derivatives | **NEUTRAL** | UNKNOWN | LOW | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| technical | **UNKNOWN** | UNKNOWN | LOW | LOW | PARTIAL | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | LOW | LOW | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | MODERATE | MEDIUM | AVAILABLE | Deribit | YES |

#### ETH — 30d · **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| flows | **POSITIVE** | STABLE | HIGH | HIGH | AVAILABLE | farside | YES |
| positioning | **NEUTRAL** | STABLE | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| derivatives | **NEUTRAL** | UNKNOWN | LOW | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| technical | **UNKNOWN** | UNKNOWN | LOW | LOW | PARTIAL | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | MEDIUM | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | MODERATE | MEDIUM | AVAILABLE | Deribit | YES |

#### SOL — 24h · **SELL** (confiance 0.61)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | HIGH | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| derivatives | **NEGATIVE** | UNKNOWN | HIGH | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| technical | **NEGATIVE** | STABLE | MODERATE | LOW | AVAILABLE | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | LOW | LOW | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | LOW | LOW | UNAVAILABLE | — | YES |

#### SOL — 7d · **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | HIGH | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| derivatives | **NEGATIVE** | UNKNOWN | HIGH | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| technical | **UNKNOWN** | UNKNOWN | LOW | LOW | PARTIAL | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | MEDIUM | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | LOW | LOW | UNAVAILABLE | — | YES |

#### SOL — 30d · **WAIT** (confiance 0.42)

| facteur | direction | tendance | impact | confiance | disponibilité | fournisseur | cohérent |
|---|---|---|---|---|---|---|---|
| positioning | **NEGATIVE** | DETERIORATING | MODERATE | HIGH | AVAILABLE | Open interest multi-exchange, comptes Binance | YES |
| spot | **NEGATIVE** | UNKNOWN | HIGH | HIGH | AVAILABLE | Binance klines, taker buy base volume / volume total | YES |
| derivatives | **NEGATIVE** | UNKNOWN | HIGH | HIGH | AVAILABLE | open interest multi-exchange et répartition des comptes Binance | YES |
| funding | **NEGATIVE** | UNKNOWN | MODERATE | HIGH | AVAILABLE | funding.rate Binance, percentile glissant par actif | YES |
| technical | **UNKNOWN** | UNKNOWN | LOW | LOW | PARTIAL | Séries de bougies internes | YES |
| volatility | **UNKNOWN** | UNKNOWN | HIGH | MEDIUM | AVAILABLE | Séries de bougies internes | YES |
| implied_volatility | **UNKNOWN** | UNKNOWN | LOW | LOW | UNAVAILABLE | — | YES |
## 11. Anciennes → nouvelles interprétations

| facteur | avant | après |
|---|---|---|
| ETF BTC | « POSITIF » | `POSITIVE` + `DETERIORATING`, impact plafonné à MODERATE |
| Explication ETF | vocabulaire baleines (transferts, plateformes) | offre/demande nette par les ETF au comptant |
| Funding | invisible dans la sémantique | facteur à part entière, lu en percentile |
| `spot` / `funding` | `UNKNOWN` bien que mesurés | direction réellement mesurée |
| Technique sans échelle | direction issue d'un label de régime | `UNKNOWN`, manque déclaré |
| Bollinger | pouvait porter une direction | `UNKNOWN`, `impact_on_direction = NONE` |
| Résumé technique | `Bollinger squeeze=False` | phrase française formée par le moteur |
| Source affichée | « Positionnement & dérivés » | Farside, Deribit, open interest multi-exchange |

## 12. Risques résiduels

**La couche reste additive.** `directional_bias` des familles, qui alimente la
décision, n'a pas été modifié. Sur ETH, la décision est calculée avec
`technical_volatility = BULLISH` alors que la couche publie `UNKNOWN`. Les deux
lectures ne se contredisent pas à l'écran — le validateur le vérifie — mais elles
ne sont pas issues du même calcul. Les aligner changerait des décisions.

**Le score mesure la cohérence interne**, pas la qualité prédictive. Un système
peut être parfaitement cohérent et se tromper.

**SOL publie 2 interprétations distinctes sur 3 horizons.** Le validateur exige
qu'elles ne soient pas toutes identiques, pas qu'elles soient toutes
différentes : deux horizons peuvent légitimement lire la même chose quand les
données sous-jacentes coïncident.

**Le scan textuel est une liste de couples interdits**, pas une compréhension du
langage. Il attrape les contradictions connues, pas toutes les contradictions
possibles.
