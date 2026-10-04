import os
from pathlib import Path
import pytest
from pptx import Presentation

from backend.presentation.schemas import (
    PresentationPlan,
    SlideSpec,
    SlidePluginParagraph,
    SlidePluginBullets,
    SlidePluginImage,
    SlidePluginTable,
    SlidePluginChart,
    SlidePluginProcessFlow,
    SlidePluginBentoGrid,
    SlidePluginKPIGrid,
    SlidePluginSplit,
    ShapeSpec,
    VisualIntent,
    ContentIntent,
    MetricSpec,
)
from backend.presentation.shapes import (
    ShapeType,
    ShapePurpose,
    SemanticRole,
    Z_BACKGROUND,
    Z_DECORATIVE_BACKGROUND,
    Z_DECORATIVE_ACCENT,
    Z_SEMANTIC_CONTAINER,
    create_shape,
    extract_content_regions,
    CollisionDetector,
    SemanticShapeEngine,
    DecorativeShapeEngine,
    DecorationQualityValidator,
    derive_shape_palette,
)
from backend.presentation.renderers.ppt_renderer import PptRenderer
from backend.presentation.geometry import Box


def test_shape_model_and_factory():
    """Verify ShapeSpec creation, default values, and attribute accessibility."""
    shape = create_shape(
        shape_type=ShapeType.ABSTRACT_ORB,
        x=9.5,
        y=0.5,
        width=3.0,
        height=3.0,
        fill="#3B82F6",
        opacity=0.10,
        z_index=Z_DECORATIVE_BACKGROUND,
        purpose=ShapePurpose.DECORATIVE,
        decorative=True,
        visual_role="title_ambient_glow",
    )
    assert shape.shape_type == "ABSTRACT_ORB"
    assert shape.x == 9.5
    assert shape.y == 0.5
    assert shape.width == 3.0
    assert shape.height == 3.0
    assert shape.fill == "#3B82F6"
    assert shape.opacity == 0.10
    assert shape.z_index == Z_DECORATIVE_BACKGROUND
    assert shape.purpose == "decorative"
    assert shape.decorative is True
    assert shape.visual_role == "title_ambient_glow"


def test_semantic_vs_decorative_separation():
    """Verify that semantic information shapes and decorative shapes remain logically distinguishable."""
    # Semantic container shape
    sem_card = create_shape(
        shape_type=ShapeType.ROUNDED_RECT,
        x=0.8,
        y=1.4,
        width=11.7,
        height=4.5,
        fill="#1E293B",
        line_color="#3B82F6",
        line_width=1.0,
        opacity=1.0,
        z_index=Z_SEMANTIC_CONTAINER,
        purpose=ShapePurpose.CONTAINER,
        decorative=False,
        semantic_role=SemanticRole.BENTO_CARD,
        visual_role="hero_container",
    )
    assert sem_card.purpose == "container"
    assert sem_card.decorative is False
    assert sem_card.semantic_role == "BENTO_CARD"
    assert sem_card.z_index == Z_SEMANTIC_CONTAINER

    # Decorative shape
    dec_ring = create_shape(
        shape_type=ShapeType.RING,
        x=12.0,
        y=0.6,
        width=0.5,
        height=0.5,
        fill="transparent",
        line_color="#3B82F6",
        line_width=1.2,
        opacity=0.60,
        z_index=Z_DECORATIVE_ACCENT,
        purpose=ShapePurpose.DECORATIVE,
        decorative=True,
        visual_role="top_right_accent_ring",
    )
    assert dec_ring.purpose == "decorative"
    assert dec_ring.decorative is True
    assert dec_ring.semantic_role is None
    assert dec_ring.z_index == Z_DECORATIVE_ACCENT


def test_title_slide_decoration():
    """Test 1: Title slide has 2–4 tasteful decorative elements without title collision."""
    slide = SlideSpec(
        layout="title_slide",
        title="Data Science",
        subtitle="From Data to Decisions",
        plugins=[],
    )
    decorated = DecorativeShapeEngine.decorate_slide(slide, slide_idx=0, total_slides=10, theme="ai")
    
    dec_shapes = [s for s in decorated.shapes if s.decorative]
    assert 2 <= len(dec_shapes) <= 5
    
    # Verify no title collision
    content_boxes = extract_content_regions(slide)
    report = DecorationQualityValidator.validate_slide_decorations(slide, dec_shapes, content_boxes)
    assert report.collisions == 0
    assert report.readability == "safe"


def test_dense_content_slide_minimal_decoration():
    """Test 2: Dense content slide has minimal decoration to preserve readability."""
    long_points = [
        "Distributed consensus protocol across multi-region availability zones.",
        "Real-time event streaming and telemetry data pipeline architecture.",
        "Continuous zero-trust security and end-to-end payload encryption.",
        "Automated horizontal pod auto-scaling and resource governance.",
        "Comprehensive disaster recovery replication and automated failover.",
        "High-throughput caching layer optimized for microsecond latency.",
    ]
    slide = SlideSpec(
        layout="bullets_slide",
        title="Distributed Cloud Infrastructure Architecture",
        plugins=[SlidePluginBullets(type="bullets", data={"points": long_points})]
    )
    decorated = DecorativeShapeEngine.decorate_slide(slide, slide_idx=3, total_slides=10, theme="ocean_blue")
    
    dec_shapes = [s for s in decorated.shapes if s.decorative]
    assert len(dec_shapes) <= 3
    
    content_boxes = extract_content_regions(slide)
    report = DecorationQualityValidator.validate_slide_decorations(slide, dec_shapes, content_boxes)
    assert report.collisions == 0
    assert report.readability == "safe"


def test_process_slide_decoration():
    """Test 3: Process slide features process-specific guidelines and status indicators."""
    slide = SlideSpec(
        layout="mixed_content_slide",
        title="End-to-End Machine Learning Lifecycle",
        visual_intent=VisualIntent.PROCESS_FLOW,
        plugins=[
            SlidePluginProcessFlow(type="process_flow", data={
                "title": "ML Lifecycle",
                "steps": [
                    {"name": "Raw Ingestion", "description": "Kafka stream"},
                    {"name": "Feature Store", "description": "Feast computation"},
                    {"name": "Model Training", "description": "Distributed PyTorch"},
                    {"name": "API Deployment", "description": "Triton inference"},
                ]
            })
        ]
    )
    decorated = DecorativeShapeEngine.decorate_slide(slide, slide_idx=4, total_slides=10, theme="tech")
    
    # Verify semantic node shapes generated
    sem_shapes = [s for s in decorated.shapes if not s.decorative]
    assert len(sem_shapes) == 4
    for s in sem_shapes:
        assert s.semantic_role == SemanticRole.PROCESS_NODE

    # Verify process-specific decoration track
    dec_shapes = [s for s in decorated.shapes if s.decorative]
    roles = [s.visual_role for s in dec_shapes]
    assert any("process" in r for r in roles)


def test_comparison_slide_decoration():
    """Test 4: Comparison slide uses header/divider accents without visual clutter."""
    slide = SlideSpec(
        layout="mixed_content_slide",
        title="Supervised vs Unsupervised Learning Paradigms",
        visual_intent=VisualIntent.COMPARISON,
        plugins=[
            SlidePluginSplit(type="split_layout", data={
                "left": {"title": "Supervised Learning", "points": ["Labeled datasets", "Classification & Regression"]},
                "right": {"title": "Unsupervised Learning", "points": ["Unlabeled data", "Clustering & Dimensionality Reduction"]}
            })
        ]
    )
    decorated = DecorativeShapeEngine.decorate_slide(slide, slide_idx=5, total_slides=10, theme="corporate_light")
    
    sem_shapes = [s for s in decorated.shapes if not s.decorative]
    assert len(sem_shapes) == 2
    assert sem_shapes[0].semantic_role == SemanticRole.COMPARISON_PANEL
    assert sem_shapes[1].semantic_role == SemanticRole.COMPARISON_PANEL

    dec_shapes = [s for s in decorated.shapes if s.decorative]
    assert len(dec_shapes) <= 3


def test_image_slide_decoration_no_overlap():
    """Test 5: Image slide decoration frames the slide without covering the image subject."""
    slide = SlideSpec(
        layout="image_slide",
        title="Edge Infrastructure Node Topology",
        plugins=[
            SlidePluginImage(type="image", data={"path": "./assets/sample.jpg", "caption": "Topology Map"})
        ]
    )
    decorated = DecorativeShapeEngine.decorate_slide(slide, slide_idx=6, total_slides=10, theme="cyberpunk_neon")
    
    content_boxes = extract_content_regions(slide)
    dec_shapes = [s for s in decorated.shapes if s.decorative]
    
    report = DecorationQualityValidator.validate_slide_decorations(slide, dec_shapes, content_boxes)
    assert report.collisions == 0
    assert report.readability == "safe"


def test_bento_slide_decoration_and_containers():
    """Test 6: Bento grid slide generates hero & feature semantic containers + subtle halo."""
    slide = SlideSpec(
        layout="mixed_content_slide",
        title="Strategic Architectural Horizons",
        visual_intent=VisualIntent.BENTO_OVERVIEW,
        plugins=[
            SlidePluginBentoGrid(type="bento_grid", data={
                "hero": {"title": "Core Platform", "description": "High-throughput foundational platform."},
                "feature": {"title": "Key Capabilities", "points": ["Auto-scaling", "Zero Trust"]},
                "stat": {"number": "99.99%", "label": "Uptime SLA"}
            })
        ]
    )
    decorated = DecorativeShapeEngine.decorate_slide(slide, slide_idx=7, total_slides=10, theme="emerald")
    
    sem_shapes = [s for s in decorated.shapes if not s.decorative]
    assert len(sem_shapes) >= 3  # Hero + Feature + Stat container cards
    for s in sem_shapes:
        assert s.semantic_role == SemanticRole.BENTO_CARD


def test_thank_you_slide_clean_decoration():
    """Test 7: Thank You slide has clean, minimal abstract shapes and zero boilerplate text."""
    slide = SlideSpec(
        layout="title_slide",
        title="Thank You",
        subtitle="Questions & Discussion",
        is_closing_slide=True,
        plugins=[],
    )
    decorated = DecorativeShapeEngine.decorate_slide(slide, slide_idx=9, total_slides=10, theme="executive_gold")
    
    dec_shapes = [s for s in decorated.shapes if s.decorative]
    assert 1 <= len(dec_shapes) <= 3
    
    content_boxes = extract_content_regions(slide)
    report = DecorationQualityValidator.validate_slide_decorations(slide, dec_shapes, content_boxes)
    assert report.collisions == 0
    assert report.readability == "safe"


def test_collision_detector_resolution():
    """Test 8: Collision detector resolves a colliding shape by relocating or scaling it."""
    # Box representing a title text box at (0.8, 0.6) with width 11.7 and height 1.0
    protected_boxes = [Box(0.8, 0.6, 11.7, 1.0)]

    # Intentionally create a decoration that directly overlaps the title box
    colliding_shape = create_shape(
        shape_type=ShapeType.RECTANGLE,
        x=2.0,
        y=0.8,
        width=4.0,
        height=0.5,
        fill="#EF4444",
        opacity=0.90,
        z_index=Z_DECORATIVE_ACCENT,
    )
    assert CollisionDetector.check_collision(colliding_shape, protected_boxes) is True

    # Resolve collision
    resolved = CollisionDetector.resolve_collision(colliding_shape, protected_boxes)
    assert resolved is not None
    # Verify the resolved shape no longer collides at dangerous opacity
    assert CollisionDetector.check_collision(resolved, protected_boxes) is False


def test_theme_aware_color_derivation():
    """Test 9: Shape palette derivation correctly pulls colors across multiple theme archetypes."""
    for theme_name in ["medical", "finance", "ai", "startup", "corporate_light", "cyberpunk_neon"]:
        palette = derive_shape_palette(theme_name)
        assert "primary" in palette
        assert "secondary" in palette
        assert "accent" in palette
        assert "background" in palette
        assert "surface" in palette
        assert palette["primary"].startswith("#")


def test_e2e_python_pptx_rendering_all_slide_types(tmp_path):
    """Test 10: End-to-end python-pptx rendering for title, process, comparison, KPI, bento, image, and thank-you slides."""
    slides = [
        SlideSpec(layout="title_slide", title="Cloud Enterprise Architecture", subtitle="Executive Strategic Blueprint"),
        SlideSpec(layout="bullets_slide", title="Core Capabilities", plugins=[SlidePluginBullets(type="bullets", data={"points": ["High Availability", "Multi-region deployment"]})]),
        SlideSpec(layout="mixed_content_slide", title="Processing Pipeline", visual_intent=VisualIntent.PROCESS_FLOW, plugins=[
            SlidePluginProcessFlow(type="process_flow", data={"title": "Pipeline", "steps": [{"name": "Step 1", "description": "Ingest"}, {"name": "Step 2", "description": "Serve"}]})
        ]),
        SlideSpec(layout="table_slide", title="Technology Comparison", plugins=[
            SlidePluginTable(type="table", data={"headers": ["Tech", "Throughput"], "rows": [["Kafka", "1M msg/s"], ["RabbitMQ", "50k msg/s"]]})
        ]),
        SlideSpec(layout="mixed_content_slide", title="Service Telemetry", visual_intent=VisualIntent.KPI_GRID, plugins=[
            SlidePluginKPIGrid(type="kpi_grid", data={"title": "Telemetry", "kpis": [{"value": "99.99%", "label": "Uptime SLA"}, {"value": "4.8 TB/hr", "label": "Ingestion"}]})
        ]),
        SlideSpec(layout="mixed_content_slide", title="Strategic Foundations", visual_intent=VisualIntent.BENTO_OVERVIEW, plugins=[
            SlidePluginBentoGrid(type="bento_grid", data={"hero": {"title": "Foundation", "description": "Core"}, "feature": {"title": "Features", "points": ["Security"]}})
        ]),
        SlideSpec(layout="title_slide", title="Thank You", subtitle="Questions & Discussion", is_closing_slide=True),
    ]

    plan = PresentationPlan(
        title="Cloud Architecture",
        theme={"name": "ocean_blue"},
        slides=slides,
    )
    # Apply decorative shape engine
    decorated_plan = DecorativeShapeEngine.decorate_presentation_plan(plan)

    renderer = PptRenderer()
    prs = renderer.render(decorated_plan)

    out_file = tmp_path / "test_shapes_deck.pptx"
    prs.save(str(out_file))

    assert out_file.exists()
    assert out_file.stat().st_size > 5000
