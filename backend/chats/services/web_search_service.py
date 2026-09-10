from __future__ import annotations

import re
import urllib.parse
import urllib.request
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def clean_html_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"&quot;", '"', cleaned)
    cleaned = re.sub(r"&amp;", "&", cleaned)
    cleaned = re.sub(r"&lt;", "<", cleaned)
    cleaned = re.sub(r"&gt;", ">", cleaned)
    cleaned = re.sub(r"&#39;", "'", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def perform_web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Perform a real-time web search using DuckDuckGo (HTML / Instant Answer API)
    with zero external API keys required.
    Returns list of dicts: [{"title": ..., "snippet": ..., "url": ...}]
    """
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return []

    results: List[Dict[str, str]] = []

    # Method 1: DuckDuckGo HTML Search
    try:
        encoded_query = urllib.parse.urlencode({"q": cleaned_query})
        url = f"https://html.duckduckgo.com/html/?{encoded_query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        with urllib.request.urlopen(req, timeout=6) as response:
            html_content = response.read().decode("utf-8", errors="ignore")

        # Parse DuckDuckGo HTML results using regex pattern matching
        matches = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>)',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )

        for href, title, snip1, snip2 in matches[:max_results]:
            final_url = href
            if "uddg=" in href:
                parsed_params = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if "uddg" in parsed_params and parsed_params["uddg"]:
                    final_url = parsed_params["uddg"][0]

            clean_t = clean_html_tags(title)
            clean_s = clean_html_tags(snip1 or snip2 or "")

            if clean_t and (clean_s or final_url):
                results.append(
                    {
                        "title": clean_t,
                        "snippet": clean_s or clean_t,
                        "url": final_url,
                    }
                )

        if results:
            logger.info("DuckDuckGo HTML search fetched %d live results for '%s'", len(results), cleaned_query)
            return results
    except Exception as exc:
        logger.warning("DuckDuckGo HTML search failed: %s", exc)

    # Method 2: Fallback to DuckDuckGo Instant Answer API
    try:
        encoded_query = urllib.parse.quote_plus(cleaned_query)
        api_url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&no_redirect=1"
        req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})

        with urllib.request.urlopen(req, timeout=5) as response:
            import json
            data = json.loads(response.read().decode("utf-8"))

        abstract = data.get("AbstractText") or data.get("Definition")
        heading = data.get("Heading") or cleaned_query
        abstract_url = data.get("AbstractURL") or ""

        if abstract:
            results.append(
                {
                    "title": heading,
                    "snippet": abstract,
                    "url": abstract_url,
                }
            )

        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(
                    {
                        "title": topic.get("Text")[:60] + "...",
                        "snippet": topic.get("Text"),
                        "url": topic.get("FirstURL") or "",
                    }
                )

        if results:
            logger.info("DuckDuckGo Instant Answer API fetched %d results", len(results))
            return results[:max_results]
    except Exception as exc:
        logger.warning("DuckDuckGo Instant Answer API failed: %s", exc)

    return results


def format_web_search_context(query: str, results: List[Dict[str, str]]) -> str:
    if not results:
        return ""

    lines = [f'🌐 LIVE REAL-TIME WEB SEARCH RESULTS FOR: "{query}"']
    lines.append("Use these real-time web facts, current data points, and sources to answer accurately:\n")

    for idx, item in enumerate(results, 1):
        lines.append(f"{idx}. Title: {item.get('title', 'Web Result')}")
        lines.append(f"   Snippet: {item.get('snippet', '')}")
        if item.get("url"):
            lines.append(f"   Source URL: {item.get('url')}")
        lines.append("")

    return "\n".join(lines)
