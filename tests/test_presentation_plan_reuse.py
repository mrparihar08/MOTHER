import pytest
from unittest.mock import patch
from backend.chats.presentation.presentation_api import PresentationPlan, SlideSpec, SlidePluginBullets


def test_generate_with_custom_plan(client):
    custom_plan = {
        "title": "Custom Test Plan Title",
        "slides": [
            {
                "layout": "title_slide",
                "title": "Custom Title Slide",
                "subtitle": "Subtitle test",
                "plugins": []
            },
            {
                "layout": "bullets_slide",
                "title": "Custom Bullets Slide",
                "plugins": [
                    {
                        "type": "bullets",
                        "data": {
                            "bullets": ["Point A", "Point B"]
                        }
                    }
                ]
            }
        ]
    }

    req_payload = {
        "prompt": "Test Prompt",
        "slide_count": 3,
        "plan": custom_plan
    }

    # Patch build_gemini_slide_script to verify it is NOT called when plan is provided
    with patch("backend.chats.presentation_api.build_gemini_slide_script") as mock_gemini:
        res = client.post("/api/presentation/generate", json=req_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert "download_url" in data
        # Gemini script builder should NOT have been called
        mock_gemini.assert_not_called()


def test_generate_without_plan(client):
    req_payload = {
        "prompt": "Test Prompt without plan",
        "slide_count": 3,
        "use_gemini": False
    }

    res = client.post("/api/presentation/generate", json=req_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "download_url" in data
