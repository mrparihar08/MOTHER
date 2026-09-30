import pytest
from backend.chats.presentation.schemas import (
    PresentationPlan,
    SlideSpec,
    SlidePluginParagraph,
    SlidePluginBullets,
    SlidePluginStat,
    SlidePluginBentoGrid,
    SlidePluginProcessFlow,
    SlidePluginKPIGrid,
    SlidePluginTable,
    VisualIntent,
    MetricSpec,
)
from backend.chats.presentation.planner import (
    extract_contextual_metrics,
    detect_visual_intent,
    consolidate_redundant_slides,
    PromptPlanner,
)


def test_metric_anchoring_no_fabrication():
    """Verify that MetricSpec extracts metrics authentically without manufacturing fake benchmarks or sources."""
    text = "4.8 TB/hr Large-Scale Ingestion Rate [Gartner 2024]\n99.99% Core Service Uptime SLA"
    metrics = extract_contextual_metrics(text, slide_title="Data Architecture Benchmarks")
    
    assert len(metrics) == 2
    m1 = metrics[0]
    assert "4.8 TB/hr" in m1.value
    assert "Ingestion" in m1.label
    assert m1.source == "Gartner 2024"
    assert m1.baseline is None
    assert m1.is_verified is True

    m2 = metrics[1]
    assert "99.99%" in m2.value
    assert "Uptime" in m2.label
    assert m2.source is None
    assert m2.baseline is None


def test_metric_anchoring_single_stat():
    """Verify single metric extraction without inventing '+12x faster'."""
    text = "Stat: 4.8 TB/hr | High Throughput Streaming Pipeline"
    metrics = extract_contextual_metrics(text, slide_title="Data Science Ingestion")
    
    assert len(metrics) == 1
    assert metrics[0].value == "4.8 TB/hr"
    assert metrics[0].label == "High Throughput Streaming Pipeline"
    assert "12x" not in str(metrics[0].impact)  # Ensure no hallucinated "+12x"


def test_visual_intent_detection():
    """Verify deterministic visual intent classification across different content patterns."""
    # 1. PROCESS_FLOW
    intent_proc = detect_visual_intent(
        content="Raw Data ➔ ETL ➔ Feature Engineering ➔ Model Training ➔ Inference API",
        title="End-to-End Machine Learning Pipeline"
    )
    assert intent_proc == VisualIntent.PROCESS_FLOW

    # 2. COMPARISON
    intent_comp = detect_visual_intent(
        content="Supervised learning uses labeled training datasets versus unsupervised learning finding latent patterns.",
        title="Supervised vs Unsupervised Learning"
    )
    assert intent_comp == VisualIntent.COMPARISON

    # 3. KPI_GRID
    intent_kpi = detect_visual_intent(
        content="Key Performance Indicators: 99.9% Uptime, 250ms Latency, 500k Active Users",
        title="Operational Telemetry & Performance Metrics"
    )
    assert intent_kpi == VisualIntent.KPI_GRID

    # 4. TIMELINE
    intent_timeline = detect_visual_intent(
        content="Historical Evolution: Paramara Era ➔ Nawabi Era ➔ Post-Independence ➔ Modern Capital",
        title="Evolutionary Milestones & City History"
    )
    assert intent_timeline == VisualIntent.TIMELINE

    # 5. SPLIT_PROBLEM_SOLUTION
    intent_split = detect_visual_intent(
        content="Data silo fragmentation and slow manual ETL workflows vs automated unified data fabric architecture.",
        title="Problem vs Solution: Enterprise Modernization"
    )
    assert intent_split == VisualIntent.SPLIT_PROBLEM_SOLUTION

    # 6. BENTO_OVERVIEW
    intent_bento = detect_visual_intent(
        content="Core foundation overview and fundamental pillars of distributed architecture.",
        title="Introduction & Architectural Overview"
    )
    assert intent_bento == VisualIntent.BENTO_OVERVIEW


def test_slide_consolidation_intro_redundancy():
    """Verify that redundant continuation intro slides are merged into a single Bento Grid slide."""
    slide1 = SlideSpec(
        layout="title_content",
        title="Introduction to Data Science",
        plugins=[
            SlidePluginParagraph(type="paragraph", data={"text": "Data Science transforms raw organizational data into actionable intelligence."}),
            SlidePluginBullets(type="bullets", data={"points": ["Statistical modeling", "Scalable data engineering", "Domain expertise"]}),
        ]
    )
    slide2 = SlideSpec(
        layout="bullets_slide",
        title="Why Data Science Matters",
        plugins=[
            SlidePluginBullets(type="bullets", data={"points": ["Automates high-stakes decision making", "Unlocks predictive capabilities", "Drives continuous operational optimization"]}),
        ]
    )

    plan = PresentationPlan(title="Modern Data Science", slides=[slide1, slide2])
    consolidated = consolidate_redundant_slides(plan)

    assert len(consolidated.slides) == 1
    merged = consolidated.slides[0]
    assert merged.layout == "mixed_content_slide"
    assert merged.visual_intent == VisualIntent.BENTO_OVERVIEW
    assert len(merged.plugins) == 1
    assert isinstance(merged.plugins[0], SlidePluginBentoGrid)
    
    bento_data = merged.plugins[0].data
    assert "hero" in bento_data
    assert "feature" in bento_data
    assert "Data Science" in merged.title


def test_slide_consolidation_part1_part2():
    """Verify that Part 1 and Part 2 slides are consolidated."""
    slide1 = SlideSpec(
        layout="bullets_slide",
        title="Scalable Infrastructure (Part 1)",
        plugins=[SlidePluginBullets(type="bullets", data={"points": ["Kubernetes cluster orchestration", "Multi-region service mesh"]})]
    )
    slide2 = SlideSpec(
        layout="bullets_slide",
        title="Scalable Infrastructure (Part 2)",
        plugins=[SlidePluginBullets(type="bullets", data={"points": ["Automated horizontal pod auto-scaling", "Edge CDN caching layer"]})]
    )

    plan = PresentationPlan(title="Cloud Architecture", slides=[slide1, slide2])
    consolidated = consolidate_redundant_slides(plan)

    assert len(consolidated.slides) == 1
    assert "Part" not in consolidated.slides[0].title


def test_prompt_planner_process_flow_pipeline():
    """Test full PromptPlanner flow on a process flow slide."""
    planner = PromptPlanner()
    script = """Slide 1:
Title: Data Engineering Architecture
Subtitle: High-Throughput Pipelines

Slide 2:
Title: End-to-End Ingestion Pipeline
Diagram: Raw Data Ingestion ➔ ETL Preprocessing ➔ Feature Engineering ➔ Model Training ➔ Inference API
Bullets:
- Real-time event streaming ingestion
- Distributed feature computation
- Automated model inference serving

Slide 3:
Title: Conclusion
Bullets:
- High reliability infrastructure
- Seamless production deployment"""

    plan = planner.plan(script)
    assert len(plan.slides) >= 3
    # Check slide 2 has process flow plugin or diagram
    slide2 = plan.slides[1]
    plugin_types = [p.type for p in slide2.plugins]
    assert "process_flow" in plugin_types or "diagram" in plugin_types


def test_prompt_planner_kpi_grid():
    """Test full PromptPlanner flow on KPI metrics slide."""
    planner = PromptPlanner()
    script = """Slide 1:
Title: System Performance Overview
Subtitle: Q4 Engineering SLA

Slide 2:
Title: Core Telemetry & Performance Metrics
Stat: 99.99% | Service Availability SLA
Stat: 4.8 TB/hr | Peak Ingestion Rate
Stat: 45ms | P99 API Response Latency

Slide 3:
Title: Conclusion
Bullets:
- Exceeded all quarterly performance SLAs"""

    plan = planner.plan(script)
    assert len(plan.slides) >= 3
    slide2 = plan.slides[1]
    plugin_types = [p.type for p in slide2.plugins]
    assert "kpi_grid" in plugin_types or "stat" in plugin_types
