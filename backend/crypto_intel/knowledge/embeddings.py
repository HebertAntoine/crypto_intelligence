"""Local sentence embeddings for the knowledge base.

BM25 finds passages that share vocabulary with the query. It cannot find a
passage that says the same thing in different words - and a trading course
rarely uses the exact phrasing of the question being asked.

Embeddings fill that gap. The model runs locally (all-MiniLM-L6-v2, ~80 MB, no
API key, no data leaving the machine) and handles cross-lingual matching, which
matters when the notes are in French and the metric names are in English.

Everything degrades cleanly: if the model cannot be loaded, retrieval falls
back to BM25 alone rather than failing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..logging_setup import get_logger
from ..settings import get_settings

log = get_logger("knowledge.embeddings")

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model: Any = None
_model_failed = False


def get_model() -> Any | None:
    """Load the sentence-transformer once, or return None if unavailable.

    A missing model is a normal state, not an error: the whole knowledge system
    still works on BM25.
    """
    global _model, _model_failed
    if _model is not None:
        return _model
    if _model_failed:
        return None

    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
        log.info("embedding_model_loaded", model=MODEL_NAME, dim=EMBEDDING_DIM)
        return _model
    except Exception as exc:
        _model_failed = True
        log.info(
            "embedding_model_unavailable",
            error=str(exc)[:200],
            consequence="knowledge search falls back to BM25 only",
        )
        return None


def embeddings_available() -> bool:
    return get_model() is not None


class EmbeddingStore:
    """Vectors on disk, keyed by chunk id.

    A plain .npz plus a JSON index rather than a vector database: the corpus is
    a personal document collection, not a web-scale index, and brute-force
    cosine over a few thousand vectors is instant.
    """

    def __init__(self, directory: Path | None = None) -> None:
        settings = get_settings()
        self.dir = directory or (settings.data_dir / "embeddings")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vectors_path = self.dir / "chunks.npz"
        self.index_path = self.dir / "index.json"
        self._ids: list[str] = []
        self._matrix: np.ndarray | None = None
        self._meta: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if self.vectors_path.exists() and self.index_path.exists():
            try:
                data = np.load(self.vectors_path)
                self._matrix = data["vectors"]
                index = json.loads(self.index_path.read_text(encoding="utf-8"))
                self._ids = index["ids"]
                self._meta = index.get("meta", {})
            except Exception as exc:
                log.warning("embedding_store_unreadable", error=str(exc))
                self._matrix, self._ids, self._meta = None, [], {}
        self._loaded = True

    def save(self) -> None:
        if self._matrix is None:
            return
        np.savez_compressed(self.vectors_path, vectors=self._matrix)
        self.index_path.write_text(
            json.dumps({"ids": self._ids, "meta": self._meta}), encoding="utf-8"
        )

    @property
    def count(self) -> int:
        self.load()
        return len(self._ids)

    def indexed_ids(self) -> set[str]:
        self.load()
        return set(self._ids)

    def add(self, chunks: list[dict[str, Any]], batch_size: int = 64) -> int:
        """Embed and store chunks that are not already indexed."""
        model = get_model()
        if model is None:
            return 0

        self.load()
        existing = set(self._ids)
        pending = [c for c in chunks if c["id"] not in existing]
        if not pending:
            return 0

        texts = [c["text"] for c in pending]
        vectors = model.encode(
            texts, batch_size=batch_size, show_progress_bar=False,
            normalize_embeddings=True,      # cosine becomes a dot product
        )
        vectors = np.asarray(vectors, dtype=np.float32)

        self._matrix = (
            vectors if self._matrix is None else np.vstack([self._matrix, vectors])
        )
        for chunk in pending:
            self._ids.append(chunk["id"])
            self._meta[chunk["id"]] = {
                "document_title": chunk.get("document_title", ""),
                "category": chunk.get("category", ""),
                "page": chunk.get("page"),
            }
        self.save()
        log.info("chunks_embedded", added=len(pending), total=len(self._ids))
        return len(pending)

    def remove(self, chunk_ids: list[str]) -> int:
        """Drop vectors for chunks that no longer exist (re-ingested document)."""
        self.load()
        if self._matrix is None or not chunk_ids:
            return 0
        drop = set(chunk_ids)
        keep = [i for i, cid in enumerate(self._ids) if cid not in drop]
        removed = len(self._ids) - len(keep)
        if removed == 0:
            return 0
        self._matrix = self._matrix[keep]
        self._ids = [self._ids[i] for i in keep]
        for cid in drop:
            self._meta.pop(cid, None)
        self.save()
        return removed

    def search(self, query: str, limit: int = 10, category: str | None = None) -> list[dict[str, Any]]:
        """Cosine similarity search. Vectors are normalised, so a dot product suffices."""
        model = get_model()
        self.load()
        if model is None or self._matrix is None or not self._ids:
            return []

        query_vector = np.asarray(
            model.encode([query], normalize_embeddings=True), dtype=np.float32
        )[0]
        scores = self._matrix @ query_vector

        order = np.argsort(-scores)
        results: list[dict[str, Any]] = []
        for i in order:
            chunk_id = self._ids[int(i)]
            meta = self._meta.get(chunk_id, {})
            if category and meta.get("category") != category:
                continue
            results.append({
                "chunk_id": chunk_id,
                "vector_score": round(float(scores[int(i)]), 4),
                **meta,
            })
            if len(results) >= limit:
                break
        return results

    def stats(self) -> dict[str, Any]:
        self.load()
        return {
            "vectors": len(self._ids),
            "model": MODEL_NAME if embeddings_available() else None,
            "dimension": EMBEDDING_DIM,
            "available": embeddings_available(),
            "path": str(self.dir),
        }


_store: EmbeddingStore | None = None


def get_store() -> EmbeddingStore:
    global _store
    if _store is None:
        _store = EmbeddingStore()
    return _store


def reciprocal_rank_fusion(
    rankings: list[list[str]], k: int = 60, weights: list[float] | None = None
) -> dict[str, float]:
    """Combine ranked lists by reciprocal rank.

    RRF rather than score averaging because BM25 scores and cosine similarities
    live on incompatible scales - normalising them against each other would be
    arbitrary, while rank position is directly comparable.
    """
    weights = weights or [1.0] * len(rankings)
    fused: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for position, item_id in enumerate(ranking, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + weight / (k + position)
    return fused
