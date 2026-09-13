# Correction UX + sémantique future-first

**Date** : 13/09/2026 · **Périmètre** : contenu affiché, design inchangé
**Tests** : backend 1378 passés / 15 ignorés (+6) · Flutter 323 passés (+3)

---

## 1. La régression que ce lot corrige est la mienne

Au lot précédent j'ai écrit, dans la construction des facteurs :

```dart
whatHappens: reason.dateTime != null
    ? '${reason.title} — ${_dateSentence(reason.dateTime)}.'
    : ...
```

Cette ligne colle une date à **n'importe quel** titre de raison. Comme les
raisons étaient des familles, elle produisait « Macro & liquidité — le 13 sept.
à 17h39 » et « Technique & volatilité — le 13 sept. à 17h39 ». La date n'était
même pas celle d'un événement : c'était l'horodatage de l'analyse.

C'est une famille transformée en faux événement. Corrigé ci-dessous par une
séparation de types, pas par un correctif de texte.

---

## 2. Les trois objets sont désormais distincts

| objet | ce que c'est | vocabulaire d'affichage |
|---|---|---|
| **FAMILY STATE** | regroupement analytique (`Macro & liquidité = NEUTRAL`) | jamais montré comme cause; réservé à l'analyse complète |
| **CURRENT SIGNAL** | mesure déjà observée | **CE QU'ON OBSERVE** · CE QUI INVALIDERAIT CE SIGNAL |
| **FUTURE CATALYST** | événement daté à venir | **CE QUI VA SE PASSER** · CE QUE LE MARCHÉ ATTEND · SI LE RÉSULTAT EST PLUS POSITIF / NÉGATIF QUE PRÉVU |

Le type est porté par `_FactorKind` et gouverne le rendu. Un catalyseur ne peut
pas afficher « ce qu'on observe », un signal ne peut pas afficher « ce que le
marché attend » : il n'y a rien à anticiper sur une mesure déjà prise.

Une famille neutre ne produit plus aucune ligne : son contenu réel, ce sont ses
événements datés, qui remontent comme catalyseurs.

---

## 3. Où les événements se perdaient (§F et §N)

Le pipeline fonctionnait jusqu'au bout. Les événements existent, sont
collectés, datés, et atteignent la sélection d'horizon :

| horizon | sélectionnés | exploitables |
|---|---|---|
| 24 h | 2 | 2 |
| 7 j | 6 | 6 |
| 30 j | 9 | **8** |

Ils se perdaient en **deux points précis**, tous deux en aval :

**1. Classement.** `future_context.py` construit `reasons=[event.title for event
in macro_events[:3]]` — les trois premiers en **ordre chronologique**. Sur 30
jours, cela remonte trois adjudications de bons du Trésor et enterre le FOMC,
seul événement CRITICAL de la fenêtre.

**2. Modèle Flutter.** Le backend envoie bien ce champ `reasons` dans le
payload, mais `FutureFamilyRead` ne le parse pas. L'UI retombait donc sur
`summary` = « 8 événement(s) macro/monétaire sourcé(s) dans la fenêtre » — un
comptage de lignes, interdit par le §M.

**Correction** : les catalyseurs ne sont plus tirés de `family.reasons` mais de
la timeline, qui porte l'importance, et sont classés importance d'abord,
proximité ensuite. La section « À surveiller » applique le même classement.

Aucune donnée fictive n'a été créée.

---

## 4. Le cas ETF (§J) : la convention de signe est correcte

Trace complète sur les données réelles (730 enregistrements Farside, BTC) :

| champ | valeur | lecture |
|---|---|---|
| `raw_value` | `IBIT 16/06 = +16,4` | positif = argent entrant |
| `regime_sessions` | 20 | fenêtre du régime |
| `regime_total_musd` | **+3 310,1** | réellement positif |
| `rolling_5_sessions_musd` | **−288,1** | réellement négatif |
| `latest_flow_musd` | −13,2 | — |
| `persistence` | OUTFLOW, **4 séances** | — |
| `flow_reversal` | **INFLOW_TO_OUTFLOW** | calculé, puis ignoré |
| `source` | Farside, `farside.co.uk/bitcoin-etf-flow-all-data/` | — |

**Aucun seuil n'a été modifié.** Les deux chiffres sont justes et le signe est
correct des deux côtés. Le défaut est que le moteur **détecte le retournement
et le jette** : `flow_reversal` et `persistence_direction` étaient calculés,
puis n'entraient dans aucune phrase. Le label positif du régime 20 séances
voyageait donc jusqu'à l'UI sans qualification.

Le résumé énonce désormais le retournement :

> avant — `Flux institutionnels inflow; cumul 5 séances -288.09999999999997 M$.`
> après — `Flux institutionnels: entrées nettes sur 20 séances (+3 310,1 M$), mais le sens s'est inversé: 4 séance(s) consécutives de sorties; 5 dernières séances −288,1 M$.`

Six tests de non-régression ([test_institutional_flow_sign.py](../tests/unit/test_institutional_flow_sign.py))
fixent la convention de signe, la distinction des deux fenêtres, et le fait
qu'un retournement ne peut plus être tu.

**Réserve à assumer** : `directional_bias` reste calculé sur le régime 20
séances et vaut donc toujours `BULLISH`. Le changer modifierait la décision, ce
que la consigne exclut de cette tâche. La divergence est énoncée, pas résolue.

---

## 5. Chaînes interdites au §M : vérifiées absentes

| chaîne | statut |
|---|---|
| « 8 événements sourcés dans la fenêtre » | supprimée de la page et de l'accroche |
| « Macro & liquidité — 13 sept. » | impossible par construction (type) |
| « structure 24h haussière sur 0 unité(s) » | traduite : « Tendance haussière sur 0 échelle(s) de temps contre 0 » |
| « catalyseur prioritaire » | supprimée |
| « ce facteur change de sens » | remplacée par une invalidation concrète par famille |

L'accroche sous la décision reprenait `decision.reasons.first.explanation`,
c'est-à-dire la phrase de comptage. Elle nomme maintenant le facteur dominant :
« Décision de la Fed sur les taux — 16 sept. · issue encore inconnue. »

Trois tests Flutter verrouillent ces absences.

---

## 6. Rapport end-to-end (§N)

Mesuré sur l'API réelle, 9 combinaisons.

| actif / horizon | décision | risque | garde-fou | catalyseurs dans la fenêtre |
|---|---|---|---|---|
| BTC 24 h | SELL | LOW | non | 2 |
| BTC 7 j | WAIT | HIGH | oui | 6 |
| BTC 30 j | WAIT | HIGH | oui | **8** |
| ETH 24 h | SELL | LOW | non | 2 |
| ETH 7 j | WAIT | HIGH | oui | 6 |
| ETH 30 j | WAIT | HIGH | oui | **8** |
| SOL 24 h | SELL | LOW | non | 2 |
| SOL 7 j | WAIT | HIGH | oui | 6 |
| SOL 30 j | WAIT | HIGH | oui | **8** |

**Vérification manuelle demandée — BTC 30 j** : les deux événements CRITICAL de
la fenêtre (FOMC du 16/09, Personal Income du 30/09) apparaissent désormais en
première et deuxième position. Avant ce lot, la page affichait trois
adjudications de bons du Trésor MEDIUM et aucun des deux.

### Détail par combinaison

#### BTC 24h — SELL

| importance | date | événement | source |
|---|---|---|---|
| MEDIUM | 2026-09-14 15:30 | 13-Week Bill Treasury auction | U.S. Treasury / TreasuryDirect |
| MEDIUM | 2026-09-14 15:30 | 26-Week Bill Treasury auction | U.S. Treasury / TreasuryDirect |

*2 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | BEARISH | NORMAL | Les vendeurs traversent le spread plus souvent que d'habitude. |
| positioning_derivatives | BEARISH | NORMAL | L'open interest recule dans la baisse : des longs sortent.; Le coût du levier reste pr |
| technical_volatility | BEARISH | NORMAL | Structure 24h: haussière sur 0 unité(s), baissière sur 1; volatilité low. Bollinger sq |

#### BTC 7d — WAIT

| importance | date | événement | source |
|---|---|---|---|
| CRITICAL | 2026-09-16 18:00 | FOMC monetary policy decision (September 2026) | Federal Reserve |
| HIGH | 2026-09-15 17:00 | 19-Year 11-Month Bond Treasury auction | U.S. Treasury / TreasuryDirect |
| HIGH | 2026-09-17 17:00 | 9-Year 10-Month Note Treasury auction | U.S. Treasury / TreasuryDirect |

*6 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | BULLISH | NORMAL | Flux institutionnels: entrées nettes sur 20 séances (+3 310,1 M$), mais le sens s'est  |
| positioning_derivatives | BEARISH | NORMAL | L'open interest recule dans la baisse : des longs sortent.; Le coût du levier reste pr |
| technical_volatility | BULLISH | HIGH | Structure 7d: haussière sur 1 unité(s), baissière sur 0; volatilité low. Bollinger squ |

#### BTC 30d — WAIT

| importance | date | événement | source |
|---|---|---|---|
| CRITICAL | 2026-09-16 18:00 | FOMC monetary policy decision (September 2026) | Federal Reserve |
| CRITICAL | 2026-09-30 12:30 | Personal Income and Outlays, August 2026 | U.S. Bureau of Economic Analysis |
| HIGH | 2026-09-15 17:00 | 19-Year 11-Month Bond Treasury auction | U.S. Treasury / TreasuryDirect |

*8 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | BULLISH | NORMAL | Flux institutionnels: entrées nettes sur 20 séances (+3 310,1 M$), mais le sens s'est  |
| positioning_derivatives | BEARISH | NORMAL | L'open interest recule dans la baisse : des longs sortent.; Le coût du levier reste pr |
| technical_volatility | NEUTRAL | HIGH | Structure 30d: haussière sur 1 unité(s), baissière sur 1; volatilité low. Bollinger sq |

#### ETH 24h — SELL

| importance | date | événement | source |
|---|---|---|---|
| MEDIUM | 2026-09-14 15:30 | 13-Week Bill Treasury auction | U.S. Treasury / TreasuryDirect |
| MEDIUM | 2026-09-14 15:30 | 26-Week Bill Treasury auction | U.S. Treasury / TreasuryDirect |

*2 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | BEARISH | NORMAL | Les vendeurs traversent le spread plus souvent que d'habitude. |
| positioning_derivatives | BEARISH | NORMAL | Les shorts paient nettement pour rester en position.; Aucun changement de positionneme |
| technical_volatility | BULLISH | NORMAL | Structure 24h: haussière sur 0 unité(s), baissière sur 0; volatilité low. Bollinger sq |

#### ETH 7d — WAIT

| importance | date | événement | source |
|---|---|---|---|
| CRITICAL | 2026-09-16 18:00 | FOMC monetary policy decision (September 2026) | Federal Reserve |
| HIGH | 2026-09-15 17:00 | 19-Year 11-Month Bond Treasury auction | U.S. Treasury / TreasuryDirect |
| HIGH | 2026-09-17 17:00 | 9-Year 10-Month Note Treasury auction | U.S. Treasury / TreasuryDirect |

*6 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | STRONGLY_BULLISH | NORMAL | Flux institutionnels: fortes entrées nettes sur 20 séances (+1 920,5 M$); 5 dernières  |
| positioning_derivatives | BEARISH | NORMAL | Les shorts paient nettement pour rester en position.; Aucun changement de positionneme |
| technical_volatility | BULLISH | NORMAL | Structure 7d: haussière sur 0 unité(s), baissière sur 0; volatilité low. Bollinger squ |

#### ETH 30d — WAIT

| importance | date | événement | source |
|---|---|---|---|
| CRITICAL | 2026-09-16 18:00 | FOMC monetary policy decision (September 2026) | Federal Reserve |
| CRITICAL | 2026-09-30 12:30 | Personal Income and Outlays, August 2026 | U.S. Bureau of Economic Analysis |
| HIGH | 2026-09-15 17:00 | 19-Year 11-Month Bond Treasury auction | U.S. Treasury / TreasuryDirect |

*8 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | STRONGLY_BULLISH | NORMAL | Flux institutionnels: fortes entrées nettes sur 20 séances (+1 920,5 M$); 5 dernières  |
| positioning_derivatives | BEARISH | NORMAL | Les shorts paient nettement pour rester en position.; Aucun changement de positionneme |
| technical_volatility | BULLISH | HIGH | Structure 30d: haussière sur 0 unité(s), baissière sur 0; volatilité low. Bollinger sq |

#### SOL 24h — SELL

| importance | date | événement | source |
|---|---|---|---|
| MEDIUM | 2026-09-14 15:30 | 13-Week Bill Treasury auction | U.S. Treasury / TreasuryDirect |
| MEDIUM | 2026-09-14 15:30 | 26-Week Bill Treasury auction | U.S. Treasury / TreasuryDirect |

*2 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | BEARISH | NORMAL | Les vendeurs traversent le spread plus souvent que d'habitude. |
| positioning_derivatives | BEARISH | NORMAL | Le prix baisse avec l'open interest : de nouveaux shorts entrent.; Le coût du levier r |
| technical_volatility | BEARISH | NORMAL | Structure 24h: haussière sur 0 unité(s), baissière sur 1; volatilité very_low. Bolling |

#### SOL 7d — WAIT

| importance | date | événement | source |
|---|---|---|---|
| CRITICAL | 2026-09-16 18:00 | FOMC monetary policy decision (September 2026) | Federal Reserve |
| HIGH | 2026-09-15 17:00 | 19-Year 11-Month Bond Treasury auction | U.S. Treasury / TreasuryDirect |
| HIGH | 2026-09-17 17:00 | 9-Year 10-Month Note Treasury auction | U.S. Treasury / TreasuryDirect |

*6 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | BEARISH | NORMAL | Les vendeurs traversent le spread plus souvent que d'habitude. |
| positioning_derivatives | BEARISH | NORMAL | Le prix baisse avec l'open interest : de nouveaux shorts entrent.; Le coût du levier r |
| technical_volatility | BULLISH | HIGH | Structure 7d: haussière sur 0 unité(s), baissière sur 0; volatilité very_low. Bollinge |

#### SOL 30d — WAIT

| importance | date | événement | source |
|---|---|---|---|
| CRITICAL | 2026-09-16 18:00 | FOMC monetary policy decision (September 2026) | Federal Reserve |
| CRITICAL | 2026-09-30 12:30 | Personal Income and Outlays, August 2026 | U.S. Bureau of Economic Analysis |
| HIGH | 2026-09-15 17:00 | 19-Year 11-Month Bond Treasury auction | U.S. Treasury / TreasuryDirect |

*8 catalyseur(s) dans la fenêtre; les 3 plus importants sont affichés.*

| famille (signal) | direction | ampleur | observation |
|---|---|---|---|
| flows_whales | BEARISH | NORMAL | Les vendeurs traversent le spread plus souvent que d'habitude. |
| positioning_derivatives | BEARISH | NORMAL | Le prix baisse avec l'open interest : de nouveaux shorts entrent.; Le coût du levier r |
| technical_volatility | BULLISH | HIGH | Structure 30d: haussière sur 0 unité(s), baissière sur 0; volatilité very_low. Bolling |
---

## 7. Limite connue

Les catalyseurs s'affichent avec `DIRECTION INCONNUE`. Ce n'est pas un défaut
d'affichage : aucun `market_expectation` n'est disponible (licence CME), donc
le système ne sait pas ce qui est déjà valorisé. Sans cela, attribuer un sens à
un FOMC reviendrait à coder « hausse = baissier », ce que la consigne interdit.
`INCERTAIN` est la réponse honnête tant que la source n'est pas branchée.

## 8. STOP

Correction, tests et rapport livrés. Le moteur de décision n'a pas été modifié :
aucun seuil, aucune règle de direction, aucun `directional_bias`.
