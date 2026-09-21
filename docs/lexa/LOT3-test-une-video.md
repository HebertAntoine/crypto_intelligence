# Intégration Lexa — LOT 3 : test complet sur UNE vidéo

## 1. La chaîne

```
transcription horodatée d'UNE vidéo
→ nettoyage (balises, espaces ; aucun mot modifié)
→ cryptos citées (alias : bitcoin → BTC, ripple → XRP, …)
→ passages par crypto (le sujet = la dernière crypto nommée)
→ lecture du contexte par un modèle LOCAL (Ollama gemma3:12b, sur cette machine)
→ vérification déterministe (anti-hallucination)
→ tableau sur 100 € + suivi des niveaux sur les prix réels
→ rapport humain + rapport de validation + JSON typé
```

Rien n'est importé dans la base Lexa : on attend ta validation.

## 2. D'où vient la transcription

L'étape « écoute / récupération audio » n'est **pas** construite pour LexaMoon : les CGV interdisent la reproduction du contenu (voir LOT 2). Tu as écrit « lorsque cela est techniquement autorisé ». Les sources permises sont donc :

- la transcription intégrée à YouTube (« Afficher la transcription »), copiée telle quelle, pour une vidéo publique de Lexa ;
- un texte ou des sous-titres (SRT, VTT) fournis par Lexa ;
- plus tard, un fichier audio si Lexa l'autorise par écrit (brouillon d'e-mail dans le LOT 2).

Formats acceptés : `[12:31] texte`, `12:31 texte`, le copier-coller YouTube (horodatage sur une ligne, texte sur la suivante), SRT et WebVTT. Un texte sans horodatage est refusé, parce qu'on ne pourrait rien citer.

## 3. Contrôle anti-hallucination

Le modèle ne fait que proposer. Le vérificateur tranche, et il est testé dans `tests/unit/test_lexa_extraction.py` :

| Règle | Effet |
|---|---|
| Un prix doit être écrit dans le passage cité | sinon il est **rejeté**, listé dans « ERREURS POSSIBLES » et absent du tableau |
| Un prix dit ailleurs qu'au minutage cité | le minutage est corrigé, avec une note |
| La citation conservée | c'est toujours le texte exact de la transcription, jamais une reformulation |
| Une allocation absente du texte | elle est retirée et signalée ; aucune n'est attribuée à Lexa |
| « 40 % sur la première zone et 60 % sur la deuxième » | lu directement dans le texte, avec son minutage |
| Une unité de temps (4 h, daily…) non dite | elle est retirée |
| Une date d'événement non dite | elle est retirée |
| Une « zone d'achat » dont le passage parle de cassure sans parler d'achat | elle est signalée « à vérifier » et rétrogradée en 🟡 |
| Un argument ou un scénario sans passage retrouvé | il est écarté et signalé |
| Une crypto seulement citée | pas de fiche |
| Le prompt | il ne contient aucune valeur de référence (testé) |

Les chiffres calculés par l'application (répartition à parts égales quand Lexa n'en donne pas, prix moyen, valeur simulée) portent toujours la mention **CALCUL APP** ou **SIMULATION APP**.

## 4. Utilisation

- **Dans l'app :** http://127.0.0.1:8100/app/ → onglet 🎬 Lexa → 🧪 → colle la transcription → « Lancer le test ». Le résultat a quatre onglets : Rapport, Validation, Transcription, JSON.
- **En ligne de commande :**
  ```
  cd backend && ../.venv/bin/python -m crypto_intel.cli lexa-test transcription.txt \
    --title "Titre" --published-at 2026-09-18T08:00:00Z
  ```

Les fichiers sont dans `data/lexa/tests/<run_id>/` (en 0600, ignorés par Git) : `transcript.txt`, `extraction.json` (schéma `lexa-extraction/1`, défini dans `backend/crypto_intel/lexa/schema.py`), `report.md` et `validation.md`.

## 5. Essai de la chaîne sur une transcription FICTIVE

La transcription `tests/fixtures/lexa_transcript_fictive.txt` a été écrite pour tester la chaîne. **Ce n'est pas une vidéo Lexa**, et ses valeurs n'ont rien à voir avec l'exemple XRP. Résultat avec gemma3:12b, en environ 50 s :

- ✅ « La cassure des 62 000 serait mauvaise » est classé 🧱 support, pas achat.
- ✅ « Si ADA revient vers 0,4870, ça pourrait redevenir intéressant » est classé 🟢 achat, en 🟡 interprétation du contexte.
- ✅ Renforcement, confirmation (clôture 4 h), invalidation (daily) et TP1 à TP3 sont extraits.
- ✅ La répartition 40 % / 60 % dite par l'auteur est reprise et attribuée à Lexa.
- ✅ Les deux scénarios (cassure / rejet) restent séparés.
- ✅ Solana, seulement citée, n'a pas de fiche.
- ✅ 0 valeur inventée.
- 🟡 « Pas de clôture daily au-dessus de 66 800 » est classé résistance (journalier), et non confirmation.
- 🟡 La direction haussière du RSI n'est pas reprise : le modèle est prudent.

## 6. Étape suivante

Il faut **une vraie transcription** d'une vidéo Lexa, obtenue par une des sources du §2. On lance le test, tu remplis la « COMPARAISON MANUELLE » du rapport de validation, et l'automatisation des autres vidéos n'est pas développée avant ta validation.
