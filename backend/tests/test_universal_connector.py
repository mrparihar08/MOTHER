import pytest
from unittest.mock import MagicMock, patch

from backend.chats.utils.intent_router import classify_intent, Intent
from backend.chats.services.unified_connector import (
    ResultCategory,
    StandardizedResult,
    ShoppingMetadata,
    AcademicMetadata,
    EducationMetadata,
    GovernmentMetadata,
    orchestrator,
    SourceRegistry,
)
from backend.chats.handlers.connector_handler import (
    detect_connector_category,
    clean_search_query,
    handle_connector_request,
)
from backend.chats.services.unified_connector.adapters.shopping_adapter import (
    build_amazon_search_url,
    build_flipkart_search_url,
    fetch_shopping_results,
)
from backend.chats.services.unified_connector.adapters.education_adapter import fetch_education_resources
from backend.chats.services.unified_connector.adapters.research_adapter import fetch_research_papers
from backend.chats.services.unified_connector.adapters.government_adapter import fetch_government_data


class TestUniversalIntentClassification:
    """Verify that intent routing classifies connector queries accurately without affecting greetings or casual chat."""

    def test_greetings_never_trigger_connector(self):
        assert classify_intent("Hi") == Intent.GREETING
        assert classify_intent("Hello Vitya") == Intent.GREETING
        assert classify_intent("namaste") == Intent.GREETING

    def test_general_chat_never_triggers_connector(self):
        assert classify_intent("Python kya hai?") == Intent.GENERAL_KNOWLEDGE
        assert classify_intent("2 + 2 kitna hota hai") == Intent.GENERAL_KNOWLEDGE

    def test_shopping_intent_detection(self):
        assert classify_intent("Amazon aur Flipkart par is product ke options compare karo") == Intent.SHOPPING
        assert classify_intent("buy iPhone 15 online") == Intent.SHOPPING
        assert classify_intent("laptop price on amazon") == Intent.SHOPPING
        assert classify_intent("/shop headphones") == Intent.SHOPPING

    def test_education_intent_detection(self):
        assert classify_intent("Free Python courses ke resources batao") == Intent.EDUCATION
        assert classify_intent("FastAPI authentication ki official documentation dikhao") == Intent.EDUCATION
        assert classify_intent("/docs react tutorial") == Intent.EDUCATION

    def test_research_intent_detection(self):
        assert classify_intent("AI par research papers find karo") == Intent.RESEARCH
        assert classify_intent("arxiv paper on transformer architectures") == Intent.RESEARCH
        assert classify_intent("/paper quantum computing") == Intent.RESEARCH

    def test_government_intent_detection(self):
        assert classify_intent("Government ke official data se is topic ko samjhao") == Intent.GOVERNMENT_DATA
        assert classify_intent("GDP of India data.gov") == Intent.GOVERNMENT_DATA
        assert classify_intent("/gov inflation statistics") == Intent.GOVERNMENT_DATA


class TestShoppingAdapter:
    """Verify Amazon and Flipkart affiliate link generation and shopping search."""

    def test_affiliate_urls_contain_tags(self):
        amz_url = build_amazon_search_url("running shoes")
        assert "amazon.in/s?k=" in amz_url
        assert "tag=" in amz_url

        fk_url = build_flipkart_search_url("running shoes")
        assert "flipkart.com/search?q=" in fk_url
        assert "affid=" in fk_url

    def test_fetch_shopping_results_returns_standardized(self):
        results = fetch_shopping_results("noise smart watch", limit=2)
        assert len(results) > 0
        first = results[0]
        assert isinstance(first, StandardizedResult)
        assert first.category == ResultCategory.SHOPPING
        assert first.shopping is not None
        assert first.shopping.store in ["Amazon India", "Flipkart", "Online Retailer"]


class TestEducationAdapter:
    """Verify curated official docs and educational courses."""

    def test_fastapi_and_python_curated_docs(self):
        results = fetch_education_resources("fastapi authentication", limit=2)
        assert len(results) > 0
        fastapi_match = [r for r in results if "fastapi" in r.title.lower() or "fastapi" in r.url.lower()]
        assert len(fastapi_match) > 0
        assert fastapi_match[0].category == ResultCategory.EDUCATION
        assert fastapi_match[0].education.is_free is True


class TestResearchAdapter:
    """Verify arXiv open-access search returns authors, abstracts, and PDF links."""

    def test_research_papers_schema(self):
        fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2301.00001</id>
            <title>Attention Is All You Need Revised</title>
            <summary>A groundbreaking deep learning architecture.</summary>
            <published>2023-01-01T00:00:00Z</published>
            <author><name>Ashish Vaswani</name></author>
            <link title="pdf" href="http://arxiv.org/pdf/2301.00001.pdf" type="application/pdf"/>
          </entry>
        </feed>"""

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_xml

        with patch("requests.get", return_value=mock_resp):
            papers = fetch_research_papers("attention is all you need", limit=1)
            assert len(papers) == 1
            p = papers[0]
            assert p.category == ResultCategory.RESEARCH
            assert p.title == "Attention Is All You Need Revised"
            assert "Vaswani" in p.academic.authors[0]
            assert p.academic.pdf_url == "http://arxiv.org/pdf/2301.00001.pdf"
            assert p.academic.year == 2023


class TestGovernmentAdapter:
    """Verify World Bank indicator parsing and OGD portal links."""

    def test_world_bank_indicator_parsing(self):
        fake_wb_json = [
            {"page": 1, "pages": 1, "per_page": 5, "total": 1},
            [{"indicator": {"id": "NY.GDP.MKTP.CD"}, "countryiso3code": "IND", "date": "2023", "value": 3549918918231.0}],
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_wb_json

        with patch("requests.get", return_value=mock_resp):
            gov_results = fetch_government_data("gdp of india", limit=1)
            assert len(gov_results) > 0
            res = gov_results[0]
            assert res.category == ResultCategory.GOVERNMENT
            assert "GDP" in res.title
            assert res.government.portal == "World Bank Open Data"


class TestOrchestratorAndHandler:
    """Verify central orchestrator caching, deduplication, and handler dispatch."""

    def test_source_registry_lists_categories(self):
        sources = SourceRegistry.get_supported_sources()
        assert "shopping" in sources
        assert "education" in sources
        assert "research" in sources
        assert "government" in sources

    def test_connector_handler_dispatch(self):
        res = handle_connector_request(
            msg="free python courses ke resources batao",
            user_message="Free Python courses ke resources batao",
        )
        assert res is not None
        assert res["type"] == "education"
        assert res["category"] == "education"
        assert len(res["content"]) > 0
        assert "text_summary" in res
