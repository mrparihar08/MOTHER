import os
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from backend.app.app import app
from backend.chats.presentation.exporter import save_presentation_as_pdf, OUTPUT_DIR
from backend.chats.presentation.schemas import PresentationPlan, SlideSpec, SlidePluginBullets, SlidePluginParagraph

client = TestClient(app)


def test_save_presentation_as_pdf():
    plan = PresentationPlan(
        title="AI Engineering Roadmap",
        topic="AI Engineering",
        slides=[
            SlideSpec(
                slide_number=1,
                title="AI Engineering Roadmap",
                subtitle="High Performance Systems",
                plugins=[
                    SlidePluginParagraph(type="paragraph", data={"text": "Overview of foundational architectures and LLMs."}),
                    SlidePluginBullets(type="bullets", data={"bullets": ["Neural Networks", "Transformer Architectures", "RAG Pipelines"]}),
                ],
            ),
            SlideSpec(
                slide_number=2,
                title="Deployment & Scalability",
                subtitle="Production Grade Infrastructure",
                plugins=[
                    SlidePluginBullets(type="bullets", data={"bullets": ["Vector Databases", "Caching Layers", "Monitoring Telemetry"]}),
                ],
            ),
        ],
    )

    pdf_path_str = save_presentation_as_pdf(plan, presentation_id="test_pdf_export")
    pdf_path = Path(pdf_path_str)

    assert pdf_path.exists()
    assert pdf_path.suffix == ".pdf"
    assert pdf_path.stat().st_size > 1000

    # Cleanup
    try:
        pdf_path.unlink()
    except Exception:
        pass


def test_voiceover_synthesize_endpoint():
    response = client.post(
        "/api/presentation/voiceover/synthesize",
        json={
            "text": "Welcome to Vitya presentation audio demonstration.",
            "language": "en-US",
            "slide_index": 0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "audio_url" in data
    assert data["filename"].endswith(".mp3")


def test_brand_profile_crud():
    # 1. Fetch initial brand profile
    res1 = client.get("/api/presentation/brand-profile")
    assert res1.status_code == 200
    data1 = res1.json()
    assert "brand_color" in data1

    # 2. Update brand profile
    res2 = client.post(
        "/api/presentation/brand-profile",
        json={
            "brand_name": "Acme Global Tech",
            "brand_color": "#2563EB",
            "brand_secondary_color": "#9333EA",
            "brand_font": "Roboto",
            "brand_footer": "Confidential • Acme 2026",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["brand_name"] == "Acme Global Tech"
    assert data2["brand_color"] == "#2563EB"
    assert data2["brand_font"] == "Roboto"

    # 3. Verify get returns updated profile
    res3 = client.get("/api/presentation/brand-profile")
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["brand_name"] == "Acme Global Tech"
    assert data3["brand_footer"] == "Confidential • Acme 2026"
