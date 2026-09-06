"""Ingestion of personal documents: TXT, MD, PDF.

These are a source of KNOWLEDGE, never a source of real-time DATA. They are
written to `knowledge_chunks`, never to `observations` - the schema itself
enforces the separation the brief asks for.

A course explains what an RSI divergence means; the market data says whether
one is happening right now. The analyst layer joins the two and cites the
passage it used.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..db.base import KnowledgeChunkRow, KnowledgeDocumentRow
from ..db.session import session_scope
from ..logging_setup import get_logger
from ..settings import get_settings
from .store import clear_document_index, index_chunks

log = get_logger("knowledge.ingest")

SUPPORTED = {".txt", ".md", ".markdown", ".pdf"}
CHUNK_SIZE = 1100
CHUNK_OVERLAP = 180


@dataclass(slots=True)
class Chunk:
    text: str
    page: int | None
    index: int


def extract_text(path: Path) -> list[tuple[str, int | None]]:
    """Return (text, page) segments. Page is None for non-paginated formats."""
    suffix = path.suffix.lower()

    if suffix in (".txt", ".md", ".markdown"):
        try:
            return [(path.read_text(encoding="utf-8", errors="replace"), None)]
        except OSError as exc:
            log.warning("read_failed", path=str(path), error=str(exc))
            return []

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            out: list[tuple[str, int | None]] = []
            for page_no, page in enumerate(reader.pages, start=1):
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    continue
                if txt.strip():
                    out.append((txt, page_no))
            return out
        except Exception as exc:
            log.warning("pdf_read_failed", path=str(path), error=str(exc))
            return []

    return []


def clean_text(raw: str) -> str:
    raw = raw.replace("\x00", " ")
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def chunk_text(segments: list[tuple[str, int | None]]) -> list[Chunk]:
    """Split on paragraph boundaries with overlap, preserving the page number.

    Paragraph-aware splitting keeps an explanation intact instead of cutting it
    mid-sentence, which matters when the passage is later quoted in a report.
    """
    chunks: list[Chunk] = []
    index = 0

    for raw, page in segments:
        text = clean_text(raw)
        if not text:
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        buffer = ""

        for para in paragraphs:
            if len(buffer) + len(para) + 2 <= CHUNK_SIZE:
                buffer = f"{buffer}\n\n{para}" if buffer else para
                continue
            if buffer:
                chunks.append(Chunk(text=buffer, page=page, index=index))
                index += 1
                tail = buffer[-CHUNK_OVERLAP:]
                buffer = f"{tail}\n\n{para}" if len(para) < CHUNK_SIZE else para
            else:
                # A single oversized paragraph: hard-split it with overlap.
                for start in range(0, len(para), CHUNK_SIZE - CHUNK_OVERLAP):
                    piece = para[start : start + CHUNK_SIZE]
                    if piece.strip():
                        chunks.append(Chunk(text=piece, page=page, index=index))
                        index += 1
                buffer = ""

        if buffer.strip():
            chunks.append(Chunk(text=buffer, page=page, index=index))
            index += 1

    return chunks


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:32]


def ingest_file(path: Path, category: str | None = None) -> dict[str, Any]:
    if path.suffix.lower() not in SUPPORTED:
        return {"path": str(path), "status": "skipped", "reason": f"unsupported {path.suffix}"}

    settings = get_settings()
    try:
        rel = path.relative_to(settings.knowledge_dir)
        cat = category or (rel.parts[0] if len(rel.parts) > 1 else "general")
    except ValueError:
        cat = category or "general"

    doc_hash = file_hash(path)
    doc_id = "doc_" + hashlib.sha1(str(path).encode()).hexdigest()[:16]

    with session_scope() as s:
        existing = s.get(KnowledgeDocumentRow, doc_id)
        if existing and existing.content_hash == doc_hash:
            return {"path": str(path), "status": "unchanged", "chunks": existing.chunk_count}

    segments = extract_text(path)
    if not segments:
        return {"path": str(path), "status": "error", "reason": "no extractable text"}

    chunks = chunk_text(segments)
    if not chunks:
        return {"path": str(path), "status": "error", "reason": "no chunks produced"}

    title = path.stem.replace("_", " ").replace("-", " ").strip()
    pages = max((c.page for c in chunks if c.page), default=None)

    rows: list[dict[str, Any]] = []
    for c in chunks:
        cid = "chk_" + hashlib.sha1(f"{doc_id}:{c.index}".encode()).hexdigest()[:16]
        rows.append({
            "id": cid, "document_id": doc_id, "document_title": title, "category": cat,
            "page": c.page, "chunk_index": c.index, "text": c.text, "char_count": len(c.text),
        })

    with session_scope() as s:
        old = s.execute(
            select(KnowledgeChunkRow).where(KnowledgeChunkRow.document_id == doc_id)
        ).scalars().all()
        old_ids = [o.id for o in old]
        for o in old:
            s.delete(o)
        s.flush()

        existing = s.get(KnowledgeDocumentRow, doc_id)
        if existing:
            existing.content_hash = doc_hash
            existing.chunk_count = len(rows)
            existing.pages = pages
            existing.title = title
            existing.category = cat
        else:
            s.add(KnowledgeDocumentRow(
                id=doc_id, path=str(path), title=title, category=cat,
                file_type=path.suffix.lower().lstrip("."), content_hash=doc_hash,
                pages=pages, chunk_count=len(rows),
            ))
        for r in rows:
            s.add(KnowledgeChunkRow(**r))

    clear_document_index(doc_id, old_ids)
    index_chunks(rows)

    # Vector index alongside the lexical one. Failure here must not break
    # ingestion - BM25 still works without embeddings.
    embedded = 0
    try:
        from .embeddings import get_store

        store = get_store()
        if old_ids:
            store.remove(old_ids)
        embedded = store.add(rows)
    except Exception as exc:
        log.info("embedding_skipped", path=str(path), error=str(exc)[:150])

    return {
        "path": str(path), "status": "ingested", "chunks": len(rows),
        "pages": pages, "category": cat, "title": title,
        "embedded": embedded,
    }


def ingest_directory(directory: Path | None = None) -> dict[str, Any]:
    """Walk knowledge/ and ingest everything supported."""
    root = directory or get_settings().knowledge_dir
    if not root.exists():
        return {"status": "error", "reason": f"directory not found: {root}", "files": []}

    results: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED:
            try:
                results.append(ingest_file(path))
            except Exception as exc:
                log.warning("ingest_failed", path=str(path), error=str(exc))
                results.append({"path": str(path), "status": "error", "reason": str(exc)})

    ingested = [r for r in results if r["status"] == "ingested"]
    return {
        "status": "ok",
        "files_processed": len(results),
        "files_ingested": len(ingested),
        "chunks_created": sum(r.get("chunks", 0) for r in ingested),
        "files": results,
    }


def reindex_embeddings() -> dict[str, Any]:
    """Build vectors for chunks that have none.

    Needed when embeddings are enabled after documents were already ingested -
    without this, older documents would stay searchable by BM25 only.
    """
    from sqlalchemy import select

    from ..db.base import KnowledgeChunkRow
    from .embeddings import embeddings_available, get_store

    if not embeddings_available():
        return {
            "status": "unavailable",
            "reason": (
                "The local embedding model could not be loaded. Knowledge search "
                "continues to work using BM25 alone."
            ),
            "embedded": 0,
        }

    store = get_store()
    already = store.indexed_ids()

    with session_scope() as s:
        rows = s.execute(select(KnowledgeChunkRow)).scalars().all()
        pending = [
            {
                "id": r.id, "text": r.text, "document_title": r.document_title,
                "category": r.category, "page": r.page,
            }
            for r in rows if r.id not in already
        ]

    embedded = store.add(pending) if pending else 0
    return {
        "status": "ok",
        "chunks_total": len(already) + embedded,
        "embedded": embedded,
        "already_indexed": len(already),
        "stats": store.stats(),
    }
