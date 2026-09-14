# Couche d'analyse et de synthèse — audit et premiers lots

**Date** : 14/09/2026
**Suites exécutées** : `pytest tests/` → **1594 passés, 15 ignorés** ·
`ruff check backend/ tests/` → clean. **+48 tests** dans ce lot.

---

## 1. Audit initial : ce qui existait déjà

La consigne demandait de ne pas refaire ce qui fonctionne. L'audit montre que
c'est la majorité du périmètre.

| demandé | état trouvé |
|---|---|
| ChiefMarketAnalyst | **existe** — `analysts/chief.py`, 406 l., avec scénarios, contradictions, `what_would_change_my_mind`, repli déterministe sans LLM |
| Analystes spécialisés | **existe** — `analysts/specialists.py`, `evidence_confrontation.py` |
| Opportunity / BuyOpportunity | **existe** — `buy_opportunity.py` 851 l., `entry_timing.py` 516 l. |
| 5 familles | **existe** — macro, catalyseurs, flux, positionnement, technique |
| Macro | **existe** — `macro.py`, provider FRED/Yahoo/Stooq/ALFRED |
| Technique, structure, patterns | **existe** — `multi_timeframe.py`, `structure/`, patterns en DESCRIPTIVE_ONLY |
| Funding, open interest, crowding | **existe** — `derivatives.py`, `leverage.py`, `market_pressure.py` |
| ETF | **existe** — `etf_flows.py`, `etf_split.py`, `institutional_flow.py` |
| On-chain, baleines | **existe** — `onchain.py`, `whales.py` |
| Événements | **existe** — `future_events/` : 8 états de cycle de vie, 11 catégories, tiers A→E |
| Provenance, fraîcheur | **existe** — sur chaque observation |
| **Étapes législatives (§50)** | **existe et correct** — `RegulatoryStage` : 13 étapes, de DISCUSSION à SIGNED_INTO_LAW, avec le test `test_clarity_markup_is_not_reported_as_adopted` |

**Conclusion de l'audit** : le §50 était déjà satisfait, je n'y ai pas touché.
Le travail utile portait ailleurs.

## 2. Problèmes identifiés

**Le tier social était étiqueté mais jamais bloqué.** `geopolitical_news.py`
assignait `FutureEventSourceTier.E` avec une confiance de 0,2, puis l'événement
poursuivait son chemin comme les autres. Rien n'empêchait un élément d'origine
sociale d'atteindre la décision — ce que les §11 et §49 interdisent
explicitement.

**Le crédit n'existait nulle part.** Aucune série de spreads, aucun moteur.
C'est précisément la variable qui sépare une correction d'un stress systémique
(§9, §52) : sans elle, la distinction ne peut pas être mesurée.

**Le pétrole était collecté mais pas interprété.** `macro.oil_wti` compte 96
observations, mais rien ne distinguait « pétrole élevé et stable » de « pétrole
+20 % en deux semaines ». Ce sont deux signaux différents (§6).

**La courbe s'arrêtait au 10 ans.** Pas de 30 ans, donc aucune lecture de
l'inflation longue ni du risque budgétaire (§8).

**Aucune séparation risque / déclencheur / confirmation.** Le §22 la rend
obligatoire, et son absence est ce qui fait qu'un système annonce une
correction dès que le risque monte.

## 3. Ce qui a été livré

### Sources macro (§6, §8, §9, §58)

Six séries ajoutées au provider FRED déjà branché, toutes gratuites :
`DGS30`, `DCOILBRENTEU`, `DCOILWTICO`, `BAMLH0A0HYM2`, `BAMLC0A0CM`, `PPIACO`.
12 → 18 séries.

### `macro_transmission.py` — la chaîne économique (§7, §9, §51, §52)

Le pétrole n'y devient jamais un signal crypto. La chaîne est explicite :
énergie → inflation anticipée → politique monétaire → rendements → conditions
financières, et le dernier maillon dit qu'elle **n'est pas automatique**.

`confront()` compare les maillons au lieu de les moyenner. Le cas du §51-C —
pétrole qui monte pendant que les taux baissent — produit `CONFLICTING` et non
une lecture tiède : la chaîne ne fonctionne pas, et c'est l'information la plus
utile disponible.

Le crédit est traité comme une **étape de confirmation**, pas comme un signal
avancé : spreads calmes ⇒ la baisse reste une correction ; spreads qui
s'écartent ⇒ autre chose.

### `source_hierarchy.py` — qui décide, qui suggère (§11-14, §49)

Quatre tiers ordonnés, `PRESS` comme plafond de production. Le filtre est posé
dans `usable_events_for_horizon`, le point de passage unique de tous les
horizons : un élément social ne peut plus atteindre une décision.

`SocialDiscoveryLayer` est `DISCOVERY_ONLY` **par construction** : `DiscoveredTopic`
ne possède aucun champ numérique, donc un chiffre lu dans un message ne peut pas
être confondu avec une mesure du système. Un sujet doit être re-sourcé auprès
d'une source primaire pour devenir un événement.

Un tier inconnu est traité comme **social**, jamais comme primaire — l'inverse
inverserait la règle.

### `market_synthesis.py` — la synthèse structurée (§18-28, §43, §53-55)

Trois notions strictement séparées : **risque** (ce qui rend un mouvement
possible), **déclencheur** (l'événement), **confirmation** (la preuve qu'il a
commencé). Seules les conditions de confirmation font passer `ELEVATED_RISK` à
`CORRECTION_CONFIRMED`.

La section « pourquoi ce n'est pas encore confirmé » (§20) est construite depuis
les lectures qui contredisent l'état, et un test vérifie qu'elle n'est jamais
silencieusement vide.

Les conditions sont **pondérées** : quatre conditions mineures ne pèsent pas
autant qu'une majeure. Ce n'est pas un vote.

Aucune probabilité chiffrée : `Likelihood` publie FAIBLE / MODÉRÉ / ÉLEVÉ /
TRÈS ÉLEVÉ avec `likelihood_basis = HEURISTIC_ASSESSMENT`. Un test vérifie
qu'aucun « % » n'apparaît.

Le verdict est **entièrement déterministe** : un test lit le source du module et
échoue s'il contient la moindre référence à un modèle de langage (§47).

## 4. Tests ajoutés (48)

| fichier | tests | ce qu'ils défendent |
|---|---|---|
| `test_macro_transmission.py` | 22 | §51 cas A/B/C, §52 crédit, courbe complète, pétrole jamais signal direct |
| `test_source_hierarchy.py` | 13 | §49 le social ne décide jamais, §11-13 discovery, tier inconnu = social |
| `test_market_synthesis.py` | 13 | §53 risque ≠ correction, §54 confirmation, §55 données insuffisantes, §28 aucune probabilité inventée |

## 5. Un défaut trouvé par la mesure, pas par lecture

`confront()` écartait toute lecture dont la fraîcheur n'était pas explicitement
`AVAILABLE`. Conséquence : une variable pourtant mesurée disparaissait du calcul
et le verdict retombait sur `UNKNOWN`. Perdre une mesure en silence est pire que
de la signaler dégradée — les lectures `PARTIAL` et `STALE` sont maintenant
comptées et la mention « lecture(s) dégradée(s) » apparaît dans le motif.

De même, l'évaluateur pétrole exigeait le Brent — série FRED, donc bloquée faute
de clé — alors que le WTI arrive déjà sans clé via Yahoo et Stooq. Il accepte
maintenant l'un ou l'autre, ce qui le rend utilisable sur les données qui
existent réellement.

## 6. Limites — ce qui n'est pas fait

**`FRED_API_KEY` n'est pas configurée.** Les six séries ajoutées ne se
chargeront pas tant qu'une clé (gratuite) n'est pas renseignée. Les moteurs
sont écrits et testés ; ils attendent la donnée. Voir
[missing-market-variables-audit.md](missing-market-variables-audit.md).

**Les trois nouveaux moteurs ne sont pas branchés sur l'API ni sur l'UI.** Ils
sont calculables et testés, mais le payload et la page Flutter ne les
consomment pas encore. La nouvelle structure de page (§40) reste à faire.

**`EventCatalystEngine` n'est pas créé comme tel.** Le modèle d'événement couvre
déjà cycle de vie, catégories et tiers ; manquent l'impact **par actif** (§5) et
le `market_relevance_score` (§16).

**Pas d'exemples réels BTC/ETH/SOL** avec la nouvelle synthèse : elle n'est pas
encore alimentée par le contexte d'analyse.

Ce lot livre les fondations testées et l'audit ; l'intégration bout en bout
reste devant.
