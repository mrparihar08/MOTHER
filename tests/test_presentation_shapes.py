import pytest
from backend.chats.presentation.schemas import SlidePluginShape, PresentationPlan, SlideSpec


def test_shapes_catalog_api(client):
    res = client.get("/api/presentation/shapes/catalog")
    assert res.status_code == 200
    data = res.json()
    assert "categories" in data
    assert "default_style" in data

    categories = {cat["id"]: cat for cat in data["categories"]}
    assert "basic_shapes" in categories
    assert "lines_connectors" in categories
    assert "flowchart" in categories
    assert "callouts" in categories

    basic_shape_ids = {s["id"] for s in categories["basic_shapes"]["shapes"]}
    expected_basic = {
        "rectangle", "rounded_rectangle", "circle", "oval", "triangle",
        "diamond", "pentagon", "hexagon", "octagon", "parallelogram",
        "trapezoid", "star", "heart", "cross"
    }
    assert expected_basic.issubset(basic_shape_ids)

    connector_ids = {s["id"] for s in categories["lines_connectors"]["shapes"]}
    expected_connectors = {"line", "arrow", "double_arrow", "elbow_connector", "curved_connector", "straight_connector"}
    assert expected_connectors.issubset(connector_ids)

    flowchart_ids = {s["id"] for s in categories["flowchart"]["shapes"]}
    expected_flowchart = {"process", "decision", "data", "document", "database", "start_end", "predefined_process"}
    assert expected_flowchart.issubset(flowchart_ids)

    callout_ids = {s["id"] for s in categories["callouts"]["shapes"]}
    expected_callouts = {"speech_bubble", "cloud_callout", "rectangular_callout", "rounded_callout"}
    assert expected_callouts.issubset(callout_ids)


def test_presentation_shapes_save_reload_download(client):
    # 1. Create a presentation with custom shape plugin elements from all categories
    shapes_payload = {
        "prompt": "System Architecture Flow",
        "topic": "System Flow",
        "slide_count": 2,
        "content_theme": "corporate_light",
        "use_ai_image_generation": False,
        "use_gemini": False,
        "plan": {
            "title": "Architecture & Flowchart Deck",
            "slides": [
                {
                    "layout": "title_slide",
                    "title": "System Architecture Deck",
                    "subtitle": "Flowchart and Callout Showcase",
                    "plugins": []
                },
                {
                    "layout": "mixed_content_slide",
                    "title": "Architecture Workflow Shapes",
                    "plugins": [
                        # Basic shape (Rounded Rectangle with text)
                        {
                            "type": "shape",
                            "data": {
                                "id": "shape-001",
                                "type": "rounded_rectangle",
                                "left": 1.0,
                                "top": 2.0,
                                "width": 2.5,
                                "height": 1.2,
                                "fill": "#3B82F6",
                                "stroke": "#1E40AF",
                                "stroke_width": 2,
                                "stroke_style": "solid",
                                "rotation": 0,
                                "text": "Microservice A",
                                "text_style": {
                                    "font_size": 14,
                                    "bold": True,
                                    "color": "#FFFFFF",
                                    "align": "center",
                                    "valign": "middle"
                                }
                            }
                        },
                        # Connector Arrow
                        {
                            "type": "shape",
                            "data": {
                                "id": "shape-002",
                                "type": "arrow",
                                "left": 3.6,
                                "top": 2.5,
                                "width": 1.5,
                                "height": 0.2,
                                "stroke": "#10B981",
                                "stroke_width": 3
                            }
                        },
                        # Flowchart Decision node
                        {
                            "type": "shape",
                            "data": {
                                "id": "shape-003",
                                "type": "decision",
                                "left": 5.3,
                                "top": 1.8,
                                "width": 1.8,
                                "height": 1.6,
                                "fill": "#F59E0B",
                                "stroke": "#B45309",
                                "text": "Valid Auth?",
                                "text_style": {
                                    "font_size": 12,
                                    "bold": True,
                                    "color": "#1E293B"
                                }
                            }
                        },
                        # Callout Speech Bubble
                        {
                            "type": "shape",
                            "data": {
                                "id": "shape-004",
                                "type": "speech_bubble",
                                "left": 7.5,
                                "top": 1.8,
                                "width": 2.2,
                                "height": 1.5,
                                "fill": "#8B5CF6",
                                "text": "OAuth 2.0 Token Verified!",
                                "text_style": {
                                    "font_size": 11,
                                    "italic": True,
                                    "color": "#FFFFFF"
                                }
                            }
                        }
                    ]
                }
            ]
        }
    }

    # 2. Save Presentation
    res_save = client.post("/api/presentation/save", json=shapes_payload)
    assert res_save.status_code == 200
    save_data = res_save.json()
    pres_id = save_data["presentation_id"]
    assert pres_id.startswith("pres_")
    assert save_data["version"] == 1

    # 3. Reload Presentation state by ID
    res_get = client.get(f"/api/presentation/{pres_id}")
    assert res_get.status_code == 200
    details = res_get.json()
    reload_plan = details["plan"]
    
    # Verify shape plugins persist accurately
    slide2_plugins = reload_plan["slides"][1]["plugins"]
    shape_types = [p["data"]["type"] for p in slide2_plugins if p["type"] == "shape"]
    assert "rounded_rectangle" in shape_types
    assert "arrow" in shape_types
    assert "decision" in shape_types
    assert "speech_bubble" in shape_types

    # 4. Download PPTX file and verify rendering
    res_dl = client.get(f"/api/presentation/download-presentation/{pres_id}")
    assert res_dl.status_code == 200
    assert len(res_dl.content) > 1000
    assert res_dl.headers["content-type"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
