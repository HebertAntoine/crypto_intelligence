# Contrat entre moteurs de données et IA

Mise à jour : 2026-10-30

## Autorité

Le LLM n'est ni une source de marché ni un calculateur autoritatif. Les providers, moteurs déterministes et validateurs produisent observations, scores, preuves, décisions, niveaux et scénarios. Le LLM peut seulement rendre leurs conclusions plus lisibles.

Le pipeline continue de fonctionner avec `LLM_PROVIDER=none`. Une panne du modèle dégrade la prose, pas l'analyse calculée.

## Entrée effectivement fournie

Chaque analyste reçoit un bloc compact comprenant score, confiance, fraîcheur, constats favorables/défavorables/neutres et données manquantes. Le Chief reçoit les conclusions des analystes, les convictions par horizon, contradictions, niveaux techniques et événements à venir.

Ce n'est pas encore un objet monolithique portant exactement tous les champs de l'exemple du cahier des charges. Les contrats sont composés depuis les modèles existants. En particulier, le radar S01–S15 et les claims issus de RSS ne sont pas automatiquement inclus dans le bloc du Chief.

Un item absent reste absent ou `UNAVAILABLE`; il n'est jamais remplacé par une estimation narrative.

## Règles système

- utiliser uniquement le bloc fourni;
- ne créer aucun prix, date, pourcentage, ratio, niveau ou source;
- respecter le score déterministe transmis;
- distinguer fait, calcul, interprétation et hypothèse;
- conserver les contradictions et données manquantes;
- respecter le statut réglementaire;
- ne pas déduire une causalité d'une coïncidence;
- ne jamais produire une probabilité de scénario;
- ne recommander ni ordre, ni taille de position, ni exécution;
- ne pas transformer un claim externe non confirmé en mesure financière.

## Schémas de sortie

`AnalystOutput` borne le score et la confiance et structure résumé, constats, données manquantes et citations de connaissance. Chaque constat narratif doit porter au moins un `evidence_ref`, et chaque référence doit appartenir aux preuves effectivement exposées au modèle. Une référence absente, inconnue ou un constat produit alors qu'aucune preuve n'a été exposée rejette l'enrichissement. `ChiefAnalystOutput` structure synthèse, arguments favorables/défavorables, contradictions, catalyseurs, risques, conditions de changement d'avis et lacunes sous la même contrainte.

`ScenarioOutput.probability` n'accepte que `null`. Les scénarios rédigés par le LLM ne remplacent jamais les trois objets construits par `ChiefMarketAnalyst`. Le modèle de domaine autorise séparément une probabilité uniquement avec un drapeau de calibration et un dossier complet d'évaluation hors échantillon; aucun modèle de ce type n'alimente actuellement le Chief.

Le rapport public `AssetAnalysis` assemble identifiant, date, actif, prix, scores, conviction, synthèse, contradictions, scénarios, décision, sources et lacunes. Les routes future-first ajoutent `analysis_id`, `as_of`, familles, qualité et décisions par horizon.

## Validation numérique

Tous les champs narratifs copiés vers `AnalystResult` et `ChiefSynthesis` sont concaténés puis contrôlés contre les nombres présents dans le bloc autorisé. Le contrôle couvre aussi petits entiers, pourcentages et ratios; les anciennes exemptions par taille ne s'appliquent plus.

Le garde-fou reconnaît les formats avec séparateur, un arrondi borné à 1 % et uniquement les changements d'échelle explicitement écrits (`k`, million, milliard, etc.). Il compare aussi la dimension explicite (`%`, points de base, ratio, USD/USDT, EUR, heures ou jours) et les termes identifiant le sujet. Le même nombre attribué à une autre métrique, à une autre devise ou à une unité arbitrairement redimensionnée n'est pas accepté. Toute valeur non rattachable rejette l'enrichissement entier et conserve le texte déterministe avec une note de donnée manquante.

Cette validation réduit les substitutions sémantiques simples, mais ne constitue pas une compréhension linguistique générale ni une preuve de causalité. Le fact-check déterministe et les objets de preuve restent nécessaires.

## Validation JSON et dégradation

Les providers LLM extraient un objet JSON puis le valident par Pydantic. Une sortie invalide peut être retentée; après échec, `LLMValidationError` remonte au wrapper, la synthèse déterministe reste publiée et `llm_used=false`.

Une sortie brute mal formée n'est jamais affichée.

## Confidentialité

Lexa peut utiliser Ollama local. Aucun LLM cloud n'est obligatoire. Envoyer une transcription privée à un tiers exigerait consentement, contrat et politique de conservation spécifiques; rien dans cette implémentation ne les suppose acquis.

## Limites restantes

- Le format rédigé A–I demandé n'est pas un schéma unique validé section par section.
- Une référence est imposée par constat structuré, mais pas encore phrase par phrase dans les champs de synthèse libres.
- Le garde-fou numérique et lexical n'est pas un fact-check sémantique général.
- Le pipeline de news général n'est pas préalablement transformé en claims vérifiés.
