# Signaux et sources : participation, institutions, catalyseurs

Date : 20/09/2026. Aucun moteur existant n'a été remplacé ; tout ce qui suit se branche sur l'architecture en place (événements, déduplication, hiérarchie des sources, fraîcheur, familles de décision).

## 1. Audit avant modification

| Élément | État trouvé | Décision |
|---|---|---|
| Breadth | `engines/cross_asset.py::CryptoBreadthEngine` + `/market/breadth` — mais sur **nos 3 actifs seulement**, le module le dit lui-même | Conservé ; un moteur de participation **du marché** ajouté à côté |
| Altcoin Season Index | absent | Indice **recalculé** à partir des prix (méthode publique), jamais l'indice sous licence |
| Flux ETF | `engines/institutional_flow.py` (Farside, quotidien) | Conservé ; fusionné avec CoinShares dans un nouvel état |
| CoinShares | absent | Ajouté (flux de recherche officiel de l'émetteur) |
| SIMD / EIP | absents ; `official_protocols.py` ne lisait que blogs et incidents | Ajoutés, lus dans les dépôts officiels |
| SEC / EDGAR | absent ; seuls les flux RSS SEC existaient | Ajouté (recherche plein texte EDGAR) |
| Étapes réglementaires | `engines/regulatory_catalyst.py` (législatif) | Conservé ; échelle propre aux produits financiers ajoutée |
| Déduplication | `future_events/deduplication.py` (signature, `canonical_event_id`, `source_references`) | **Réutilisée** telle quelle |
| Hiérarchie des sources | `engines/source_hierarchy.py` (tiers A→E, découverte sociale) | **Étendue** : règle média → source primaire |
| Schéma catalyseur | `FutureEvent` couvrait déjà presque tous les champs demandés | **Réutilisé**, aucun schéma parallèle |
| Fraîcheur | `core/freshness.py` + politiques par source | **Étendue** : 4 politiques ajoutées |
| Clés API | aucune configurée | EDGAR débloqué avec un contact déclaré (ta décision) ; Alchemy/Helius/CME restent absents |

## 2. Sources réellement opérationnelles

| Source | Accès | Ce qu'elle donne |
|---|---|---|
| CoinGecko (API publique) | sans clé | Top 150, variations 24 h / 7 j / 30 j, capitalisations → participation, TOTAL2, TOTAL3 |
| CoinShares Research (flux officiel de l'émetteur) | sans clé | Flux hebdomadaires monde, par actif, encours |
| GitHub `solana-foundation/solana-improvement-documents` | sans clé | SIMD, statut lu dans l'en-tête du document |
| GitHub `ethereum/EIPs` | sans clé | EIP, statut lu dans l'en-tête |
| SEC EDGAR (recherche plein texte) | contact déclaré requis | Dépôts 19b-4, S-1, S-1/A, 424B, 8-A12B |
| Farside (déjà en place) | sans clé | Flux quotidiens des ETF au comptant |

**Non ajouté volontairement** : l'Altcoin Season Index de CoinMarketCap (API sous licence — l'indice est recalculé à partir des prix, et la fenêtre de 90 jours n'est **pas** reproduite car l'API gratuite n'expose que 24 h / 7 j / 30 j) ; Hyperliquid (hors périmètre BTC/ETH/SOL, conformément au §10) ; les flux baleines directionnels (Alchemy/Helius : clé requise).

## 3. Moteurs ajoutés, et ce qui les consomme

| Moteur | Fichier | Consommé par |
|---|---|---|
| Participation du marché | `engines/market_breadth.py` | page Marché, explication, Chief |
| Demande institutionnelle fusionnée | `engines/institutional_demand.py` | page Institutions, explication, économie du protocole |
| Catalyseurs par actif | `engines/asset_catalysts.py` | page Catalyseurs, explication |
| Réaction du marché au catalyseur | `engines/catalyst_reaction.py` | chaque catalyseur affiché |
| Économie du protocole | `engines/protocol_economics.py` | page Catalyseurs |
| Explication du mouvement | `engines/market_explanation.py` | carte d'accueil « Pourquoi le marché bouge ? » |
| Règle média → primaire | ajout dans `engines/source_hierarchy.py` | catalyseurs, déduplication |

## 4. Garde-fous

- **Une hausse n'est jamais une confirmation.** L'explication distingue ce qui soutient le mouvement, ce qui s'y oppose et ce qui reste ambigu ; sa conclusion ne dit jamais « acheter ».
- **Une rotation altcoins exige quatre conditions indépendantes** plus une dominance qui recule réellement. Deux sur quatre aujourd'hui → « début de rotation », pas « altseason ».
- **Une proposition n'est pas un vote, un vote n'est pas une activation.** Chaque SIMD/EIP porte son étape et la phrase qui l'empêche d'être surinterprétée.
- **Un dépôt n'est pas un ETF approuvé.** Même échelle pour EDGAR, du dépôt à la négociation.
- **Un article et le document officiel sont un seul événement** : l'article devient une référence de plus, jamais une seconde confirmation.
- **Aucune probabilité inventée** : la confiance est LOW / MODERATE / HIGH, jamais un pourcentage de hausse.
- **Attention ≠ direction** : tous les catalyseurs ajoutés sortent en `NEUTRAL`.
- **Une donnée périmée n'est pas une donnée actuelle** : le rapport CoinShares de juin est affiché, daté, et ne pilote pas l'état.

## 5. Exemples réels (20/09/2026)

**BTC** — Marché : 🔵 début de rotation (2 conditions sur 4). Institutions : 🟢 entrées (ETF +1 762 M$ sur 30 jours ; rapport mondial de juin, périmé, affiché mais non utilisé). Catalyseur : Osprey Bitcoin Trust, 424B3, « produit coté » → marché : **confirmé**. Économie : offre +0,8 %/an. Conclusion : « Hausse (+5,1 % sur 7 jours) réelle mais incomplètement confirmée : macro. »

**ETH** — Institutions : 🔴 sorties (−141 M$ sur cinq séances) alors que la participation s'élargit. Catalyseurs : Fidelity Ethereum Fund (424B3) → **réaction mitigée** ; iShares Ethereum Trust → **pas encore intégré**. Économie : émission nette non mesurée (indexeur requis), demande en baisse. Conclusion : « Hausse (+4,2 %) réelle mais incomplètement confirmée : institutions — sorties, macro. »

**SOL** — Institutions : ⚪ données insuffisantes (pas d'ETF vérifié côté Farside ; rapport mondial périmé). Catalyseurs : 21Shares Solana Staking ETF et Franklin Solana Trust, « produit coté » → **réaction mitigée**. SIMD suivis avec leur statut réel (`Review` → « en discussion »). Économie : offre +2,9 %/an. Conclusion : « Hausse (+9,1 %) réelle mais incomplètement confirmée : macro. »

## 6. Tableau demandé (§24)

| Élément | Existait | Partiel | Ajouté | Source | Branché au Chief | Testé | UI | Statut |
|---|---|---|---|---|---|---|---|---|
| Altcoin Season Index | ✗ | | ✓ (recalculé) | CoinGecko | ✓ | ✓ | Marché | Opérationnel, fenêtre 90 j non reproduite |
| Market Breadth | | ✓ (3 actifs) | ✓ (marché) | CoinGecko | ✓ | ✓ | Marché | Opérationnel |
| CoinShares | ✗ | | ✓ | Flux officiel | ✓ | ✓ | Institutions | Opérationnel (dernier rapport juin → périmé) |
| Fusion Farside + CoinShares | ✗ | | ✓ | les deux | ✓ | ✓ | Institutions | Opérationnel, divergence affichée |
| Solana SIMD | ✗ | | ✓ | Dépôt officiel | ✓ | ✓ | Catalyseurs | Opérationnel |
| Ethereum EIP | ✗ | | ✓ | Dépôt officiel | ✓ | ✓ | Catalyseurs | Opérationnel |
| SEC / EDGAR | ✗ | | ✓ | EDGAR | ✓ | ✓ | Catalyseurs | Opérationnel (contact déclaré) |
| Protocol Economics | ✗ | | ✓ | chaîne + catalyseurs | ✓ | ✓ | Catalyseurs | Partiel : ETH non mesuré (clé requise) |
| Asset Catalysts | | ✓ (événements) | ✓ | multi | ✓ | ✓ | Catalyseurs | Opérationnel |
| Réaction au catalyseur | ✗ | | ✓ | bougies + dérivés | ✓ | ✓ | Catalyseurs | Opérationnel |
| Hiérarchie des sources | ✓ | | étendue | — | ✓ | ✓ | Catalyseurs | Opérationnel |
| Déduplication | ✓ | | réutilisée | — | ✓ | ✓ | — | Opérationnel |
| Fraîcheur | ✓ | | étendue | — | ✓ | ✓ | partout | Opérationnel |

## 7. Tests

`tests/unit/test_market_intelligence.py` — 34 tests, dont les dix interdits du §25 : SIMD jamais « active », dépôt jamais « approuvé », article + document = un seul événement, indice seul insuffisant pour une altseason, entrées CoinShares seules incapables de déclencher un achat, bonne nouvelle suivie d'une baisse → rejetée par le marché, donnée périmée jamais utilisée comme actuelle, source primaire préférée, divergence affichée, UNKNOWN qui reste UNKNOWN.

Backend : 1957 réussis, 15 ignorés. Flutter : 391 réussis.

## 8. Limites restantes

- **CoinShares** : le dernier rapport publié date du 01/06/2026 ; il est donc lu comme périmé. La lecture mondiale redeviendra active à la prochaine publication.
- **Fenêtre 90 jours** absente de l'API gratuite : la participation se mesure sur 30 jours au plus long.
- **Émission nette ETH, destruction de frais, cycle d'émission SOL** : non mesurés sans indexeur.
- **Flux baleines directionnels** : toujours indisponibles (clé requise), conformément au lot précédent.
- **TOTAL2 / TOTAL3** : les variations sur 30 jours n'apparaîtront qu'après un mois de collecte.
- **EDGAR** : la recherche plein texte est filtrée sur les formulaires utiles ; un dossier dont l'étape n'est pas lisible est écarté plutôt qu'affiché « étape inconnue ».
