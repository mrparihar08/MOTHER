from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
import requests

from backend.chats.services.unified_connector.models import (
    AcademicMetadata,
    ResultCategory,
    StandardizedResult,
)
from backend.chats.services.unified_connector.security import is_safe_url

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
REQUEST_TIMEOUT = 8.0


def fetch_research_papers(query: str, limit: int = 4) -> List[StandardizedResult]:
    """
    Search official open-access academic research papers from arXiv.org API.
    Provides authors, publication date, abstract, and direct PDF download link.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    # Strip conversational keywords
    clean_q = re.sub(r"(?i)\b(research\s+papers?|academic\s+papers?|papers?|find|dikhao|batao|search|latest)\b", " ", clean_q)
    clean_q = re.sub(r"\s+", " ", clean_q).strip() or query.strip()

    results: List[StandardizedResult] = []

    try:
        params = {
            "search_query": f"all:{clean_q}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        resp = requests.get(ARXIV_API_URL, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            # Parse Atom XML
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

            entries = root.findall("atom:entry", ns)
            for idx, entry in enumerate(entries):
                title_elem = entry.find("atom:title", ns)
                title = (title_elem.text if title_elem is not None and title_elem.text else "Research Paper").strip()
                title = re.sub(r"\s+", " ", title)

                summary_elem = entry.find("atom:summary", ns)
                summary = (summary_elem.text if summary_elem is not None and summary_elem.text else "").strip()
                summary = re.sub(r"\s+", " ", summary)
                if len(summary) > 280:
                    summary = summary[:277] + "..."

                id_elem = entry.find("atom:id", ns)
                paper_url = (id_elem.text if id_elem is not None and id_elem.text else "").strip()

                published_elem = entry.find("atom:published", ns)
                published = (published_elem.text if published_elem is not None and published_elem.text else "").strip()
                year = int(published[:4]) if published and len(published) >= 4 and published[:4].isdigit() else None

                # Extract authors
                authors = []
                for author_elem in entry.findall("atom:author", ns):
                    name_elem = author_elem.find("atom:name", ns)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())

                # Find PDF link
                pdf_url = None
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                        pdf_url = link.get("href")
                        break

                if not pdf_url and paper_url:
                    pdf_url = paper_url.replace("/abs/", "/pdf/") + ".pdf"

                results.append(
                    StandardizedResult(
                        id=f"arxiv_{idx}_{hash(paper_url) % 100000}",
                        category=ResultCategory.RESEARCH,
                        title=title,
                        description=summary,
                        source="arXiv.org (Open Access)",
                        source_domain="arxiv.org",
                        url=paper_url,
                        published_at=published,
                        attribution="Cornell University / arXiv Open Access Repository",
                        academic=AcademicMetadata(
                            authors=authors[:4],
                            journal_or_venue="arXiv Preprint",
                            pdf_url=pdf_url,
                            year=year,
                            open_access=True,
                        ),
                    )
                )

    except Exception as exc:
        logger.warning("arXiv search exception: %s", exc)

    return results[:limit]
