# Licences, droits et coûts des données

Date de vérification documentaire : 2026-10-29

## Règle de décision

Une clé permet l'accès ; elle ne prouve pas le droit de stocker, d'afficher ou de redistribuer. Le comportement sûr est l'indisponibilité tant que le contrat applicable n'est pas confirmé.

Cette intégration applique cette règle à trois zones à risque :

- `macro.indices` n'utilise Twelve Data qu'avec une clé et le consentement opérateur `TWELVE_DATA_REDISTRIBUTION_AUTHORIZED=true` ;
- CoinGecko et le breadth associé exigent ensemble une clé Pro, `COINGECKO_COMMERCIAL_USE_AUTHORIZED=true` et `COINGECKO_ATTRIBUTION_CONFIGURED=true` ;
- tout contenu FRED reste exclu, y compris des caches et backfills, sans `FRED_CONTENT_USE_AUTHORIZED=true`, qui doit représenter une autorisation documentée applicable à ce logiciel et non la simple accessibilité du site ;
- une série FRED portant des droits ICE BofA ou Cboe exige en plus `FRED_THIRD_PARTY_REDISTRIBUTION_AUTHORIZED=true`.

## Registre de conformité

| Source | Coût possible | Stockage/affichage | Décision actuelle |
|---|---|---|---|
| Institutions publiques Fed, Treasury, BLS, BEA, BCE, BoJ | Généralement sans abonnement | Vérifier les mentions propres aux sites et séries | Utilisées avec provenance ; aucune garantie générale de redistribution au-delà des conditions publiées. |
| FRED | Clé API gratuite pour certains endpoints | Les conditions courantes restreignent notamment stockage/cache et usages liés au développement logiciel/IA; certaines séries ajoutent des droits tiers | Tous les adaptateurs FRED échouent fermé sans autorisation documentée; ICE/Cboe exigent aussi le droit tiers. |
| Twelve Data | Plans gratuits et payants, quotas variables | Droits d'usage commercial/redistribution dépendants du plan | Double opt-in ; aucune donnée en production par défaut. |
| CME FedWatch | Accès API/licence commerciale possible | Ne pas scraper ni republier sans accord | Endpoint et clé dédiés obligatoires, sinon indisponible. |
| CoinGecko | Plan payant commercial ou contrat sur mesure selon l'usage | L'affichage public commercial requiert le plan/droit applicable et une attribution visible; revente/redistribution peut exiger un accord sur mesure | Endpoint Pro et en-tête secret uniquement; activation avec clé, droit commercial et attribution tous confirmés. |
| Binance/Coinbase/Kraken/Deribit | Endpoints publics et offres commerciales | Conditions propres à chaque bourse | Mesures utilisées avec source ; revoir avant redistribution commerciale. |
| DeFiLlama/blockchain providers | Souvent sans clé ou freemium | Quotas/attribution propres | Adaptateurs présents ; pas de promesse de SLA. |
| Coinglass/SoSoValue/Glassnode/CryptoQuant/Nansen/Arkham/Whale Alert | Payant ou freemium | Contrat et redistribution spécifiques | Désactivés sans clé ; coûts non inclus au projet. |
| Farside/CoinShares | Site ou publication publique | L'accès public ne vaut pas autorisation de republication | Usage prudent ; aucun contournement anti-bot. |
| RSS médias | Gratuit à consulter | Reproduire les articles peut être interdit | Titres, métadonnées, liens et courts résumés seulement ; aucun paywall contourné. |
| SEC EDGAR/Congress.gov | Accès public ; clé Congress | Politiques d'usage et identification | Les appels SEC sont refusés sans User-Agent portant un contact réel; limites/rate policy à respecter. |
| Lexa/transcriptions/Excel | Contenu privé de l'utilisateur | Pas de diffusion publique | Base séparée, pas de snapshot public, pas d'ajout du classeur à Git. |
| LLM cloud | Facturation au token selon provider | Contrat du fournisseur et confidentialité | Optionnel ; `none`/Ollama permettent un chemin local. |

## Références contractuelles contrôlées

- Twelve Data : [Terms of Use](https://twelvedata.com/terms), [documentation API](https://twelvedata.com/docs) et [usage commercial/personnel](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage).
- FRED : [conditions légales courantes](https://fred.stlouisfed.org/legal/terms/) et [documentation API](https://fred.stlouisfed.org/docs/api/fred/).
- CME : [FedWatch API](https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html).
- CoinGecko : [API Terms](https://www.coingecko.com/en/api_terms) et [licences commerciales](https://support.coingecko.com/articles/1043089972-what-are-the-differences-between-commercial-and-custom-licenses).

Les conditions peuvent changer. La date de cette revue doit être actualisée avant un lancement commercial ou un changement de plan.

## Procédure d'activation d'une source sous licence

1. Identifier la capacité et les écrans qui exposeront la donnée.
2. Lire le contrat du plan effectivement souscrit, pas seulement une page marketing.
3. Confirmer cache, rétention historique, dérivés calculés, attribution et redistribution publique.
4. Conserver en interne le plan, la date, la preuve et le responsable de la validation.
5. Configurer la clé ou l'identité requise côté serveur.
6. Activer chaque drapeau de droits seulement après validation; pour CoinGecko, configurer aussi l'attribution visible avant la collecte.
7. Tester les statuts, quotas, fuseaux, symboles et erreurs 429.
8. Désactiver l'export public si le droit est local/interne seulement.

## Coûts non chiffrés

Le dépôt ne fixe aucun tarif car ceux-ci varient avec le plan, le volume et la redistribution. Les postes possibles sont Twelve Data, CME, CoinGecko commercial, fournisseurs ETF/dérivés/baleines, hébergement persistant, sauvegardes, push tiers et LLM cloud. Aucun budget ne doit être déduit des noms de variables.

## Limites

`Provenance.license_note` et certains `meta.license_status` portent une trace d'exécution, mais le dépôt ne contient pas encore un registre juridique signé par abonnement. Les drapeaux d'environnement sont des garde-fous techniques, pas une preuve juridique autonome. La revue ci-dessus reflète les pages officielles contrôlées à la date indiquée; elle ne remplace pas l'accord du plan effectivement souscrit.
