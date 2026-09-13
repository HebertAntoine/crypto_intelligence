# Implémentation future-first

État vérifié le 13 septembre 2026. Le détail de l'état initial est conservé
dans [future-first-audit.md](future-first-audit.md).

## Résultat

Le produit conserve ses cinq couches (providers, stockage, moteurs
déterministes, synthèse, API/clients) et ses anciennes routes. La nouvelle
lecture future-first est additive : `/api/future/{asset}` devient le contrat
principal de décision pour BTC, ETH et SOL, sans supprimer l'historique utilisé
par la recherche, les percentiles et les backtests.

La décision suit cette hiérarchie : événement critique, attentes/liquidité et
flux, baleines/positionnement, puis technique. `EventRiskGate` force `WAIT`
devant un événement critique à forte amplitude dans les 48 heures lorsque la
distribution reste incertaine. Une technique haussière ne peut donc pas
neutraliser silencieusement un risque FOMC ou systémique.

## Contrat de données

`FutureEvent` et la table additive `future_events` portent identité canonique,
cycle de vie, source et tier, dates UTC, actifs touchés, importance, consensus,
distribution de marché horodatée, résultat/surprise, direction, amplitude,
chaîne causale et preuves. La fraîcheur et l'âge sont calculés à la lecture ;
ils ne sont jamais persistés comme `LIVE` ou `age_seconds=0`.

L'identité d'une analyse inclut un digest de tous les événements futurs. Une
modification de date, statut, importance, consensus, probabilité ou surprise
invalide donc le cache et produit un nouvel `analysis_id`.

## Sources futures

| Domaine | Source | Comportement |
|---|---|---|
| Politique monétaire | Federal Reserve | calendrier FOMC officiel, horaire Eastern converti en UTC |
| Inflation/emploi | BLS ICS | CPI, PPI, emploi, salaires ; UID officiel conservé |
| PCE/GDP | BEA | calendrier officiel et lien de publication |
| Financement US | TreasuryDirect | adjudications, CUSIP et échéance conservés |
| Réglementation | SEC/CFTC/White House/Treasury RSS | publication non programmée, étape législative explicite |
| Congrès | House, Senate Banking/Agriculture | hearings datés ; aucune heure manquante n'est devinée |
| Actions de loi | Congress.gov API | motion, cloture, vote et promulgation restent des étapes distinctes |
| Attentes Fed | adaptateur CME FedWatch licencié | distribution complète et timestamp obligatoires, sinon `UNAVAILABLE` |
| Protocoles | Ethereum Foundation, Solana Foundation | annonces majeures filtrées, direction non inférée |
| Incidents Solana | Solana Status API | incident actif/résolu, amplitude séparée de la direction |
| Géopolitique/énergie | flux configurés | seules les actions concrètes deviennent des événements |

Les indisponibilités partielles restent visibles dans le rapport de collecte.
Un blocage anti-bot, une clé absente ou un parseur qui ne reconnaît plus sa
source ne déclenche aucun fallback fictif.

## Cinq familles et scénarios

Les cinq slots sont constants :

1. macro & liquidité ;
2. catalyseurs & réglementation ;
3. flux institutionnels & baleines ;
4. positionnement & dérivés ;
5. technique & volatilité.

Chaque slot expose disponibilité, direction, mouvement attendu, confiance,
fraîcheur, raisons et sources. Les quatre scénarios sont `base_case`,
`bullish_case`, `bearish_case` et `tail_risk_case`. Une probabilité de scénario
reste `null` sans méthodologie sourcée et horodatée ; la confiance d'analyse
est affichée séparément.

## Interfaces

React et Flutter partagent la navigation Marchés / Analyse / Graphiques. La
page Analyse propose le sélecteur BTC/ETH/SOL, l'horizon, le prix actuel, la
décision, le risque événementiel, le prochain catalyseur, les raisons
prioritaires, les cinq familles, la timeline et les scénarios. Les anciennes
routes restent enregistrées pour compatibilité.

## Exploitation

Le scheduler collecte les événements futurs toutes les six heures. Pour activer
les sources à clé :

```dotenv
CONGRESS_API_KEY=...
CME_FEDWATCH_API_URL=https://endpoint-licencie.example/...
CME_FEDWATCH_API_KEY=...
WHALE_ALERT_API_KEY=...
```

Sans ces clés, les familles concernées se dégradent proprement. En particulier,
aucun transfert whale et aucune probabilité Fed ne sont simulés.

## Validation

Commandes de référence :

```bash
.venv/bin/pytest -q -m "not network"
.venv/bin/ruff check .
.venv/bin/mypy --no-site-packages --follow-imports=skip \
  backend/crypto_intel/future_events \
  backend/crypto_intel/engines/future_decision.py \
  backend/crypto_intel/engines/future_context.py \
  backend/crypto_intel/providers/events
npm --prefix frontend run typecheck
npm --prefix frontend run build
flutter analyze app
flutter test app
```

La suite vérifie notamment la séparation direction/amplitude, le gate 48 h,
les rolling windows ETF, la taxonomie whale, la déduplication, les fuseaux, la
fraîcheur runtime, les cinq slots, la surprise, le timestamp des probabilités,
l'absence de contradiction et l'anti-look-ahead point-in-time.

## Limites honnêtes

- FedWatch nécessite un flux autorisé fourni par l'utilisateur ; le projet ne
  scrape pas la page CME.
- Congress.gov nécessite sa clé gratuite.
- Whale Alert, CryptoQuant, Glassnode, Nansen et Arkham restent indisponibles
  sans licence ; aucun transfert n'est extrapolé.
- Une source officielle peut ne publier aucun événement pertinent. Cela produit
  `NO_DATA`, pas une annonce reconstruite.
- Le risque systémique IA/actions reste contextuel via les séries macro et
  cross-asset existantes ; aucune valorisation élevée ne déclenche seule une
  vente.
