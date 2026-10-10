import pytest
from unittest.mock import MagicMock, patch

from backend.chats.utils.intent_router import classify_intent, Intent
from backend.chats.services.news_service import (
    extract_news_query,
    detect_news_category,
    detect_news_country,
    is_news_summary_query,
    _deduplicate_articles,
    _normalize_common_article,
    summarize_news_articles,
    fetch_news,
    _NEWS_CACHE,
)
from backend.chats.handlers.news_handler import handle_news_request


class TestNewsIntentClassification:
    """Verify that intent routing distinguishes news queries from greetings and normal Q&A."""

    def test_greeting_is_not_news(self):
        assert classify_intent("Hi") == Intent.GREETING
        assert classify_intent("hello") == Intent.GREETING
        assert classify_intent("namaste vitya") == Intent.GREETING

    def test_general_question_is_not_news(self):
        assert classify_intent("Python kya hai?") == Intent.GENERAL_KNOWLEDGE
        assert classify_intent("What is photosynthesis?") == Intent.GENERAL_KNOWLEDGE
        assert classify_intent("2 + 2 kitna hota hai") == Intent.GENERAL_KNOWLEDGE

    def test_fresh_news_intent_detection(self):
        assert classify_intent("Aaj ki latest news batao") == Intent.NEWS
        assert classify_intent("Latest Python news batao") == Intent.NEWS
        assert classify_intent("India ki top headlines dikhao") == Intent.NEWS
        assert classify_intent("Taza samachar kya hai") == Intent.NEWS
        assert classify_intent("aaj bharat me kya huaa") == Intent.NEWS
        assert classify_intent("aaj kya hua") == Intent.NEWS
        assert classify_intent("/news cricket") == Intent.NEWS

    def test_news_summary_and_followup_intent(self):
        assert classify_intent("Is news ko simple Hindi mein samjhao") == Intent.NEWS_SUMMARY
        assert classify_intent("Is article ko summarize karo") == Intent.NEWS_SUMMARY
        assert classify_intent("Iska India par kya impact hoga") == Intent.NEWS_SUMMARY


class TestNewsQueryAndCategoryNLP:
    """Test natural language keyword extraction and category/country detection."""

    def test_extract_news_query_hinglish_cleaning(self):
        query = extract_news_query("OpenAI ke latest updates batao")
        assert "openai" in query.lower()
        # Ensure stop words like 'ke', 'batao', 'latest', 'updates' are stripped
        assert "batao" not in query.lower()
        assert "updates" not in query.lower()

    def test_detect_news_category(self):
        assert detect_news_category("Latest cricket match score and news") == "sports"
        assert detect_news_category("Share market aur Sensex ki report") == "business"
        assert detect_news_category("New AI and semiconductor chips") == "technology"
        assert detect_news_category("ISRO Chandrayaan mission space update") == "science"
        assert detect_news_category("Hospital medicine and covid update") == "health"
        assert detect_news_category("Bollywood new movie trailer release") == "entertainment"
        assert detect_news_category("Election and parliament session update") == "politics"
        assert detect_news_category("Kuch taza khabrein") == "general"

    def test_detect_news_country(self):
        assert detect_news_country("India ki top news") == "in"
        assert detect_news_country("Bharat ka naya budget") == "in"
        assert detect_news_country("USA election news") == "us"
        assert detect_news_country("UK london news") == "gb"

    def test_is_news_summary_query(self):
        assert is_news_summary_query("Is news ko simple Hindi me samjhao") is True
        assert is_news_summary_query("Iska India par kya impact hoga") is True
        assert is_news_summary_query("Summarize this article") is True
        assert is_news_summary_query("Python code likho") is False
        assert is_news_summary_query("Hi Vitya") is False


class TestArticleNormalizationAndDeduplication:
    """Test uniform schema normalization across providers and deduplication."""

    def test_normalize_newsapi_article(self):
        raw = {
            "title": "Tech Breakthrough in AI",
            "description": "Scientists invent new neural architecture.",
            "url": "https://techtimes.com/breakthrough",
            "urlToImage": "https://techtimes.com/img.jpg",
            "publishedAt": "2026-10-10T08:00:00Z",
            "source": {"name": "Tech Times"},
            "category": "technology",
        }
        item = _normalize_common_article(raw, provider="newsapi")
        assert item["title"] == "Tech Breakthrough in AI"
        assert item["source"] == "Tech Times"
        assert item["url"] == "https://techtimes.com/breakthrough"
        assert item["image"] == "https://techtimes.com/img.jpg"
        assert item["provider"] == "newsapi"

    def test_normalize_mediastack_article(self):
        raw = {
            "title": "Market Highs Today",
            "description": "Stock indices reach all-time records.",
            "url": "https://financials.org/stocks",
            "image": "https://financials.org/chart.png",
            "published_at": "2026-10-10T07:30:00Z",
            "source": "Market Watch",
            "category": "business",
        }
        item = _normalize_common_article(raw, provider="mediastack")
        assert item["title"] == "Market Highs Today"
        assert item["source"] == "Market Watch"
        assert item["category"] == "business"
        assert item["provider"] == "mediastack"

    def test_normalize_currents_article(self):
        raw = {
            "title": "Space Probe Lands Safely",
            "description": "Exploration unit touches down.",
            "url": "https://space.org/landing",
            "image": "https://space.org/landing.jpg",
            "published": "2026-10-10T06:00:00Z",
            "author": "Space Agency",
            "category": "science",
        }
        item = _normalize_common_article(raw, provider="currents")
        assert item["title"] == "Space Probe Lands Safely"
        assert item["source"] == "Space Agency"
        assert item["provider"] == "currents"

    def test_deduplicate_articles(self):
        articles = [
            {"title": "Sensex Jumps 500 Points", "url": "https://news.com/1", "source": "A"},
            {"title": "sensex jumps 500 points", "url": "https://news.com/2", "source": "B"},  # duplicate title
            {"title": "Different News", "url": "https://news.com/1", "source": "C"},  # duplicate url
            {"title": "Unique Fresh Story", "url": "https://news.com/3", "source": "D"},
        ]
        deduped = _deduplicate_articles(articles)
        assert len(deduped) == 2
        assert deduped[0]["title"] == "Sensex Jumps 500 Points"
        assert deduped[1]["title"] == "Unique Fresh Story"


class TestNewsServiceCachingAndFallback:
    """Test caching mechanism and web fallback."""

    def test_in_memory_caching(self):
        _NEWS_CACHE.clear()
        fake_articles = [
            {
                "title": "Cached News Title",
                "description": "Test cache description",
                "source": "Test Source",
                "url": "https://test.com/cache",
                "image": None,
                "publishedAt": "2026-10-10T00:00:00Z",
                "category": "technology",
                "provider": "newsapi",
            }
        ]

        with patch("backend.chats.services.news_service.fetch_from_newsapi", return_value=fake_articles) as mock_api:
            # First call: hits provider and caches
            res1 = fetch_news(category="technology", provider="newsapi")
            assert len(res1) == 1
            assert res1[0]["title"] == "Cached News Title"
            assert mock_api.call_count == 1

            # Second call: served directly from _NEWS_CACHE
            res2 = fetch_news(category="technology", provider="newsapi")
            assert len(res2) == 1
            assert res2[0]["title"] == "Cached News Title"
            assert mock_api.call_count == 1  # Not called again!

    def test_summarize_news_articles_fallback(self):
        articles = [
            {
                "title": "AI Model Announced",
                "source": "TechDaily",
                "description": "New AI model achieves state-of-the-art benchmarks.",
                "url": "https://techdaily.com/ai",
            }
        ]
        summary = summarize_news_articles(articles, "Summarize this news")
        assert "AI Model Announced" in summary
        assert "TechDaily" in summary


class TestNewsHandler:
    """Test handle_news_request dispatch and responses."""

    def test_non_news_returns_none(self):
        res = handle_news_request("hello", "hello")
        assert res is None

    def test_news_request_returns_structured_news(self):
        mock_articles = [
            {
                "title": "ISRO Tests New Engine",
                "source": "Science Today",
                "url": "https://example.com/engine",
                "image": "https://example.com/engine.jpg",
                "publishedAt": "2026-10-10T10:00:00Z",
                "category": "science",
                "provider": "newsapi",
                "description": "Successful test completed.",
            }
        ]

        with patch("backend.chats.handlers.news_handler.fetch_news", return_value=mock_articles):
            res = handle_news_request("aaj ki science news", "aaj ki science news")
            assert res is not None
            assert res["type"] == "news"
            assert res["category"] == "science"
            assert len(res["content"]) == 1
            assert "ISRO Tests New Engine" in res["text_summary"]

    def test_news_summary_request_returns_summary(self):
        mock_articles = [
            {
                "title": "India GDP Grows 7.2%",
                "source": "Economy Wire",
                "url": "https://example.com/gdp",
                "description": "Strong domestic manufacturing drives growth.",
            }
        ]

        with patch("backend.chats.handlers.news_handler.fetch_news", return_value=mock_articles):
            with patch("backend.chats.handlers.news_handler.summarize_news_articles", return_value="**GDP Summary:** Bharat ki economy majboot hai."):
                res = handle_news_request(
                    "is news ko simple hindi me samjhao: 'India GDP Grows 7.2%'",
                    "Is news ko simple Hindi me samjhao: 'India GDP Grows 7.2%'",
                )
                assert res is not None
                assert res["type"] == "text"
                assert res["intent"] == "NEWS_SUMMARY"
                assert "GDP Summary" in res["content"]
