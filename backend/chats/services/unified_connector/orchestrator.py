from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.chats.services.unified_connector.cache import connector_cache
from backend.chats.services.unified_connector.models import (
    ResultCategory,
    StandardizedResult,
)
from backend.chats.services.unified_connector.adapters.shopping_adapter import fetch_shopping_results
from backend.chats.services.unified_connector.adapters.research_adapter import fetch_research_papers
from backend.chats.services.unified_connector.adapters.education_adapter import fetch_education_resources
from backend.chats.services.unified_connector.adapters.government_adapter import fetch_government_data

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Tracks configured external sources and their availability."""

    @staticmethod
    def get_supported_sources() -> Dict[str, Any]:
        return {
            "news": ["NewsAPI", "Mediastack", "Currents", "Verified Web Fallback"],
            "shopping": ["Amazon India (PA-API / Affiliate)", "Flipkart (Affiliate Search)"],
            "education": ["FastAPI Official Docs", "Python.org", "MDN Web Docs", "MIT OCW", "freeCodeCamp"],
            "research": ["arXiv.org Open Access API", "CrossRef / Open Repositories"],
            "government": ["Data.gov.in (OGD India)", "World Bank Open Data API", "Data.gov"],
            "web": ["DuckDuckGo Live Search / Instant Answers"],
        }


class SearchOrchestrator:
    """
    Central search coordinator:
    Dispatches requests to appropriate adapters, handles caching, deduplication,
    and returns verified StandardizedResult objects.
    """

    def __init__(self) -> None:
        self.cache = connector_cache

    def search(
        self,
        category: ResultCategory,
        query: str,
        limit: int = 4,
        force_refresh: bool = False,
    ) -> List[StandardizedResult]:
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        # Check cache
        if not force_refresh:
            cached = self.cache.get(category, clean_q, limit=limit)
            if cached:
                logger.info("Serving %d cached results for category '%s'", len(cached), category.value)
                return cached

        results: List[StandardizedResult] = []

        if category == ResultCategory.SHOPPING:
            results = fetch_shopping_results(clean_q, limit=limit)
        elif category == ResultCategory.RESEARCH:
            results = fetch_research_papers(clean_q, limit=limit)
        elif category == ResultCategory.EDUCATION:
            results = fetch_education_resources(clean_q, limit=limit)
        elif category == ResultCategory.GOVERNMENT:
            results = fetch_government_data(clean_q, limit=limit)
        elif category == ResultCategory.NEWS:
            from backend.chats.services.news_service import fetch_news
            raw_news = fetch_news(q=clean_q, limit=limit)
            for idx, a in enumerate(raw_news):
                results.append(
                    StandardizedResult(
                        id=f"news_{idx}_{hash(a.get('url', '')) % 100000}",
                        category=ResultCategory.NEWS,
                        title=a.get("title") or "News Headline",
                        description=a.get("description") or "",
                        source=a.get("source") or "Verified News",
                        source_domain=a.get("url", "").split("/")[2] if "//" in a.get("url", "") else "news",
                        url=a.get("url") or "#",
                        image=a.get("image"),
                        published_at=a.get("publishedAt"),
                        attribution=f"News via {a.get('provider', 'news')}",
                    )
                )
        elif category == ResultCategory.WEB_SEARCH:
            from backend.chats.services.web_search_service import perform_web_search
            raw_web = perform_web_search(clean_q, max_results=limit)
            for idx, w in enumerate(raw_web):
                url = w.get("url", "")
                domain = url.split("/")[2] if "//" in url else "web"
                results.append(
                    StandardizedResult(
                        id=f"web_{idx}_{hash(url) % 100000}",
                        category=ResultCategory.WEB_SEARCH,
                        title=w.get("title") or "Web Result",
                        description=w.get("snippet") or "",
                        source=domain,
                        source_domain=domain,
                        url=url,
                        attribution="Web Search Index",
                    )
                )

        if results:
            self.cache.set(category, clean_q, results, limit=limit)

        return results

    def summarize_results(
        self,
        results: List[StandardizedResult],
        user_query: str,
        category: ResultCategory,
    ) -> str:
        """
        Grounded summarization using the Gemini LLM service.
        Constrains output strictly to facts, specifications, and links from retrieved results.
        """
        if not results:
            return "Koi data nahi mila."

        blocks = []
        for i, r in enumerate(results[:4], 1):
            detail_line = ""
            if r.shopping and r.shopping.price:
                detail_line = f"Price: ₹{r.shopping.price:,.2f} on {r.shopping.store}"
            elif r.academic:
                authors_str = ", ".join(r.academic.authors) if r.academic.authors else "Authors"
                detail_line = f"Authors: {authors_str} | Year: {r.academic.year or 'Recent'}"
            elif r.education:
                detail_line = f"Platform: {r.education.platform} | Free: {r.education.is_free}"
            elif r.government and r.government.portal:
                detail_line = f"Portal: {r.government.portal} | License: {r.government.license_name}"

            blocks.append(
                f"Source {i}: {r.title}\n"
                f"- Details: {r.description}\n"
                f"- Link: {r.url}\n"
                f"- Metadata: {detail_line}\n"
            )

        context_str = "\n".join(blocks)

        system_instruction = (
            "You are Vitya AI Universal Information Analyst.\n"
            "Explain the retrieved sources to the user in a natural, empathetic, and clear Hinglish/English tone.\n\n"
            "STRICT GUIDELINES:\n"
            "1. ONLY use the verified facts, prices, links, and information present in the sources above. Never hallucinate specs or false discounts.\n"
            "2. For Shopping: Highlight price comparisons, merchant names (Amazon vs Flipkart), and buying options with Markdown links.\n"
            "3. For Education: Recommend the best learning pathway and highlight official documentation or free certifications.\n"
            "4. For Research: Clearly explain the core finding/methodology and provide the direct paper/PDF link.\n"
            "5. For Government Data: State the recorded metrics, year of observation, and official data license.\n"
            "6. Use bullet points and bold highlights for readability."
        )

        prompt = f"User Query: {user_query}\n\nRetrieved Data Sources:\n{context_str}"

        try:
            from backend.chats.services.gemini_service import generate_response
            reply = generate_response(prompt, system_instruction=system_instruction)
            if reply and not reply.startswith("Gemini error") and "not configured" not in reply.lower():
                return reply
        except Exception as exc:
            logger.warning("LLM summarization exception: %s", exc)

        # Fallback structured markdown
        fallback = [f"📊 **Verified Results for '{user_query}':**\n"]
        for r in results[:3]:
            fallback.append(f"• **[{r.title}]({r.url})** ({r.source})\n  {r.description}\n")
        return "\n".join(fallback)


orchestrator = SearchOrchestrator()
