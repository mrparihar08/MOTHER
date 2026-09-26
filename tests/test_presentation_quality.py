import pytest
from unittest.mock import patch
from backend.chats.presentation.presentation_api import (
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
    with patch("backend.chats.presentation.planner.os.getenv", return_value="fake_api_key"):
        with patch("backend.chats.presentation.planner.generate_response") as mock_gen:
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
            assert "BESPOKE ACTION-ORIENTED TITLE INTELLIGENCE" in call_arg
            assert "CONTENT QUALITY & DENSITY" in call_arg
            assert "INTELLIGENT CHART SELECTION" in call_arg


def test_build_gemini_slide_script_audience_persona():
    req_exec = GenerateRequest(prompt="Cloud Architecture", slide_count=5, audience="Executives & Board Members", use_gemini=True)
    with patch("backend.chats.presentation.planner.os.getenv", return_value="fake_api_key"):
        with patch("backend.chats.presentation.planner.generate_response") as mock_gen:
            mock_gen.return_value = "Slide 1:\nTitle: Cloud Architecture\n\nSlide 2:\nTitle: Overview"
            build_gemini_slide_script(req_exec)
            call_arg = mock_gen.call_args[0][0]
            assert "Focus on strategic ROI, financial impact" in call_arg

    req_dev = GenerateRequest(prompt="Cloud Architecture", slide_count=5, audience="Software Engineers & Tech Leads", use_gemini=True)
    with patch("backend.chats.presentation.planner.os.getenv", return_value="fake_api_key"):
        with patch("backend.chats.presentation.planner.generate_response") as mock_gen:
            mock_gen.return_value = "Slide 1:\nTitle: Cloud Architecture\n\nSlide 2:\nTitle: Overview"
            build_gemini_slide_script(req_dev)
            call_arg = mock_gen.call_args[0][0]
            assert "Focus on technical specs, architecture, APIs" in call_arg



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


def test_presentation_save_endpoint(client):
    payload = {
        "prompt": "Artificial Intelligence Strategy",
        "slide_count": 4,
        "audience": "Executives",
        "use_gemini": False
    }
    res = client.post("/api/presentation/save", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "saved"
    assert "presentation_id" in data
    assert data["presentation_id"].startswith("pres_")
    assert "download_url" in data
    assert data["file_name"].endswith(".pptx")


def test_refine_slide_endpoint(client):
    payload = {
        "text": "Our product is good and fast",
        "action": "polish"
    }
    res = client.post("/api/presentation/refine-slide", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "refined_text" in data
    assert len(data["refined_text"]) > 0


def test_custom_brand_presentation_generation(client):
    payload = {
        "prompt": "Acme Corporate Strategy Deck",
        "slide_count": 4,
        "use_gemini": False,
        "use_custom_brand": True,
        "brand_color": "#1e293b",
        "brand_secondary_color": "#0f172a",
        "brand_font": "Montserrat",
        "brand_footer": "© 2026 Acme Corp | Confidential",
        "brand_logo": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    }
    res = client.post("/api/presentation/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "download_url" in data
    assert data["file_name"].endswith(".pptx")


def test_two_stage_structured_presentation_plan_api(client):
    payload = {
        "topic": "Quantum Computing Innovations",
        "audience": "Tech Investors & CTOs",
        "purpose": "Investment Pitch & System Architecture Overview",
        "language": "English",
        "slide_count": "auto",
        "depth": "detailed",
        "style": "corporate",
        "user_requirements": "Focus on qubit stability, fault tolerance, and financial ROI",
        "use_gemini": False
    }
    res = client.post("/api/presentation/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "structured_plan" in data
    s_plan = data["structured_plan"]
    assert s_plan is not None
    assert "presentation" in s_plan
    assert "design_system" in s_plan
    assert "slides" in s_plan
    assert len(s_plan["slides"]) > 0

    slide1 = s_plan["slides"][0]
    assert "content_plan" in slide1
    assert "design_plan" in slide1
    assert "type" in slide1["content_plan"]
    assert "layout" in slide1["design_plan"]
    assert "density" in slide1["design_plan"]


def test_stage1_and_stage2_pipeline(client):
    # STAGE 1: PPT PLANNER -> USER PREVIEW
    payload_stage1 = {
        "topic": "Autonomous Driving Systems",
        "audience": "Automotive Executives",
        "purpose": "Technology Strategy Review",
        "slide_count": "auto",
        "depth": "detailed",
        "use_gemini": False
    }
    res1 = client.post("/api/presentation/stage1/plan", json=payload_stage1)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "preview_ready"
    assert "topic" in data1
    assert data1["decided_slide_count"] > 0
    assert "slide_sequence" in data1
    assert "design_system" in data1
    assert "structured_plan" in data1

    # STAGE 2: PPT GENERATOR -> FINAL PPT
    payload_stage2 = {
        "topic": data1["topic"],
        "plan": data1["structured_plan"],
        "use_gemini": False
    }
    res2 = client.post("/api/presentation/stage2/generate", json=payload_stage2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "completed"
    assert "download_url" in data2
    assert data2["file_name"].endswith(".pptx")


def test_topic_title_cleaning_and_extraction():
    from backend.chats.presentation.planner import PromptPlanner
    planner = PromptPlanner()

    raw_prompt1 = "Create a 10 slide presentation on Artificial Intelligence in Healthcare with subtopics: Radiology, Pathology, Drug Discovery"
    clean_title1 = planner.extract_overall_title(raw_prompt1, [])
    assert clean_title1 == "Artificial Intelligence In Healthcare" or clean_title1 == "Artificial Intelligence in Healthcare"

    raw_prompt2 = "Generate a PPT about Autonomous Electric Vehicles covering battery tech and infrastructure"
    clean_title2 = planner.extract_overall_title(raw_prompt2, [])
    assert clean_title2 == "Autonomous Electric Vehicles"


def test_subtopics_parsing_numbered_and_bullet_lists():
    from backend.chats.presentation.planner import PromptPlanner
    planner = PromptPlanner()

    prompt = """Artificial Intelligence in Healthcare
Subtopics:
1. Medical Imaging & Diagnostics
2) AI-Driven Drug Discovery
- Robot-Assisted Surgery
* Ethical & Regulatory Challenges"""

    subtopics = planner.extract_user_subtopics(prompt)
    assert len(subtopics) == 4
    assert subtopics[0] == "Medical Imaging & Diagnostics"
    assert subtopics[1] == "Ai-Driven Drug Discovery" or subtopics[1] == "AI-Driven Drug Discovery"
    assert subtopics[2] == "Robot-Assisted Surgery"
    assert subtopics[3] == "Ethical & Regulatory Challenges"


def test_subtopics_fallback_and_explicit_request(client):
    # Test fallback subtopics when prompt has no explicit subtopics clause
    payload_fallback = {
        "prompt": "Quantum Computing Innovations",
        "use_gemini": False
    }
    res = client.post("/api/presentation/plan", json=payload_fallback)
    assert res.status_code == 200
    data = res.json()
    assert data["topic"] == "Quantum Computing Innovations"
    assert isinstance(data["subtopics"], list)
    assert len(data["subtopics"]) > 0

    # Test explicit subtopics array in request
    payload_explicit = {
        "topic": "Renewable Energy Trends",
        "subtopics": ["Solar Grid Scale", "Offshore Wind Power", "Green Hydrogen Storage"],
        "use_gemini": False
    }
    res2 = client.post("/api/presentation/plan", json=payload_explicit)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["topic"] == "Renewable Energy Trends"
    assert data2["subtopics"] == ["Solar Grid Scale", "Offshore Wind Power", "Green Hydrogen Storage"]


def test_framed_archetype_title_and_text_bounds():
    from backend.chats.presentation.planner import best_font_size_for_paragraph, best_font_size_for_bullets
    
    # Test paragraph font scaling in a narrow column box with full 546-char text from user image
    long_text = "Contemporary lifestyle management requires a deliberate balancing act between professional ambition, academic rigor, and personal health. As societal pressures intensify for both students and working professionals, establishing a structured foundation becomes essential for preventing burnout and fostering long-term resilience. This framework integrates physical vitality, mental clarity, and emotional equilibrium into a cohesive daily routine designed to optimize human potential across all life stages."
    font_size_narrow = best_font_size_for_paragraph(long_text, base=14, box_width=4.4, box_height=3.5)
    font_size_wide = best_font_size_for_paragraph(long_text, base=14, box_width=11.7, box_height=5.0)
    
    assert font_size_narrow <= 13
    assert font_size_narrow < font_size_wide

    # Test title top position for framed archetypes in presentation planner/renderer
    from backend.chats.presentation.renderers.ppt_renderer import PptRenderer
    from backend.chats.presentation.schemas import PresentationPlan, SlideSpec, SlidePluginParagraph, SlidePluginImage
    
    plan = PresentationPlan(
        title="Modern Lifestyle Dynamics",
        template_name="savon_classic",
        slides=[
            SlideSpec(title="Modern Lifestyle Dynamics", is_title_slide=True),
            SlideSpec(
                title="Introduction to Holistic Lifestyle Frameworks",
                layout="mixed_content_slide",
                plugins=[
                    SlidePluginParagraph(type="paragraph", data={"text": long_text}),
                    SlidePluginImage(type="image", data={"caption": "Holistic Framework"}),
                ]
            )
        ]
    )
    renderer = PptRenderer()
    prs = renderer.render(plan)
    slide2 = prs.slides[1]
    
    # Find title shape and check top position >= 0.70 inches
    title_shape = None
    for shape in slide2.shapes:
        if shape.has_text_frame and "Introduction to Holistic" in shape.text_frame.text:
            title_shape = shape
            break
            
    assert title_shape is not None
    top_inches = title_shape.top / 914400.0  # Convert EMU to Inches
    assert top_inches >= 0.70




