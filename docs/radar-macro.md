# Radar macro : 15 moteurs surveillés, 5 affichés

Les « signaux » dont il s'agit ici sont **macroéconomiques, monétaires, financiers, réglementaires et de liquidité**. Aucun indicateur technique (RSI, moyennes mobiles, MACD) n'entre dans ce moteur : l'analyse technique garde son système, et les deux ne sont jamais mélangées.

```
données officielles  →  15 moteurs  →  importance recalculée  →  TOP 5
                                    →  direction (ou inconnu)  →  page
                                    →  instantané historisé    →  cycle suivant
```

## 1. Audit : ce qui existait déjà et qui est réutilisé

La mission demandait d'auditer avant de construire. L'essentiel était là.

| Besoin | Déjà présent | Réutilisé pour |
|---|---|---|
| Attention ≠ direction, décroissance par catégorie | `engines/market_radar.py` (`AttentionLevel`, `EventDirection`, `DECAY_AFTER_RELEASE`) | les deux échelles et la décroissance du radar |
| Transmission macro → crypto (énergie, courbe, **crédit**) | `engines/macro_transmission.py` | seuils de stress du crédit, canal du pétrole |
| Cycle de vie réglementaire | `engines/regulation.py` (statuts légaux explicites) | moteur Réglementation |
| Géopolitique par canaux mesurables | `engines/geopolitics.py` | moteur Risque géopolitique |
| Composants macro avec signal et poids | `engines/decision_families.py` | cohérence des lectures taux / dollar / actions |
| Événements datés, importance, consensus | table `future_events`, `engines/event_surprise.py` | « prochaine publication » |
| Instantanés historisés | `history/snapshots.py` | historisation des cycles |

**Créé** : `engines/macro_drivers.py` (les 15 moteurs et le classement), `history/macro_cycles.py` (un instantané par cycle), `api/routes_macro.py`, `providers/macro/fred_public.py`. Rien d'autre côté moteur.

## 2. Les 15 moteurs et leurs sources

| # | Moteur | Source | État des données |
|---|---|---|---|
| 1 | 🏛️ Fed / taux américains | Fed de New York (EFFR, fourchette cible) | ✅ |
| 2 | 🇺🇸 Inflation US | BLS (CPI), BEA via FRED (PCE) | ✅ |
| 3 | 👷 Emploi US | BLS (chômage, emplois), FRED (inscriptions) | ✅ |
| 4 | 📈 Rendements US | U.S. Treasury (2 / 10 / 30 ans, taux réel) | ✅ |
| 5 | 💵 Dollar | Yahoo Finance (DXY) | ✅ |
| 6 | 💧 Liquidité banque centrale | Fed H.4.1, Treasury (TGA), Fed de NY (RRP) | ✅ |
| 7 | 🏦 Conditions de crédit | ICE BofA via FRED (primes haut rendement et qualité) | ✅ **nouveau** |
| 8 | 🇪🇺 BCE / Europe | Banque centrale européenne | ✅ |
| 9 | 🇯🇵 BoJ / Japon | Banque du Japon | ✅ |
| 10 | 🛢️ Pétrole / énergie | Yahoo Finance (WTI) | ✅ |
| 11 | 🪙 Flux ETF crypto | Farside Investors | ✅ |
| 12 | 💰 Stablecoins | DefiLlama | ✅ |
| 13 | ⚖️ Réglementation | SEC EDGAR, calendriers officiels | ✅ |
| 14 | 🌍 Risque géopolitique | mesuré par ses canaux (pétrole, VIX) | ✅ |
| 15 | 📊 Marchés risqués | Yahoo Finance (Nasdaq, S&P 500, VIX) | ✅ |

**15 est une cible UX, pas une contrainte** : aucun moteur n'a été dédoublé pour atteindre le chiffre, et un moteur sans source s'affiche « Source non branchée » plutôt que d'être masqué ou montré comme neutre.

### Données ajoutées pour cette mission

Les primes de risque du crédit manquaient — c'est pourtant ce qui sépare une correction d'un stress réel. Elles viennent désormais de l'export CSV public de la Fed de Saint-Louis (`fred.stlouisfed.org/graph/fredgraph.csv`) : **aucune clé, aucune authentification, et le robots.txt l'autorise explicitement** (seuls l'image du graphique, la page d'accueil du graphe et la recherche sont interdits ; le délai d'un seconde demandé est respecté). Le même provider apporte le PCE, les inscriptions hebdomadaires au chômage, et l'historique du bilan de la Fed — qui ne comptait que 3 points.

## 3. Importance ≠ direction

Deux échelles, deux vocabulaires, jamais fusionnées.

| Attention | Direction |
|---|---|
| NONE · LOW · MODERATE · HIGH · CRITICAL | FAVORABLE · UNFAVORABLE · NEUTRAL · MIXED · UNKNOWN |

**CRITICAL + UNKNOWN est une lecture valide et fréquente** : une décision de banque centrale dans 20 h mérite toute l'attention et ne pointe nulle part tant que le résultat n'est pas publié. Le moteur dit « le sens dépendra de l'écart avec ce qui était attendu », il n'invente pas une direction parce que l'événement est important.

L'importance est **additive et explicable**, pour que la page puisse justifier un 94/100 au lieu de l'asséner :

```
poids de la famille (+55 pour une banque centrale)
+ proximité d'une échéance (+40 à moins de 6 h, +30 à moins de 24 h…)
+ publication récente (+12)        − donnée ancienne (−10)
+ mouvement inhabituel (+25 au-delà du 95ᵉ centile de son propre historique)
+ signaux contradictoires à trancher (+5)
```

Chaque ligne est conservée et affichée sous « POURQUOI CE POIDS ».

## 4. Aucun raccourci macro

Les règles interdites par la mission sont testées comme telles :

- **« baisse des taux = crypto monte » est refusé.** Une Fed qui assouplit est lue FAVORABLE *si le crédit est calme*, et **MIXED si les primes de risque sont tendues au même moment** : une baisse provoquée par une dégradation économique n'a pas la portée d'une baisse préventive. Le test `test_an_easing_fed_inside_credit_stress_is_not_read_as_positive` fige les deux cas.
- **Le pétrole n'agit jamais directement.** En dessous de 12 % sur un mois il est NEUTRAL (« mouvement trop limité pour peser sur les anticipations d'inflation ») ; au-delà, il passe par le canal inflation → taux, jamais « pétrole baisse = crypto monte ».
- **L'emploi est MIXED quand il se détend** : des baisses de taux plus proches *et* une économie qui ralentit, les deux effets jouant en sens contraire.
- **La géopolitique ne compte que par ses canaux mesurés** (pétrole, volatilité des actions). Une actualité sans effet mesurable n'est pas un signal.

## 5. Un cycle toutes les 3 heures, sans republier les valeurs

Le cycle tourne à **00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC** (`CronTrigger`, fuseau explicite). À chaque cycle : lecture des 15 moteurs, importance recalculée, TOP 5 resélectionné, synthèse refaite, instantané enregistré.

**Ce qui n'est jamais fait** : présenter une donnée mensuelle comme nouvelle. Un CPI d'août garde sa date de publication ; la page affiche la date de la dernière publication et celle de la prochaine. Seule l'importance est recalculée toutes les trois heures. Le test `test_a_monthly_figure_keeps_its_date_and_names_the_next_one` le vérifie.

**Entre deux cycles** : `job_macro_watch` tourne toutes les 15 minutes et ne déclenche une réévaluation que si une publication majeure vient de tomber (FOMC, CPI, PCE, emploi, BCE, BoJ). Il n'attend pas trois heures.

## 6. Historisation et comparaison

Un instantané par cycle dans `history/macro_cycles.py`, jamais réécrit. Deux cycles dans la même tranche de trois heures rafraîchissent la même ligne — ce qui rend le planificateur sûr au redémarrage ; deux cycles différents sont deux lignes.

« Il y a 3 h, la Fed était NEUTRAL, elle est maintenant NEGATIVE » n'est affiché que si **la lecture précédente a été enregistrée quand elle était d'actualité**. Après une longue coupure, aucune comparaison n'est proposée plutôt qu'une comparaison fausse (fenêtre de 9 h maximum).

## 7. Ce que la page montre

**Home** (décision validée avec l'utilisateur) : le bloc « 🌍 Pourquoi le marché bouge ? » affiche les 5 moteurs du moment, chacun avec sa direction, son état et son poids, puis « Actualisé à 18:00 · prochaine vérification 21:00 » et « Voir les 15 moteurs › ».

La ligne « Macro » disparaît du bloc « 🧩 Lecture du marché » quand le radar est présent : la même famille ne doit pas être lue deux fois, une fois en ligne et une fois en bloc.

**Page des 15** : la synthèse, ce qui a changé depuis la vérification précédente, les moteurs mesurés classés par importance, puis ceux sans source, déclarés.

**Un moteur au clic** : direction et attention côte à côte, résumé, valeurs clés avec leur période et leur source, « pourquoi cela compte », « ce que nous surveillons », la prochaine publication, et le détail du score.

## 8. Ce qui n'est pas fait, et pourquoi

- **Consensus et surprise.** La mission demande précédent / consensus / réel / surprise. La table `macro_releases` existe et `event_surprise.py` sait les exploiter, mais **aucune source de consensus n'est branchée** : la lecture d'inflation le dit explicitement (« la surprise par rapport au consensus ne peut pas être calculée ici ») plutôt que d'inventer une attente.
- **Calendrier du BLS inaccessible.** `bls.gov` répond **403 à ce serveur**, y compris sur `robots.txt` : les dates du prochain CPI et du prochain rapport sur l'emploi ne sont pas affichées. Conformément à la consigne, aucune tentative de contournement n'a été faite ; le manque est déclaré dans la lecture du moteur Emploi. Les données elles-mêmes (collectées plus tôt) restent utilisées avec leur date. Le calendrier de la BEA, lui, fonctionne : la prochaine publication PCE est affichée.
- **Probabilités implicites de la Fed.** Aucune source de pricing (futures, OIS) n'est connectée, et `central_bank_rates.py` le documentait déjà : « anticipation indisponible » plutôt qu'une estimation.
- **Réaction post-publication.** Le relevé automatique de la réaction de BTC, du Nasdaq, du dollar et des taux après un événement (`engines/catalyst_reaction.py` existe) n'est pas encore branché sur le radar.

## 9. Le radar explique, il ne décide pas

Le radar macro est une **couche de lecture**. Il ne modifie ni la décision ACHETER / ATTENDRE / VENDRE, ni les scores internes, ni les moteurs : la macro entre dans la décision par la famille macro du moteur de décision, comme avant. Croiser les trois couches (macro, Lexa, technique) reste du ressort du moteur de décision, qui garde ses propres conditions.

## 10. Tests

`tests/unit/test_macro_drivers.py` (13 tests) fige : les deux échelles séparées, CRITICAL + UNKNOWN, le refus du raccourci de la Fed, le seuil macro du pétrole, un moteur sans source déclaré, le TOP 5 recalculé (la BoJ passe première à quatre heures de sa décision), les heures du cycle, et le fait qu'un changement vient d'un instantané enregistré.

`app/test/macro_drivers_test.dart` (8 tests) fige : 15 surveillés et 5 affichés, le classement, les deux échelles à l'écran, l'absence de probabilité, « Macro » non répété sur la Home, et le détail d'un moteur avec ses chiffres, ses sources et sa prochaine échéance.
