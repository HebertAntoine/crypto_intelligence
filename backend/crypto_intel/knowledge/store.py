"""Knowledge store backed by SQLite FTS5 (BM25 ranking).

Chosen over an embedding database on purpose: zero extra dependencies, no model
download, works offline immediately, and it is genuinely good at finding
passages about "RSI divergence" in a trading course.

`KnowledgeRetriever` is an interface, so swapping in embeddings later touches
this file only.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import text

from ..db.session import get_engine, session_scope
from ..logging_setup import get_logger

log = get_logger("knowledge.store")

FTS_TABLE = "knowledge_fts"


def ensure_fts() -> bool:
    """Create the FTS5 virtual table if the SQLite build supports it."""
    engine = get_engine()
    if not engine.url.drivername.startswith("sqlite"):
        return False
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} "
                    "USING fts5(chunk_id UNINDEXED, document_title, category, text)"
                )
            )
        return True
    except Exception as exc:
        log.warning("fts5_unavailable", error=str(exc))
        return False


def index_chunks(rows: list[dict[str, Any]]) -> int:
    if not rows or not ensure_fts():
        return 0
    with get_engine().begin() as conn:
        for r in rows:
            conn.execute(
                text(
                    f"INSERT INTO {FTS_TABLE} (chunk_id, document_title, category, text) "
                    "VALUES (:cid, :title, :cat, :txt)"
                ),
                {"cid": r["id"], "title": r["document_title"],
                 "cat": r["category"], "txt": r["text"]},
            )
    return len(rows)


def clear_document_index(document_id: str, chunk_ids: list[str]) -> None:
    if not chunk_ids or not ensure_fts():
        return
    with get_engine().begin() as conn:
        for cid in chunk_ids:
            conn.execute(
                text(f"DELETE FROM {FTS_TABLE} WHERE chunk_id = :cid"), {"cid": cid}
            )


def _sanitize_query(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    User queries contain quotes, hyphens and operators that FTS5 parses as
    syntax; quoting each term avoids syntax errors and accidental operators.
    """
    terms = re.findall(r"[A-Za-z0-9_]+", query)
    terms = [t for t in terms if len(t) > 1]
    if not terms:
        return ""
    return " OR ".join(f'"{t}"' for t in terms)


class KnowledgeRetriever(ABC):
    """Interface: BM25 today, embeddings later, same callers."""

    @abstractmethod
    def search(self, query: str, limit: int = 5, category: str | None = None) -> list[dict[str, Any]]:
        ...


class FTSRetriever(KnowledgeRetriever):
    def search(self, query: str, limit: int = 5, category: str | None = None) -> list[dict[str, Any]]:
        match = _sanitize_query(query)
        if not match or not ensure_fts():
            return []

        sql = (
            f"SELECT chunk_id, document_title, category, "
            f"snippet({FTS_TABLE}, 3, '', '', ' ... ', 32) AS snip, "
            f"bm25({FTS_TABLE}) AS rank "
            f"FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH :q "
        )
        params: dict[str, Any] = {"q": match, "lim": limit}
        if category:
            sql += "AND category = :cat "
            params["cat"] = category
        # bm25() returns lower = better in SQLite.
        sql += "ORDER BY rank LIMIT :lim"

        try:
            with get_engine().connect() as conn:
                rows = conn.execute(text(sql), params).fetchall()
        except Exception as exc:
            log.warning("knowledge_search_failed", error=str(exc))
            return []

        out: list[dict[str, Any]] = []
        for row in rows:
            full = self._chunk_text(row[0])
            out.append({
                "chunk_id": row[0],
                "document_title": row[1],
                "category": row[2],
                "snippet": row[3],
                "score": round(-float(row[4]), 4),
                "text": full or row[3],
            })
        return out

    def _chunk_text(self, chunk_id: str) -> str | None:
        from ..db.base import KnowledgeChunkRow

        with session_scope() as s:
            row = s.get(KnowledgeChunkRow, chunk_id)
            return row.text if row else None


class HybridRetriever(KnowledgeRetriever):
    """BM25 + vector similarity, fused by reciprocal rank.

    BM25 is precise on exact terminology ("RSI divergence"); embeddings catch
    the same idea expressed differently, including across languages. Fusing
    both beats either alone, and the system still works if the embedding model
    is unavailable - it simply becomes BM25.
    """

    def __init__(self, bm25_weight: float = 1.0, vector_weight: float = 1.0) -> None:
        self.bm25 = FTSRetriever()
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight

    def search(self, query: str, limit: int = 5, category: str | None = None) -> list[dict[str, Any]]:
        from .embeddings import embeddings_available, get_store, reciprocal_rank_fusion

        # Over-fetch from each retriever so fusion has something to work with.
        lexical = self.bm25.search(query, limit=limit * 3, category=category)

        if not embeddings_available():
            for hit in lexical:
                hit["retrieval"] = "bm25"
                hit["vector_score"] = None
            return lexical[:limit]

        vector_hits = get_store().search(query, limit=limit * 3, category=category)

        fused = reciprocal_rank_fusion(
            [[h["chunk_id"] for h in lexical], [h["chunk_id"] for h in vector_hits]],
            weights=[self.bm25_weight, self.vector_weight],
        )

        by_id = {h["chunk_id"]: h for h in lexical}
        vector_by_id = {h["chunk_id"]: h for h in vector_hits}

        results: list[dict[str, Any]] = []
        for chunk_id, score in sorted(fused.items(), key=lambda kv: -kv[1])[:limit]:
            hit = by_id.get(chunk_id)
            if hit is None:
                # Found only by the vector search: fetch its text from the DB.
                text = self.bm25._chunk_text(chunk_id)
                meta = vector_by_id.get(chunk_id, {})
                if text is None:
                    continue
                hit = {
                    "chunk_id": chunk_id,
                    "document_title": meta.get("document_title", ""),
                    "category": meta.get("category", ""),
                    "snippet": text[:200],
                    "score": 0.0,
                    "text": text,
                }
            hit = dict(hit)
            hit["fusion_score"] = round(score, 5)
            hit["vector_score"] = vector_by_id.get(chunk_id, {}).get("vector_score")
            hit["retrieval"] = (
                "hybrid" if chunk_id in by_id and chunk_id in vector_by_id
                else ("bm25" if chunk_id in by_id else "vector")
            )
            results.append(hit)
        return results


def get_retriever(hybrid: bool = True) -> KnowledgeRetriever:
    """Hybrid by default; BM25 alone when embeddings are unavailable."""
    if hybrid:
        return HybridRetriever()
    return FTSRetriever()


def knowledge_stats() -> dict[str, Any]:
    from sqlalchemy import func, select

    from ..db.base import KnowledgeChunkRow, KnowledgeDocumentRow

    with session_scope() as s:
        docs = s.execute(select(func.count(KnowledgeDocumentRow.id))).scalar() or 0
        chunks = s.execute(select(func.count(KnowledgeChunkRow.id))).scalar() or 0
        by_cat = s.execute(
            select(KnowledgeDocumentRow.category, func.count(KnowledgeDocumentRow.id))
            .group_by(KnowledgeDocumentRow.category)
        ).all()
    from .embeddings import get_store

    return {
        "documents": docs,
        "chunks": chunks,
        "by_category": dict(by_cat),
        "fts_available": ensure_fts(),
        "embeddings": get_store().stats(),
    }
