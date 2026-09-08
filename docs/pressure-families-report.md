# Les cinq familles : d'une carte morte à des mesures réelles

## 1. Le problème

La carte affichait « ACHAT DOMINANT +61/100 » sur **une famille disponible sur
cinq**. Deux défauts distincts, corrigés séparément.

**A — les données manquaient.** Non pas parce que les sources n'existent pas,
mais parce que rien ne faisait tourner le planificateur et que deux familles
n'avaient jamais été câblées.

**B — le vocabulaire était trop affirmatif.** Un score calculé sur presque rien
se présentait comme une conclusion.

## 2. Audit avant modification

Les cinq familles trouvées dans `engines/market_pressure.py`, et leur état réel
au 8 septembre 2026 à 10 h 43 UTC :

| Famille | Source | BTC | ETH | SOL | Problème |
| --- | --- | --- | --- | --- | --- |
| `institutions` | Farside, flux ETF spot | 3 105 lignes, 5 j | 2 574 lignes, 5 j | — | pas d'ETF SOL |
| `levier` (funding) | `funding.rate` Binance | 7 009 lignes, **18,7 h** | idem | 6 631, 18,7 h | non rafraîchi |
| `positionnement` | `oi.contracts_bybit` | 2 225 lignes, **34,7 h** | 2 147, 34,7 h | 1 896, 34,7 h | non rafraîchi |
| `baleines` | observations `whale.` | **0** | **0** | **0** | aucun fournisseur |
| `flux_spot` | — | **aucune source** | — | — | jamais câblée |

Résultat : BTC = 1/5.

Décisions : REUSE pour `institutions` et `levier` ; EXTEND pour
`positionnement` ; REPLACE pour `flux_spot` ; DEPRECATE d'aucune.

## 3. Ce qui bloquait réellement

**Le planificateur ne tournait pas.** APScheduler ne vit que dans le processus
API, et rien ne l'exécutait. Un `job_derivatives_sync` lancé à la main a suffi :
funding est passé de 18,7 h à 2,7 h, l'open interest de 34,7 h à 10,7 h. La
profondeur des séries — sept mille points de funding — masquait complètement
leur immobilité.

**Les bougies 4 H et 1 H avaient 19 heures.** C'est sur elles que la structure,
la position dans le range et le timing sont calculés.

**Le seuil de fraîcheur du funding était plus court que sa cadence de
publication.** Le funding se règle toutes les huit heures ; la fenêtre
« récent » était de neuf heures. La famille devenait donc inutilisable pendant
une grande partie de chaque cycle alors qu'elle était parfaitement à jour.
Chaque famille est maintenant jugée contre la cadence de sa propre source.

## 4. Les deux familles remises en service

### Spot — agressivité des acheteurs

Une bougie Binance transporte le *taker buy base volume* à côté du volume
total : la part du volume où l'acheteur a traversé le spread. Toute transaction
a un acheteur et un vendeur, donc le volume seul ne dit rien — mais **quel côté
était l'agresseur, si.**

Le projet appelait déjà cet endpoint et jetait les champs 9 et 10. C'est pour
cela que « flux spot » n'avait pas de source.

- Série : `spot.taker_buy_ratio`, `spot.net_taker_volume`
- Profondeur : BTC/ETH 3 310 jours (depuis 2017), SOL 2 220 jours (depuis 2020)
- Ce n'est pas un proxy : c'est la comptabilité de l'exchange.

### Dérivés — positionnement des comptes

Une hausse d'open interest **n'est pas un achat** : il y a un short en face de
chaque long. La répartition long/short des comptes Binance
(`derivatives.long_account_share`, ~31 jours, la limite de la source) se lit
maintenant à côté du couple prix/OI, si bien que « OI en hausse » se résout en
nouveaux longs ou nouveaux shorts au lieu d'être converti mécaniquement en
achat.

## 5. Baleines : réellement indisponible

L'attribution d'adresses aux exchanges est exactement ce que facturent
Glassnode, CryptoQuant et Nansen. Aucune source gratuite ne la fournit.

Ce qui a été cherché et écarté :

- dériver un signal des observations `onchain.` existantes — le nombre de
  transactions et les frais mesurent l'activité, **pas une direction** ;
  l'appeler « baleines » serait un proxy renommé ;
- Blockchair et blockchain.info donnent de grosses transactions sans
  attribution d'exchange, ce qui ne répond pas à la question.

La famille reste absente, porte sa raison, et ne contient aucun chiffre. Un
signal baleine fabriqué est l'une des sorties les plus dangereuses que cet
outil puisse produire. Solution future : renseigner une clé Glassnode active la
famille sans autre changement.

## 6. Disponibilité, avant et après

| Actif | Avant | Après | Non applicable |
| --- | --- | --- | --- |
| BTC | 1/5 | **4/5** (90 %) | — |
| ETH | 1/5 | **3/5** (60 %) | — |
| SOL | 1/5 | **3/4** (86 %) | ETF |

ETH est à 3/5 parce que Farside publie son tableau ETH avec un jour de retard
sur celui de BTC ; la famille reviendra seule. SOL n'est pas pénalisé pour un
ETF spot qui n'existe pas : cette famille est **non applicable**, et compter une
absence structurelle comme un trou signalerait un défaut de données là où il y a
un fait de marché.

## 7. Les cinq valeurs réelles

Relevé du 8 septembre 2026, 11 h 05 UTC.

**BTC — PRESSION ACHETEUSE +29,9/100 — 4/5 (90 %, forte)**

| Famille | État | Score | Poids | Apport | Fraîcheur | Observation |
| --- | --- | --- | --- | --- | --- | --- |
| ETF / Institutions | Acheteur marqué | +98,7 | 0,30 | **+32,89** | RECENT | 2026-09-04 00:00 |
| Spot / agressivité | Vendeur marqué | −60,0 | 0,25 | **−16,68** | LIVE | 2026-09-08 00:00 |
| Dérivés / positionnement | Acheteur marqué | +66,7 | 0,20 | **+14,82** | LIVE | 2026-09-08 08:00 |
| Funding / levier | Neutre | −6,7 | 0,15 | **−1,12** | LIVE | 2026-09-08 08:00 |
| Baleines | indisponible | — | 0,10 | — | — | — |

Somme des apports : 32,89 − 16,68 + 14,82 − 1,12 = **+29,91**. Dénominateur
0,90. Le total se refait à la main.

**ETH — ÉQUILIBRÉE −3,3/100 — 3/5 (60 %, partielle)** : spot −31,6 (−13,16),
dérivés +61,7 (+20,57), funding −42,7 (−10,67).

**SOL — ÉQUILIBRÉE −1,5/100 — 3/4 (86 %, forte)** : spot −8,9 (−3,71),
dérivés +25,6 (+8,53), funding −25,2 (−6,30).

## 8. Formule et poids

```
score = Σ(score_normalisé × poids) / Σ(poids des familles disponibles)
```

| Famille | Poids | Pourquoi |
| --- | --- | --- |
| institutions | 0,30 | de l'argent réel, mais publié une fois par séance |
| spot | 0,25 | le côté agresseur de transactions réellement passées |
| derivatives | 0,20 | positionnement, ambigu pris isolément |
| funding | 0,15 | coût de portage ; un extrême dit l'encombrement plus que le sens |
| whales | 0,10 | quand une source vérifiée existe |

Bornes −100/+100. Une famille absente **sort du dénominateur**, elle ne devient
jamais un zéro : « pas de donnée » et « pas de pression » sont deux
affirmations différentes, et confondre la première avec la seconde tire
silencieusement chaque score vers le neutre. Une famille non applicable sort du
dénominateur **et** du décompte de couverture.

## 9. Vocabulaire sous contrainte de couverture

| Couverture | Titre |
| --- | --- |
| < 40 % | PRESSION ACHETEUSE **INDICATIVE** |
| 40–70 % | PRESSION ACHETEUSE **PARTIELLE** |
| 70–75 % | PRESSION ACHETEUSE |
| ≥ 75 % et \|score\| ≥ 45 | **ACHETEURS DOMINANTS** |

Le même +61 sur une famille se lit désormais « PRESSION ACHETEUSE INDICATIVE ».
Un déséquilibre faible sur une couverture forte reste « LÉGÈRE ».

## 10. `crypto-intel data-health`

Chaque source, actif par actif, jugée contre sa propre cadence : `OK`, `STALE`,
`UNAVAILABLE`, `NOT_APPLICABLE`, `ERROR`. Sortie non nulle quand quelque chose
est réellement à corriger, pour servir de garde en cron ou en CI.
`NOT_APPLICABLE` n'y compte jamais comme un manque.

État après remise à niveau : **29 à jour, 2 en retard, 3 indisponibles, 2 sans
objet, 0 en erreur**. Les deux retards sont les ETF (Farside n'a pas publié
depuis le 4 septembre) ; les trois indisponibles sont les baleines.

## 11. Planificateur

`job_derivatives_sync` rafraîchit désormais funding, open interest Binance et
Bybit, DVOL, **agressivité spot** et **répartition des comptes**. Un test
d'anti-régression vérifie que chaque série lue par une famille a un travail qui
l'actualise : une famille câblée sans travail planifié se périme en silence.

Une panne de fournisseur laisse la famille absente ; elle ne rejoue jamais la
dernière valeur comme si elle était courante.

## 12. Tests

- `test_market_pressure.py` (23) — reproductibilité du score, dénominateur,
  et les six cas de vocabulaire du cahier des charges, dont « 1 forte hausse +
  4 absentes ne peut jamais être dominant ».
- `test_pressure_families.py` (25) — câblage bout en bout par actif, aucune
  fabrication, `NOT_APPLICABLE` hors dénominateur, la pression n'écrase pas le
  timing, `data-health`, et le planificateur couvre chaque série.
- `test_today_page.py`, `test_analysis_identity.py` — cohérence page et
  identité d'analyse.

940 tests backend, 133 Flutter, ruff et analyze propres, build web OK.

## 13. Limites honnêtes

- **Les baleines restent absentes** et le resteront sans abonnement payant.
  4/5 est le maximum réel aujourd'hui pour BTC.
- **Rien ne fait tourner le planificateur en continu.** Les données ont été
  remises à niveau à la main pendant ce travail ; sans processus qui vit, elles
  se périmeront de nouveau. C'est le même blocage de déploiement que
  précédemment, et il demande une décision d'hébergement.
- **La répartition des comptes n'a que 31 jours** de profondeur — limite de
  Binance, enregistrée pour qu'aucune étude ne suppose des années.
- **L'agressivité spot est journalière** : elle décrit la séance, pas la
  minute.
- Le poids de chaque famille est un choix documenté, pas un résultat mesuré.
  Aucune étude n'a établi que ces poids prédisent quoi que ce soit — la carte
  décrit une pression, elle ne prétend pas à un avantage.
