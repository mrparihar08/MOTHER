from __future__ import annotations

import io
import re
import csv
import json
import logging
from typing import Any, Dict, List, Optional, Set
import numpy as np
from sqlalchemy.orm import Session

from backend.api.database import SessionLocal, engine, Base
from backend.api.models.vitya import RAGDocument, RAGDocumentChunk
from backend.api.services.gemini_service import get_gemini_client

logger = logging.getLogger(__name__)


def _ensure_rag_tables_exist() -> None:
    """Ensure RAG tables exist in persistent database storage."""
    try:
        Base.metadata.create_all(bind=engine, tables=[RAGDocument.__table__, RAGDocumentChunk.__table__], checkfirst=True)
    except Exception as exc:
        logger.debug("RAG tables creation check: %s", exc)


def is_binary_file(file_bytes: bytes) -> bool:
    """Detect if file bytes contain binary signatures (ZIP, ELF, EXE, etc.) or null bytes."""
    if not file_bytes:
        return False
    # Check for binary archive headers (ZIP / DOCX / XLSX: PK\x03\x04 or PK\x05\x06)
    if file_bytes.startswith(b"PK\x03\x04") or file_bytes.startswith(b"PK\x05\x06"):
        return True
    if file_bytes.startswith(b"\x7fELF") or file_bytes.startswith(b"MZ"):
        return True
    # Check for null bytes in initial sample
    if b"\x00" in file_bytes[:1024]:
        return True
    return False


def parse_txt(file_bytes: bytes) -> str:
    """Parse TXT or Markdown file content safely without decoding binary files."""
    if not file_bytes or is_binary_file(file_bytes):
        return ""
    try:
        return file_bytes.decode("utf-8")
    except Exception:
        try:
            return file_bytes.decode("latin-1")
        except Exception:
            return file_bytes.decode("utf-8", errors="ignore")


def parse_csv(file_bytes: bytes) -> str:
    """Parse CSV file content into readable structured rows."""
    text_content = parse_txt(file_bytes)
    lines = text_content.splitlines()
    if not lines:
        return ""

    reader = csv.reader(lines)
    output_lines = []
    headers = []
    
    for idx, row in enumerate(reader):
        if not row or not any(row):
            continue
        if idx == 0:
            headers = [h.strip() for h in row]
            output_lines.append(f"CSV Headers: {', '.join(headers)}")
        else:
            if headers:
                row_str = "; ".join(f"{h}: {val.strip()}" for h, val in zip(headers, row) if val.strip())
            else:
                row_str = ", ".join(val.strip() for val in row if val.strip())
            output_lines.append(f"Row {idx}: {row_str}")

    return "\n".join(output_lines)


def parse_docx(file_bytes: bytes) -> str:
    """Parse DOCX document text including headings, paragraphs, and tables safely."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        lines: List[str] = []
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                lines.append(t)
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("DOCX parsing failed: %s", exc)
        return ""


def parse_xlsx(file_bytes: bytes) -> str:
    """Parse XLSX / XLS / XLSM Excel sheets, rows, and cells into structured text."""
    # Attempt 1: openpyxl
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        lines: List[str] = []
        for sheetname in wb.sheetnames:
            ws = wb[sheetname]
            sheet_rows = []
            for row in ws.iter_rows(values_only=True):
                if any(v is not None and str(v).strip() for v in row):
                    row_vals = [str(v).strip() if v is not None else "" for v in row]
                    sheet_rows.append(", ".join(row_vals))
            if sheet_rows:
                lines.append(f"[Sheet: {sheetname}]")
                lines.extend(sheet_rows)
        if lines:
            return "\n".join(lines)
    except Exception as exc:
        logger.debug("openpyxl parsing failed: %s; trying pandas fallback", exc)

    # Attempt 2: pandas read_excel
    try:
        import pandas as pd
        excel_data = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
        lines = []
        for sheetname, df in excel_data.items():
            if not df.empty:
                lines.append(f"[Sheet: {sheetname}]")
                lines.append(df.to_string(index=False))
        if lines:
            return "\n".join(lines)
    except Exception as exc:
        logger.debug("pandas read_excel failed: %s", exc)

    return ""


def parse_pdf(file_bytes: bytes) -> str:
    """Parse PDF document text using pypdf or PyPDF2 with regex fallback."""
    text_parts = []

    # Attempt 1: pypdf
    try:
        # pyrefly: ignore [missing-import]
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        for page_num, page in enumerate(reader.pages, 1):
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(f"[Page {page_num}]\n{t.strip()}")
        if text_parts:
            return "\n\n".join(text_parts)
    except Exception as exc:
        logger.debug("pypdf extraction failed: %s", exc)

    # Attempt 2: PyPDF2
    try:
        # pyrefly: ignore [missing-import]
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        for page_num, page in enumerate(reader.pages, 1):
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(f"[Page {page_num}]\n{t.strip()}")
        if text_parts:
            return "\n\n".join(text_parts)
    except Exception as exc:
        logger.debug("PyPDF2 extraction failed: %s", exc)

    return ""


def extract_document_text(filename: str, file_bytes: bytes) -> str:
    """Detect file extension and extract text content safely."""
    fn_lower = filename.lower()
    if fn_lower.endswith(".pdf"):
        return parse_pdf(file_bytes)
    elif fn_lower.endswith(".csv"):
        return parse_csv(file_bytes)
    elif fn_lower.endswith(".docx") or fn_lower.endswith(".doc"):
        return parse_docx(file_bytes)
    elif fn_lower.endswith(".xlsx") or fn_lower.endswith(".xls") or fn_lower.endswith(".xlsm"):
        return parse_xlsx(file_bytes)
    else:
        # Prevent binary garbage (e.g. unknown .zip, .exe, or corrupted files) from being decoded as text
        if is_binary_file(file_bytes):
            logger.warning("Unsupported binary file format for document: %s", filename)
            return ""
        return parse_txt(file_bytes)


def tokenize(text: str) -> Set[str]:
    """Tokenize string into lowercase alphanumeric keyword set."""
    words = re.findall(r"\w+", (text or "").lower())
    # Filter common stop words
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "it", "this", "that"}
    return {w for w in words if len(w) > 1 and w not in stopwords}


def generate_embeddings(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate dense semantic vector embeddings for a list of text strings
    using Gemini text-embedding-004 model.
    """
    if not texts:
        return []

    client = get_gemini_client()
    if not client:
        return [None] * len(texts)

    results: List[Optional[List[float]]] = []
    batch_size = 16

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            res = client.models.embed_content(
                model="text-embedding-004",
                contents=batch,
            )
            if hasattr(res, "embeddings") and res.embeddings:
                for emb in res.embeddings:
                    results.append(list(emb.values) if hasattr(emb, "values") else None)
            else:
                results.extend([None] * len(batch))
        except Exception as exc:
            logger.warning("Gemini batch embed_content failed: %s; retrying individually", exc)
            for single_text in batch:
                try:
                    single_res = client.models.embed_content(
                        model="text-embedding-004",
                        contents=single_text,
                    )
                    if hasattr(single_res, "embeddings") and single_res.embeddings:
                        results.append(list(single_res.embeddings[0].values))
                    else:
                        results.append(None)
                except Exception as inner_exc:
                    logger.debug("Gemini individual embed_content failed: %s", inner_exc)
                    results.append(None)

    return results


def generate_single_embedding(text: str) -> Optional[List[float]]:
    """Generate dense semantic vector embedding for a single text query."""
    if not text or not text.strip():
        return None
    res = generate_embeddings([text.strip()])
    return res[0] if res else None


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors using numpy."""
    try:
        a = np.asarray(vec_a, dtype=np.float32)
        b = np.asarray(vec_b, dtype=np.float32)
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    except Exception:
        return 0.0


def chunk_text(text: str, filename: str, chunk_size: int = 700, overlap: int = 120) -> List[Dict[str, Any]]:
    """Chunk document text into overlapping segments with metadata."""
    text = (text or "").strip()
    if not text:
        return []

    chunks = []
    start = 0
    chunk_idx = 1

    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Adjust chunk boundary to complete sentence or newline if possible
        if end < len(text):
            sentence_end = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if sentence_end > start + 200:
                end = sentence_end + 1

        segment = text[start:end].strip()
        if segment:
            chunks.append({
                "chunk_id": f"{filename}_chunk_{chunk_idx}",
                "filename": filename,
                "chunk_index": chunk_idx,
                "text": segment,
                "tokens": tokenize(segment),
                "embedding": None,
            })
            chunk_idx += 1

        if end >= len(text):
            break

        start = max(start + 1, end - overlap)

    return chunks


class RAGStore:
    """
    Database-backed, multi-worker persistent vector and hybrid BM25 document store.
    Persists document chunks and vector embeddings across server restarts,
    while maintaining an in-memory acceleration cache.
    """

    def __init__(self) -> None:
        self._store: Dict[tuple[int, int], List[Dict[str, Any]]] = {}
        self._doc_meta: Dict[tuple[int, int], List[Dict[str, Any]]] = {}
        _ensure_rag_tables_exist()

    def _get_key(self, conversation_id: Optional[int], user_id: Optional[int] = None) -> tuple[int, int]:
        return (user_id or 0, conversation_id or 0)

    def _save_to_database(
        self,
        conversation_id: int,
        filename: str,
        char_count: int,
        chunks: List[Dict[str, Any]],
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> None:
        """Persist document metadata and all chunk embeddings to relational database."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            # Delete any existing document record with same filename for this user & conversation
            old_docs = (
                db.query(RAGDocument)
                .filter(
                    RAGDocument.user_id == user_id,
                    RAGDocument.conversation_id == conversation_id,
                    RAGDocument.filename == filename,
                )
                .all()
            )
            for od in old_docs:
                db.delete(od)
            db.flush()

            rag_doc = RAGDocument(
                user_id=user_id,
                conversation_id=conversation_id,
                filename=filename,
                char_count=char_count,
                chunk_count=len(chunks),
            )
            db.add(rag_doc)
            db.flush()

            for c in chunks:
                emb_json = json.dumps(c.get("embedding")) if c.get("embedding") is not None else None
                toks_json = json.dumps(list(c.get("tokens", [])))
                chunk_record = RAGDocumentChunk(
                    document_id=rag_doc.id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    filename=filename,
                    chunk_id=c.get("chunk_id", ""),
                    chunk_index=c.get("chunk_index", 0),
                    text=c.get("text", ""),
                    embedding_json=emb_json,
                    tokens_json=toks_json,
                )
                db.add(chunk_record)

            db.commit()
            logger.debug("Successfully persisted RAG document '%s' with %d chunks to DB", filename, len(chunks))
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to persist RAG document to database: %s", exc)
        finally:
            if close_db:
                db.close()

    def _load_chunks_from_database(
        self,
        conversation_id: int,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Load document chunks and vector embeddings from database into memory."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        chunks: List[Dict[str, Any]] = []
        try:
            records = (
                db.query(RAGDocumentChunk)
                .filter(
                    RAGDocumentChunk.user_id == user_id,
                    RAGDocumentChunk.conversation_id == conversation_id,
                )
                .order_by(RAGDocumentChunk.id.asc())
                .all()
            )
            for r in records:
                emb = json.loads(r.embedding_json) if r.embedding_json else None
                toks = set(json.loads(r.tokens_json)) if r.tokens_json else tokenize(r.text)
                chunks.append({
                    "chunk_id": r.chunk_id,
                    "filename": r.filename,
                    "chunk_index": r.chunk_index,
                    "text": r.text,
                    "tokens": toks,
                    "embedding": emb,
                })
        except Exception as exc:
            logger.warning("Failed to load RAG chunks from database: %s", exc)
        finally:
            if close_db:
                db.close()
        return chunks

    def _load_meta_from_database(
        self,
        conversation_id: int,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Load document metadata list from database."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        docs: List[Dict[str, Any]] = []
        try:
            records = (
                db.query(RAGDocument)
                .filter(
                    RAGDocument.user_id == user_id,
                    RAGDocument.conversation_id == conversation_id,
                )
                .all()
            )
            for r in records:
                docs.append({
                    "filename": r.filename,
                    "chunk_count": r.chunk_count,
                    "char_count": r.char_count,
                })
        except Exception as exc:
            logger.warning("Failed to load RAG metadata from database: %s", exc)
        finally:
            if close_db:
                db.close()
        return docs

    def index_document(
        self,
        conversation_id: int,
        filename: str,
        file_bytes: bytes,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        text = extract_document_text(filename, file_bytes)
        chunks = chunk_text(text, filename)
        key = self._get_key(conversation_id, user_id)

        # Generate dense semantic vector embeddings for all chunks in batch
        chunk_texts = [c["text"] for c in chunks]
        embeddings = generate_embeddings(chunk_texts)
        for c, emb in zip(chunks, embeddings):
            c["embedding"] = emb

        # 1. Persist directly to DB (so data survives restarts & multi-workers)
        self._save_to_database(conversation_id, filename, len(text), chunks, user_id=user_id, db=db)

        # 2. Update local in-memory cache
        if key not in self._store:
            self._store[key] = []
            self._doc_meta[key] = []

        self._store[key] = [c for c in self._store[key] if c["filename"] != filename]
        self._doc_meta[key] = [d for d in self._doc_meta[key] if d["filename"] != filename]

        self._store[key].extend(chunks)
        doc_info = {
            "filename": filename,
            "chunk_count": len(chunks),
            "char_count": len(text),
            "has_embeddings": any(c.get("embedding") is not None for c in chunks),
        }
        self._doc_meta[key].append(doc_info)

        logger.info(
            "Indexed & persisted document '%s' for user %s, conv %s: %d chunks (embeddings=%s)",
            filename,
            user_id,
            conversation_id,
            len(chunks),
            doc_info["has_embeddings"],
        )
        return doc_info

    def get_documents(
        self,
        conversation_id: int,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        key = self._get_key(conversation_id, user_id)
        if key in self._doc_meta and self._doc_meta[key]:
            return self._doc_meta[key]

        # Load from DB if memory cache is clean (e.g. post restart or different worker)
        db_docs = self._load_meta_from_database(conversation_id, user_id, db=db)
        if db_docs:
            self._doc_meta[key] = db_docs
        return db_docs

    def clear_documents(
        self,
        conversation_id: int,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> bool:
        key = self._get_key(conversation_id, user_id)
        if key in self._store:
            del self._store[key]
        if key in self._doc_meta:
            del self._doc_meta[key]

        # Delete from persistent database
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            docs = (
                db.query(RAGDocument)
                .filter(
                    RAGDocument.user_id == user_id,
                    RAGDocument.conversation_id == conversation_id,
                )
                .all()
            )
            for d in docs:
                db.delete(d)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to delete RAG documents from DB: %s", exc)
        finally:
            if close_db:
                db.close()
        return True

    def search(
        self,
        conversation_id: int,
        query: str,
        top_k: int = 4,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid Semantic Search:
        Combines Dense Vector Cosine Similarity (via Gemini text-embedding-004)
        with Keyword/Jaccard token matching, backed by persistent DB storage.
        """
        key = self._get_key(conversation_id, user_id)
        chunks = self._store.get(key)
        if chunks is None:
            # Cold cache or new worker: load from database
            chunks = self._load_chunks_from_database(conversation_id, user_id, db=db)
            self._store[key] = chunks

        # Fall back to user's general documents (cid=0) if searching a specific conversation
        if not chunks and (conversation_id or 0) != 0 and user_id:
            chunks = self._store.get((user_id, 0))
            if chunks is None:
                chunks = self._load_chunks_from_database(0, user_id, db=db)
                self._store[(user_id, 0)] = chunks

        if not chunks or not query.strip():
            return []

        # Generate query embedding for dense vector search
        query_embedding = generate_single_embedding(query)
        query_tokens = tokenize(query)

        scored_chunks = []
        for c in chunks:
            chunk_embedding = c.get("embedding")
            dense_sim = 0.0
            if query_embedding is not None and chunk_embedding is not None:
                dense_sim = compute_cosine_similarity(query_embedding, chunk_embedding)

            # Keyword Jaccard matching
            jaccard_score = 0.0
            if query_tokens:
                intersection = query_tokens.intersection(c.get("tokens", set()))
                if intersection:
                    jaccard_score = len(intersection) / float(
                        len(query_tokens) + len(c.get("tokens", set())) - len(intersection) + 1e-5
                    )
                    # Substring boost
                    for q_tok in query_tokens:
                        if q_tok in c["text"].lower():
                            jaccard_score += 0.25

            # Hybrid score formulation:
            # 75% semantic vector similarity + 25% keyword match
            if query_embedding is not None and chunk_embedding is not None:
                final_score = (0.75 * dense_sim) + (0.25 * min(1.0, jaccard_score))
            else:
                final_score = jaccard_score

            # Filter out chunks with zero or negligible relevance
            if final_score > 0.05:
                scored_chunks.append((final_score, c))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_chunks[:top_k]]


rag_store = RAGStore()


def format_rag_context(query: str, chunks: List[Dict[str, Any]]) -> str:
    """Format top retrieved document chunks into LLM prompt context."""
    if not chunks:
        return ""

    lines = [
        f'📑 MULTI-DOCUMENT RAG CONTEXT FOR USER QUESTION: "{query}"',
        "The user has uploaded source documents. Use these authoritative document passages to answer accurately and specify exact facts, figures, or metrics:\n",
    ]

    for idx, c in enumerate(chunks, 1):
        lines.append(f"Passage {idx} [Document: {c['filename']}]")
        lines.append(f'"{c["text"]}"\n')

    return "\n".join(lines)
