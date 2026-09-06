# Base de connaissances personnelle

Dépose ici tes cours, PDF, notes et transcriptions. Formats : **TXT, MD, PDF**.

```
knowledge/
├── courses/      cours et formations
├── transcripts/  transcriptions de vidéos
├── trading/      analyse technique, figures chartistes, gestion du risque
├── bitcoin/      documents spécifiques BTC
├── ethereum/     documents spécifiques ETH
├── solana/       documents spécifiques SOL
├── macro/        macroéconomie
└── regulation/   régulation et cadre légal
```

Puis : `make ingest`

Le sous-dossier devient la **catégorie** du document, ce qui permet de cibler
une recherche (par exemple uniquement `trading` pour une question sur les figures).

## Important

Ces documents sont une **source de connaissance**, pas une source de données
temps réel. Le système ne lira jamais un prix dans un PDF pour l'afficher comme
une donnée de marché : ils sont stockés dans une table séparée (`knowledge_chunks`),
distincte des observations de marché (`observations`).

Le lien entre les deux se fait à l'analyse : les données détectent qu'une
divergence RSI est présente sur ETH 4H, ton cours explique ce que cela signifie,
et le passage utilisé est cité dans le rapport.

Ces fichiers sont exclus de git (voir `.gitignore`) — ils t'appartiennent.
