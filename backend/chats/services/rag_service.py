from __future__ import annotations

import io
import re
import csv
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def parse_txt(file_bytes: bytes) -> str:
    """Parse TXT or Markdown file content."""
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


def parse_pdf(file_bytes: bytes) -> str:
    """Parse PDF document text using pypdf or PyPDF2 with regex fallback."""
    text_parts = []

    # Attempt 1: pypdf
    try:
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

    # Fallback: Plain text regex stream extraction
    try:
        raw_str = file_bytes.decode("latin-1", errors="ignore")
        text_matches = re.findall(r"\((.*?)\)\s*Tj", raw_str)
        if text_matches:
            cleaned = " ".join(text_matches)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                return cleaned
    except Exception:
        pass

    return parse_txt(file_bytes)


def extract_document_text(filename: str, file_bytes: bytes) -> str:
    """Detect file extension and extract text content."""
    fn_lower = filename.lower()
    if fn_lower.endswith(".pdf"):
        return parse_pdf(file_bytes)
    elif fn_lower.endswith(".csv"):
        return parse_csv(file_bytes)
    else:
        return parse_txt(file_bytes)


def tokenize(text: str) -> Set[str]:
    """Tokenize string into lowercase alphanumeric keyword set."""
    words = re.findall(r"\w+", (text or "").lower())
    # Filter common stop words
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "it", "this", "that"}
    return {w for w in words if len(w) > 1 and w not in stopwords}


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
            })
            chunk_idx += 1

        if end >= len(text):
            break

        start = max(start + 1, end - overlap)

    return chunks


class RAGStore:
    """In-memory user- and conversation-scoped vector/BM25 document index."""

    def __init__(self) -> None:
        # Map (user_id, conversation_id) -> list of document chunk dicts
        self._store: Dict[tuple[int, int], List[Dict[str, Any]]] = {}
        # Map (user_id, conversation_id) -> list of active filenames
        self._doc_meta: Dict[tuple[int, int], List[Dict[str, Any]]] = {}

    def _get_key(self, conversation_id: Optional[int], user_id: Optional[int] = None) -> tuple[int, int]:
        return (user_id or 0, conversation_id or 0)

    def index_document(
        self,
        conversation_id: int,
        filename: str,
        file_bytes: bytes,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        text = extract_document_text(filename, file_bytes)
        chunks = chunk_text(text, filename)
        key = self._get_key(conversation_id, user_id)

        if key not in self._store:
            self._store[key] = []
            self._doc_meta[key] = []

        # Remove previous chunks of the same filename if re-uploaded
        self._store[key] = [c for c in self._store[key] if c["filename"] != filename]
        self._doc_meta[key] = [d for d in self._doc_meta[key] if d["filename"] != filename]

        self._store[key].extend(chunks)
        doc_info = {
            "filename": filename,
            "chunk_count": len(chunks),
            "char_count": len(text),
        }
        self._doc_meta[key].append(doc_info)

        logger.info("Indexed document '%s' for user %s, conversation %s: %d chunks", filename, user_id, conversation_id, len(chunks))
        return doc_info

    def get_documents(self, conversation_id: int, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        key = self._get_key(conversation_id, user_id)
        return self._doc_meta.get(key, [])

    def clear_documents(self, conversation_id: int, user_id: Optional[int] = None) -> bool:
        key = self._get_key(conversation_id, user_id)
        if key in self._store:
            del self._store[key]
        if key in self._doc_meta:
            del self._doc_meta[key]
        return True

    def search(
        self,
        conversation_id: int,
        query: str,
        top_k: int = 4,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        key = self._get_key(conversation_id, user_id)
        chunks = self._store.get(key, [])
        # Fall back to user's general documents (cid=0) if searching a specific conversation
        if not chunks and (conversation_id or 0) != 0 and user_id:
            chunks = self._store.get((user_id, 0), [])

        if not chunks or not query.strip():
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored_chunks = []
        for c in chunks:
            intersection = query_tokens.intersection(c["tokens"])
            if not intersection:
                continue

            # Compute BM25/Jaccard similarity score
            score = len(intersection) / float(len(query_tokens) + len(c["tokens"]) - len(intersection) + 1e-5)
            # Boost score for exact keyword string match
            for q_tok in query_tokens:
                if q_tok in c["text"].lower():
                    score += 0.25

            scored_chunks.append((score, c))

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
