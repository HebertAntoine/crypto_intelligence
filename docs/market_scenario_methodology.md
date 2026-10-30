# Méthode des scénarios de marché

Mise à jour : 2026-10-30

## Convention

Le contrat future-first public produit exactement trois scénarios conditionnels, dans cet ordre :

| Identifiant public | Affichage | Fonction |
|---|---|---|
| `base_case` | Intermédiaire | persistance de la configuration observée sans supposer l'issue des événements non résolus |
| `bullish_case` | Favorable | résolution haussière sous conditions mesurables |
| `bearish_case` | Défavorable | résolution baissière sous conditions mesurables |

Ils sont conditionnels. Ils ne sont ni des prédictions certaines, ni des ordres, ni des conseils personnalisés.

Le modèle historique `AssetAnalysis` du Chief conserve les noms legacy `central`, `bull` et `bear`; ils correspondent aux mêmes trois conventions d'affichage et ne créent pas un quatrième scénario. Les clients React et Flutter filtrent le contrat future-first sur les trois identifiants ci-dessus et les ordonnent explicitement. `tail_risk_case`, bien que présent dans une énumération interne legacy, n'est pas publié par le générateur courant.

## Contrat produit

Chaque `FutureScenario` courant porte : identifiant, hypothèse, horizon, actifs concernés, éléments déjà confirmés, identifiants de preuve, conditions nécessaires, signaux de confirmation, invalidations, incertitudes et note de prudence. L'horizon vient de la décision demandée (`24h`, `7d` ou `30d`) et l'actif analysé est explicitement associé au scénario. Le générateur historique du Chief garde son horizon `8-30 days`.

Les anciens rapports persistés peuvent ne pas posséder tous ces champs. Les clients gardent donc ces propriétés optionnelles à la lecture; cette compatibilité n'autorise pas le générateur courant à les omettre silencieusement.

## Construction à partir des preuves disponibles

Les scénarios sont bâtis après les analystes déterministes. Le générateur ne crée une condition que si l'entrée correspondante est disponible :

- clôture, support, résistance et état du volume issus du snapshot journalier validé;
- flux ETF net validé;
- tendance du dollar mesurée;
- régime de liquidité stablecoin mesuré;
- état du funding mesuré;
- contradictions et événements à venir présents dans le contexte.

Une entrée absente devient une incertitude. Elle ne produit ni condition générique « support/résistance la plus proche », ni flux supposé, ni niveau inventé. Si aucun déclencheur propre au scénario n'est disponible, la narration dit explicitement que le chemin reste insuffisamment spécifié.

Les trois chemins restent présents même lorsque la conviction est directionnelle : une tendance optimiste peut continuer malgré un risque élevé et un marché dégradé peut rebondir.

## Probabilités

La conversion heuristique score/confiance en distribution `central/bull/bear` a été supprimée. Sans modèle qualifié, les trois scénarios ont `probability=null`, `calibrated=false` et l'interface n'affiche aucun chiffre.

Le schéma LLM interdit toute probabilité numérique et le Chief ignore ses scénarios narratifs. Le modèle future-first n'accepte une distribution que si elle couvre exactement les trois cas, somme approximativement à un, marque chaque valeur `calibrated=true`, fournit source et instant d'observation et valide des métadonnées complètes : nom/version du modèle, cible, horizon, méthode, `out_of_sample_tested=true`, taille de l'échantillon hors échantillon, métrique, score, date d'évaluation et preuves. React et Flutter masquent eux aussi toute probabilité qui ne satisfait pas ce contrat. Aucun modèle probabiliste ainsi qualifié n'est branché au générateur courant.

## Distinction avec le diagnostic de risque

Le niveau de risque peut devenir `CRITICAL` lorsque l'amplitude événementielle est extrême. Ce niveau n'est pas un scénario supplémentaire et ne transforme pas l'écran en quatre chemins concurrents. Les trois scénarios ci-dessus demeurent l'unique convention publique.

## Invalidation et prudence

Une invalidation doit être falsifiable : clôture hors d'une zone réellement mesurée ou retournement d'un régime de flux observé. En l'absence de déclencheur validé, le système indique qu'elle ne peut pas encore être spécifiée.

Une contradiction forte durcit la note de prudence et exige plusieurs confirmations indépendantes. Le système ne génère ni fourchette de baisse, ni taille de position, ni ordre automatique.

## Limites

- Les conditions dépendent de la couverture au moment du calcul; une famille indisponible demeure une incertitude.
- Les scénarios future-first s'arrêtent à 30 jours; le diagnostic de risque 31–90 jours est un objet distinct et reste indéterminé sans familles dédiées.
- Les interfaces anciennes peuvent afficher moins de champs pour des rapports historiques créés avant ce contrat.
- Aucun résultat de calibration probabiliste hors échantillon n'est revendiqué.
