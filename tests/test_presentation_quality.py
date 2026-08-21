import pytest
from unittest.mock import patch
from backend.chats.presentation_api import (
    clean_ai_instructions,
    build_gemini_slide_script,
    GenerateRequest,
    PromptPlanner,
    service,
)


def test_clean_ai_instructions():
    assert clean_ai_instructions("Explain the key features of AI") == "key features of AI"
    assert clean_ai_instructions("Break down the system architecture") == "the system architecture"
    assert clean_ai_instructions("Detail the performance benchmark results") == "performance benchmark results"
    assert clean_ai_instructions("Focus on the primary advantages") == "the primary advantages"
    assert clean_ai_instructions("Highlight top 3 security mechanisms") == "top 3 security mechanisms"
    assert clean_ai_instructions("Describe the dataset cleaning pipeline") == "dataset cleaning pipeline"
    assert clean_ai_instructions("Conclude with future scope") == "future scope"
    assert clean_ai_instructions("Normal Slide Title") == "Normal Slide Title"
    assert clean_ai_instructions("") == ""


def test_build_gemini_slide_script_prompt():
    req = GenerateRequest(prompt="Electric Vehicle Architecture", slide_count=6, use_gemini=True)
    with patch("backend.chats.presentation_api.os.getenv", return_value="fake_api_key"):
        with patch("backend.chats.presentation_api.generate_response") as mock_gen:
            mock_gen.return_value = """Slide 1:
Title: Electric Vehicle Architecture
Subtitle: Modern Powertrain Overview

Slide 2:
Title: Executive Summary
Paragraph: EVs replace internal combustion engines with electric motors and high-voltage battery packs.

Slide 3:
Title: Powertrain Workflow
Diagram: [Battery Pack] ➔ [Inverter / Controller] ➔ [Electric Motor] ➔ [Drivetrain / Wheels]

Slide 4:
Title: Battery Tech Comparison
Table:
Chemistry | Energy Density | Safety | Cost
LFP | Medium (160 Wh/kg) | Exceptional | Low
NMC | High (250 Wh/kg) | High | Medium

Slide 5:
Title: Global EV Sales Growth
Chart: column
Series Name: Sales (Millions) [Illustrative Data]
2021: 6.5
2022: 10.2
2023: 14.0
2024: 17.5

Slide 6:
Title: Visual Showcase
Image: EV charging hub
Paragraph: High-speed DC charging networks enable fast multi-state travel."""

            script = build_gemini_slide_script(req)
            assert script is not None
            assert "Slide 1:" in script
            call_arg = mock_gen.call_args[0][0]
            assert "TOPIC & STRUCTURE INTELLIGENCE" in call_arg
            assert "CONTENT QUALITY & DENSITY" in call_arg
            assert "CHARTS & DATA INTEGRITY" in call_arg
            assert "REAL COMPARISON TABLES" in call_arg


def test_diagram_plugin_parsing():
    script_text = """Slide 1:
Title: Machine Learning Pipeline
Diagram: [Raw Data] ➔ [Preprocessing] ➔ [Model Training] ➔ [Evaluation] ➔ [Deployment]
Bullets:
- Automated feature extraction
- Real-time inference service"""

    planner = PromptPlanner()
    plan = planner.plan(script_text)
    assert plan.title == "Machine Learning Pipeline"
    target_slide = plan.slides[1] if len(plan.slides) > 1 else plan.slides[0]
    plugin_types = [p.type for p in target_slide.plugins]
    assert "diagram" in plugin_types


def test_chart_illustrative_labeling():
    planner = PromptPlanner()
    script_text = """Slide 1:
Title: Growth Metrics
Chart: column
Series Name: Performance Trend
Q1: 25
Q2: 50
Q3: 75
Q4: 100"""
    plan = planner.plan(script_text)
    chart_plugin = next(p for p in plan.slides[1].plugins if p.type == "chart")
    assert chart_plugin.data is not None


def test_full_presentation_generation_endpoint(client):
    payload = {
        "prompt": "Cyber Security Best Practices",
        "slide_count": 5,
        "use_gemini": False
    }
    res = client.post("/api/presentation/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "download_url" in data
    assert data["file_name"].endswith(".pptx")
