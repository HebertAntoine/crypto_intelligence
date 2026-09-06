# Base de connaissances personnelle

## Objectif

Tes cours, PDF, notes et transcriptions deviennent une source de connaissance que
le système cite quand il explique ce que les données montrent.

```
Cours   : « Une divergence RSI baissière signale un essoufflement du momentum… »
Données : « Une divergence RSI baissière est détectée sur ETH 4H (force 68). »
Moteur  : relie les deux et cite le passage utilisé.
```

## Séparation stricte, imposée par le schéma

| Table | Contenu | Origine |
|---|---|---|
| `observations` | données de marché | providers uniquement |
| `knowledge_chunks` | passages de tes documents | ingestion |

Un cours ne peut donc **jamais** devenir une donnée de marché. Le système ne lira
jamais un prix dans un PDF pour l'afficher comme une observation.

## Utilisation

```bash
knowledge/
├── courses/      formations
├── transcripts/  transcriptions vidéo
├── trading/      analyse technique, figures, gestion du risque
├── bitcoin/      ethereum/  solana/
├── macro/        regulation/
```

```bash
make ingest
```

Le sous-dossier devient la **catégorie**, ce qui permet de cibler une recherche
(par exemple uniquement `trading` pour une question sur les figures chartistes).

## Fonctionnement

1. **Extraction** — TXT/MD lus directement, PDF page par page via `pypdf`.
2. **Découpage** — ~1100 caractères, recouvrement 180, **sur les frontières de
   paragraphes** pour ne pas couper une explication en deux.
3. **Conservation** — document, titre, catégorie et **numéro de page** sont gardés.
4. **Indexation** — SQLite FTS5, classement BM25.
5. **Recherche** — chaque analyste formule une requête à partir de ce qu'il a
   détecté (`knowledge_query()`), et les passages remontés sont cités.

L'ingestion est **idempotente** : un fichier inchangé (hash SHA-256 identique)
est ignoré ; un fichier modifié voit ses anciens chunks supprimés et réindexés.

## Pourquoi FTS5 plutôt que des embeddings

- aucune dépendance supplémentaire, aucun modèle à télécharger ;
- fonctionne immédiatement, hors ligne ;
- BM25 est très efficace sur du vocabulaire technique précis
  (« divergence RSI », « triangle ascendant »).

L'interface `KnowledgeRetriever` est abstraite : brancher des embeddings plus
tard ne touchera que `knowledge/store.py`.

## API

```
GET  /api/knowledge/stats
GET  /api/knowledge/search?q=divergence+RSI&category=trading
POST /api/knowledge/ingest
```

## Limites actuelles

- Formats : TXT, MD, PDF. (DOCX, EPUB, SRT/VTT restent à faire.)
- Les PDF scannés sans couche texte ne donnent rien — l'OCR n'est pas intégré.
- La recherche est lexicale : un synonyme jamais écrit dans tes documents ne sera
  pas trouvé. C'est la contrepartie assumée du choix BM25.
