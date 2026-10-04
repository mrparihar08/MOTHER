import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.presentation.schemas import (
    ImageResult,
    LicenseStatus,
    VisualType,
    PresentationPlan,
    SlideSpec,
    SlidePluginImage,
)
from backend.presentation.services.image_search.license_checker import (
    normalize_license_name,
    evaluate_license,
    build_attribution_string,
)
from backend.presentation.services.image_search.image_selector import (
    determine_visual_type,
    build_slide_image_query,
    score_image_result,
    rank_and_select_images,
)
from backend.presentation.services.image_search.openverse import search_openverse
from backend.presentation.services.image_search.wikimedia import search_wikimedia
from backend.presentation.services.image_search.image_service import (
    search_images,
    suggest_images_for_slide,
    is_safe_external_url,
)
from backend.presentation.presentation_api import router
from fastapi import FastAPI
from backend.presentation.renderers.ppt_renderer import PptRenderer


app = FastAPI()
app.include_router(router, prefix="/api/presentation")
client = TestClient(app)


# ---------------------------------------------------------------------
# 1. License Evaluation & Attribution Unit Tests
# ---------------------------------------------------------------------

def test_license_normalization_and_evaluation():
    # CC0 / Public Domain
    assert normalize_license_name("cc0 1.0 universal") == "CC0 1.0"
    assert evaluate_license("CC0")["license_status"] == LicenseStatus.COMMERCIAL_SAFE
    assert evaluate_license("public domain mark")["license_status"] == LicenseStatus.COMMERCIAL_SAFE

    # CC BY variants
    assert normalize_license_name("creative commons attribution 4.0 international") == "CC BY 4.0"
    assert evaluate_license("CC BY 4.0")["license_status"] == LicenseStatus.ATTRIBUTION_REQUIRED

    # Non-Commercial
    assert evaluate_license("CC BY-NC 4.0")["license_status"] == LicenseStatus.NON_COMMERCIAL

    # Unknown
    assert evaluate_license("Random Unknown License")["license_status"] == LicenseStatus.UNKNOWN


def test_attribution_string_builder():
    attr_by = build_attribution_string("Architecture Diagram", "Jane Smith", "CC BY 4.0", "Openverse")
    assert "Image: Architecture Diagram" in attr_by
    assert "Jane Smith" in attr_by
    assert "CC BY 4.0" in attr_by

    attr_no_title = build_attribution_string("", "Anonymous", "CC BY-SA 3.0", "Wikimedia")
    assert "Image: Untitled Visual" in attr_no_title
    assert "Anonymous" in attr_no_title


# ---------------------------------------------------------------------
# 2. Visual Type Detection & Query Construction Tests
# ---------------------------------------------------------------------

def test_visual_type_detection():
    assert determine_visual_type("System Architecture & Flow", "data pipeline microservices") == VisualType.FLOWCHART
    assert determine_visual_type("Quarterly Growth Metrics", "revenue column chart") == VisualType.CHART
    assert determine_visual_type("Executive Leadership Team", "corporate portrait photo") == VisualType.PHOTO
    assert determine_visual_type("Feature Comparison Icon Set", "vector icon glyph") in (VisualType.ICON, VisualType.CONCEPTUAL_IMAGE)


def test_build_slide_image_query():
    query_diag = build_slide_image_query("Cloud Infrastructure", "Kubernetes Pipeline", "deploy microservices cluster", VisualType.DIAGRAM)
    assert "cloud infrastructure" in query_diag.lower()
    assert "kubernetes pipeline" in query_diag.lower()
    assert "diagram" in query_diag.lower()


# ---------------------------------------------------------------------
# 3. Image Scoring, Ranking & Duplicate Prevention Tests
# ---------------------------------------------------------------------

def test_image_scoring_and_ranking():
    item1 = ImageResult(
        id="1",
        image_url="https://example.com/1.jpg",
        thumbnail_url="https://example.com/1.jpg",
        title="Artificial Intelligence Neural Network Diagram",
        creator="Alice",
        license="CC BY 4.0",
        provider="openverse",
        width=1920,
        height=1080,
        aspect_ratio=1.78,
        visual_type="diagram",
        license_status="attribution_required",
    )
    item2 = ImageResult(
        id="2",
        image_url="https://example.com/2.jpg",
        thumbnail_url="https://example.com/2.jpg",
        title="Unrelated Small Square Image",
        creator="Bob",
        license="Unknown",
        provider="wikimedia",
        width=200,
        height=200,
        aspect_ratio=1.0,
        visual_type="photo",
        license_status="unknown",
    )

    score1 = score_image_result(item1, query="artificial intelligence", slide_title="AI Architecture", visual_type=VisualType.DIAGRAM)
    score2 = score_image_result(item2, query="artificial intelligence", slide_title="AI Architecture", visual_type=VisualType.DIAGRAM)

    assert score1 > score2

    ranked = rank_and_select_images([item1, item2], query="artificial intelligence", slide_title="AI Architecture", visual_type=VisualType.DIAGRAM)
    assert len(ranked) == 2
    assert ranked[0].id == "1"


def test_duplicate_prevention_ranking():
    item1 = ImageResult(
        id="1",
        image_url="https://example.com/shared.jpg",
        thumbnail_url="https://example.com/shared.jpg",
        title="Shared Image",
        license="CC BY 4.0",
    )
    item2 = ImageResult(
        id="2",
        image_url="https://example.com/unique.jpg",
        thumbnail_url="https://example.com/unique.jpg",
        title="Unique Image",
        license="CC BY 4.0",
    )

    used = {"https://example.com/shared.jpg"}
    ranked = rank_and_select_images([item1, item2], query="test", slide_title="test title", visual_type=VisualType.PHOTO, used_urls=used)
    assert len(ranked) == 2
    assert ranked[0].id == "2"


# ---------------------------------------------------------------------
# 4. Openverse & Wikimedia Integration Mocks
# ---------------------------------------------------------------------

@patch("requests.get")
def test_openverse_api_search_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "id": "123",
                "url": "https://images.openverse.org/123.jpg",
                "thumbnail": "https://images.openverse.org/123_thumb.jpg",
                "title": "Open Source Tech Diagram",
                "creator": "Tech Creator",
                "creator_url": "https://openverse.org/users/1",
                "license": "by",
                "license_version": "4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "foreign_landing_url": "https://flickr.com/photos/123",
                "width": 1600,
                "height": 900,
            }
        ]
    }
    mock_get.return_value = mock_resp

    results = search_openverse("tech diagram", page=1, page_size=10)
    assert len(results) == 1
    res = results[0]
    assert res.id.startswith("ov_")
    assert res.provider == "openverse"
    assert res.license == "CC BY 4.0"
    assert "Open Source Tech Diagram" in res.attribution


@patch("requests.get")
def test_wikimedia_commons_api_search_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": {
            "pages": {
                "987": {
                    "pageid": 987,
                    "title": "File:Cloud Computing Architecture.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/wikipedia/commons/cloud.png",
                            "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/cloud.png",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Cloud.jpg",
                            "mime": "image/jpeg",
                            "width": 1200,
                            "height": 800,
                            "extmetadata": {
                                "Artist": {"value": "<a href='...'>Wiki Artist</a>"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                            },
                        }
                    ],
                }
            }
        }
    }
    mock_get.return_value = mock_resp

    results = search_wikimedia("cloud architecture", limit=5)
    assert len(results) == 1
    res = results[0]
    assert res.provider == "wikimedia"
    assert res.license == "CC BY-SA 4.0"
    assert "Wiki Artist" in res.creator


# ---------------------------------------------------------------------
# 5. Security & SSRF Protection Tests
# ---------------------------------------------------------------------

def test_ssrf_security_validation():
    assert is_safe_external_url("https://images.openverse.org/photo.jpg") is True
    assert is_safe_external_url("http://127.0.0.1/admin") is False
    assert is_safe_external_url("http://localhost:8000/secret") is False
    assert is_safe_external_url("http://169.254.169.254/latest/meta-data/") is False


# ---------------------------------------------------------------------
# 6. REST API Endpoints Integration Tests
# ---------------------------------------------------------------------

@patch("backend.chats.presentation.presentation_api.search_images")
def test_api_image_search_endpoint(mock_search):
    mock_search.return_value = [
        ImageResult(
            id="test_1",
            image_url="https://example.com/test.jpg",
            thumbnail_url="https://example.com/test.jpg",
            title="Test Visual",
            license="CC0",
            provider="openverse",
        )
    ]

    response = client.get("/api/presentation/images/search?query=test&provider=openverse")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["total"] == 1
    assert data["results"][0]["title"] == "Test Visual"


@patch("backend.chats.presentation.presentation_api.suggest_images_for_slide")
def test_api_image_suggest_endpoint(mock_suggest):
    from backend.presentation.schemas import ImageSuggestResponse
    mock_suggest.return_value = ImageSuggestResponse(
        query="Enterprise Microservices diagram",
        visual_type="diagram",
        suggested_images=[
            ImageResult(
                id="sug_1",
                image_url="https://example.com/sug.jpg",
                thumbnail_url="https://example.com/sug.jpg",
                title="Microservices Flow",
                license="CC BY 4.0",
                provider="wikimedia",
            )
        ],
    )

    payload = {
        "presentation_topic": "Enterprise Tech",
        "slide_title": "Microservices Architecture",
        "key_bullets": ["API Gateway", "Container Cluster"],
    }
    response = client.post("/api/presentation/images/suggest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["visual_type"] == "diagram"
    assert len(data["suggested_images"]) == 1


# ---------------------------------------------------------------------
# 7. PPT Renderer Attribution Integration Test
# ---------------------------------------------------------------------

def test_ppt_renderer_attribution_rendering(tmp_path):
    renderer = PptRenderer()
    plan = PresentationPlan(
        title="Licensed Presentation",
        theme={"name": "modern_corporate", "background": "#FFFFFF", "text": "#1E293B", "accent": "#3B82F6"},
        slides=[
            SlideSpec(
                layout="mixed_content_slide",
                title="Attribution Test Slide",
                plugins=[
                    SlidePluginImage(
                        type="image",
                        data={
                            "url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800",
                            "title": "Neural Network Node Matrix",
                            "attribution": "Image: Neural Network Node Matrix — Jane Creator — CC BY 4.0",
                            "license": "CC BY 4.0",
                            "provider": "openverse",
                            "creator": "Jane Creator",
                        },
                    )
                ],
            )
        ],
    )

    prs = renderer.render(plan)
    assert len(prs.slides) == 1
    slide = prs.slides[0]

    texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
    found_attribution = any("Jane Creator" in t for t in texts)

    assert found_attribution is True, f"Attribution string should be rendered on slide. Found texts: {texts}"
