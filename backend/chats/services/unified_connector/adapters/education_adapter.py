from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.chats.services.unified_connector.models import (
    EducationMetadata,
    ResultCategory,
    StandardizedResult,
)
from backend.chats.services.web_search_service import perform_web_search

logger = logging.getLogger(__name__)

# Directory of verified official documentation & educational hubs
DOCUMENTATION_DIRECTORIES = {
    "fastapi": {
        "title": "FastAPI Official Documentation & Tutorial",
        "url": "https://fastapi.tiangolo.com/tutorial/",
        "platform": "FastAPI Docs",
        "description": "Official interactive documentation for FastAPI covering routing, dependency injection, OAuth2 security, and Pydantic models.",
        "difficulty": "Beginner to Advanced",
        "resource_type": "Documentation",
    },
    "python": {
        "title": "Python 3 Official Documentation & Tutorial",
        "url": "https://docs.python.org/3/tutorial/",
        "platform": "Python Software Foundation",
        "description": "Comprehensive official Python tutorial and standard library reference from python.org.",
        "difficulty": "Beginner to Advanced",
        "resource_type": "Documentation",
    },
    "mdn": {
        "title": "MDN Web Docs (Mozilla Developer Network)",
        "url": "https://developer.mozilla.org/",
        "platform": "Mozilla Developer Network",
        "description": "Authoritative open web standards documentation for JavaScript, HTML, CSS, and modern Web APIs.",
        "difficulty": "All Levels",
        "resource_type": "Reference & Tutorial",
    },
    "react": {
        "title": "React.dev Official Documentation",
        "url": "https://react.dev/learn",
        "platform": "React Docs",
        "description": "Modern React guides covering components, state, hooks, and best practices.",
        "difficulty": "Beginner to Intermediate",
        "resource_type": "Documentation",
    },
    "freecodecamp": {
        "title": "freeCodeCamp Open Curriculum",
        "url": "https://www.freecodecamp.org/learn",
        "platform": "freeCodeCamp",
        "description": "100% free verified certifications for Web Development, Python, Machine Learning, and Data Analysis.",
        "difficulty": "Beginner to Intermediate",
        "resource_type": "Interactive Course",
    },
    "mit": {
        "title": "MIT OpenCourseWare (Free Course Materials)",
        "url": "https://ocw.mit.edu/",
        "platform": "MIT OpenCourseWare",
        "description": "Freely available educational materials from thousands of MIT undergraduate and graduate courses.",
        "difficulty": "College / University Level",
        "resource_type": "Course Materials",
    },
}


def fetch_education_resources(query: str, limit: int = 4) -> List[StandardizedResult]:
    """
    Search educational tutorials, free courses, and official programming documentation.
    """
    clean_q = (query or "").strip().lower()
    if not clean_q:
        return []

    results: List[StandardizedResult] = []

    # Check for direct matches in authoritative doc directories
    for key, item in DOCUMENTATION_DIRECTORIES.items():
        if key in clean_q or any(token in clean_q for token in key.split()):
            results.append(
                StandardizedResult(
                    id=f"edu_dir_{key}",
                    category=ResultCategory.EDUCATION,
                    title=item["title"],
                    description=item["description"],
                    source=item["platform"],
                    source_domain=item["url"].split("/")[2],
                    url=item["url"],
                    attribution="Open Technical Documentation / Educational Resources",
                    education=EducationMetadata(
                        platform=item["platform"],
                        difficulty=item["difficulty"],
                        is_free=True,
                        resource_type=item["resource_type"],
                    ),
                )
            )

    # Perform targeted search for online courses & documentation
    try:
        search_query = f"{clean_q} official tutorial documentation course free"
        web_hits = perform_web_search(search_query, max_results=5)
        for idx, hit in enumerate(web_hits):
            url = hit.get("url", "")
            title = hit.get("title", "")
            snip = hit.get("snippet", "")

            # Filter educational domains
            domain = url.split("/")[2] if "//" in url else "web"
            is_edu_domain = any(ed in url for ed in [
                "docs.python.org", "fastapi.tiangolo.com", "developer.mozilla.org",
                "freecodecamp.org", "coursera.org", "edx.org", "ocw.mit.edu",
                "w3schools.com", "geeksforgeeks.org", "khanacademy.org"
            ])

            platform_name = "Technical Learning"
            if "fastapi.tiangolo.com" in url:
                platform_name = "FastAPI Official"
            elif "docs.python.org" in url:
                platform_name = "Python.org"
            elif "developer.mozilla.org" in url:
                platform_name = "MDN Web Docs"
            elif "freecodecamp.org" in url:
                platform_name = "freeCodeCamp"
            elif "coursera.org" in url:
                platform_name = "Coursera"
            elif "ocw.mit.edu" in url:
                platform_name = "MIT OpenCourseWare"

            results.append(
                StandardizedResult(
                    id=f"edu_web_{idx}_{hash(url) % 100000}",
                    category=ResultCategory.EDUCATION,
                    title=title,
                    description=snip,
                    source=platform_name,
                    source_domain=domain,
                    url=url,
                    attribution=f"Educational resource from {platform_name}",
                    education=EducationMetadata(
                        platform=platform_name,
                        difficulty="All Levels",
                        is_free=True,
                        resource_type="Course / Tutorial" if "course" in clean_q else "Documentation",
                    ),
                )
            )
    except Exception as exc:
        logger.warning("Education search exception: %s", exc)

    # Deduplicate results by URL
    seen_urls = set()
    deduped = []
    for r in results:
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            deduped.append(r)

    return deduped[:limit]
