# Page Aujourd'hui — audit bloc par bloc

Verdict par bloc, avec ce qui a été fait. La règle appliquée : **une
information importante, une carte principale.** Les autres blocs peuvent y
faire référence, jamais la répéter mot pour mot.

## Ce que la page affichait en double

Quatre informations apparaissaient deux ou trois fois :

| Information | Où elle apparaissait | Décision |
| --- | --- | --- |
| « proche du haut du range » | barre de position, phrase de décision, contexte immédiat, conditions de changement | REMOVE_DUPLICATE — retirée du contexte |
| « CPI · dans 3 jours » | contexte immédiat **et** bloc « à surveiller » | MERGE — le bloc ne revient que s'il ajoute quelque chose |
| titre de pression | titre, phrase de résumé, décompte de familles | REMOVE_DUPLICATE — le résumé en phrase supprimé |
| « aucun avantage démontré » | ligne Direction/Timing/Avantage et bloc avantage | KEEP — la ligne est un résumé, le bloc porte le détail |

## Bloc par bloc

| Bloc | Verdict | Ce qui a changé |
| --- | --- | --- |
| En-tête actif + prix live | KEEP | inchangé |
| Ligne « analyse calculée à » + dérive | KEEP | inchangé ; deux couches, deux horodatages |
| Bandeau d'identifiants divergents | KEEP | ne s'affiche que sur désaccord réel |
| Direction / Timing / Avantage | KEEP | trois lectures indépendantes, jamais fusionnées |
| Décision principale | SIMPLIFY | phrase raccourcie à deux propositions ; le garde-fou quitte la carte pour « voir pourquoi » |
| Barre de position 4H | KEEP | seule porteuse de la position |
| Support / résistance | KEEP | distances réelles, issues du clustering de swings |
| Qui achète, qui vend | SIMPLIFY | titre verrouillé par la couverture ; résumé en phrase supprimé ; badge de couverture ajouté |
| Contexte immédiat | SIMPLIFY | « Position » retirée (affichée au-dessus) ; échéance raccourcie en « CPI US · 3 j » |
| À surveiller | MERGE | ne réapparaît que si urgence ≤ 24 h ou plusieurs échéances |
| Positionnement / ETF | KEEP | en mots ; les valeurs brutes restent dans Preuves |
| Ce qui ferait changer la décision | SIMPLIFY | titre court + une ligne, au lieu d'une phrase de trente mots |
| Structure par unité | SIMPLIFY | une phrase ajoutée ; la note méthodologique déplacée au détail |
| Couverture des données | SIMPLIFY | « 11/13 disponibles, 9 à jour · 2 anciennes » |
| Dernier changement de lecture | KEEP | absent tant qu'aucun historique n'est enregistré |

## Déplacé vers « voir pourquoi »

- Le garde-fou qui a plafonné l'état (« Incertitude 72/100 : plafond
  attendre ») — il reste dans `decision.guard_rails`, nommé et sourcé.
- Les facteurs classés aide / frein / manque, avec leur source et leur
  horodatage.
- L'explication complète des trois lectures Direction / Timing / Avantage.

## Déplacé vers Preuves

- Poids, apport pondéré et dénominateur de chaque famille de pression — la
  feuille de détail les montre, la carte non.
- Valeurs brutes de funding, d'open interest et de flux ETF par émetteur.
- Taille d'échantillon : n brut, n effectif, MDE, taux de réussite, MFE, MAE.
- La note méthodologique sur l'alignement des horizons.

## Règles de texte appliquées

| Élément | Règle | Exemple |
| --- | --- | --- |
| Titre de bloc | 2–6 mots | « CE QUI AMÉLIORERAIT LE TIMING » |
| Valeur | 1–4 mots | « Proche du haut du range » |
| Explication | 2 phrases au plus | « Tendance nettement positive, mais BTC est proche du haut de son range 4H. L'entrée est moins intéressante à ce niveau. » |
| Condition | titre court + une ligne | « Retour vers le support — Meilleur emplacement si le support tient. » |

Un test tient chacune : titre d'une condition ≤ 6 mots, phrase de décision
≤ 30 mots et ≤ 2 points, détail d'une condition ≤ 2 points.

## Hiérarchie

1. **Aujourd'hui** — que se passe-t-il, est-ce intéressant, pourquoi en deux
   phrases, qu'est-ce qui changerait la lecture.
2. **Voir pourquoi** — l'explication humaine, facteur par facteur.
3. **Preuves** — les chiffres et les méthodes.
4. **Recherche** — est-ce que cette méthode fonctionne historiquement.

Rien n'a été supprimé du système : ce qui quitte la carte principale reste
accessible d'un cran plus bas. Simple en surface, profond au clic.

## Ce que je n'ai pas vérifié

Je ne peux pas voir l'application tourner. La revue est statique et par
widget ; le rendu sur téléphone reste à vérifier.
