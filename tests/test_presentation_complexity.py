import pytest
from backend.chats.presentation.planner import analyze_prompt_complexity, PromptPlanner, PRESET_SLIDE_COUNTS

def test_analyze_prompt_complexity_presets():
    # 1. Very simple prompt -> 6 slides
    count_simple = analyze_prompt_complexity("Quick summary of Python")
    assert count_simple == 6

    # 2. Standard prompt -> 8 slides
    count_std = analyze_prompt_complexity("Overview of Python Programming for beginners with features and examples")
    assert count_std == 8

    # 3. Moderate topic -> 10 slides
    count_mod = analyze_prompt_complexity("Detailed overview of Python web frameworks, performance, and API design principles")
    assert count_mod == 10

    # 4. Technical / Deep Dive topic -> 15 slides
    count_tech = analyze_prompt_complexity("Deep dive into Microservices Architecture with Docker, Kubernetes, Database Sharding, API Gateway, and Security")
    assert count_tech == 15

    # 5. Advanced / Enterprise topic -> 20 slides
    count_adv = analyze_prompt_complexity(
        "Enterprise Cloud Migration strategy covering multi-region deployment, disaster recovery, zero-trust security, and cost optimization"
    )
    assert count_adv == 20

    # 6. Multi-module curriculum topic -> 25 slides
    count_curr = analyze_prompt_complexity(
        "Exhaustive masterclass curriculum for full stack web development: frontend React, backend FastAPI, PostgreSQL databases, devops pipelines, cloud deployment, security audit, and microservices"
    )
    assert count_curr == 25

    # 7. Explicit 30-slide request -> 30 slides
    count_30 = analyze_prompt_complexity("Complete end-to-end 30-slide presentation masterclass on Artificial Intelligence")
    assert count_30 == 30

    # All returned slide counts must strictly be in PRESET_SLIDE_COUNTS
    assert count_simple in PRESET_SLIDE_COUNTS
    assert count_std in PRESET_SLIDE_COUNTS
    assert count_mod in PRESET_SLIDE_COUNTS
    assert count_tech in PRESET_SLIDE_COUNTS
    assert count_adv in PRESET_SLIDE_COUNTS
    assert count_curr in PRESET_SLIDE_COUNTS
    assert count_30 in PRESET_SLIDE_COUNTS


def test_prompt_planner_preset_counts():
    planner = PromptPlanner()

    # Test that PromptPlanner generates exact preset counts when requested or auto-analyzed
    for target in PRESET_SLIDE_COUNTS:
        plan = planner.plan(
            f"Test topic preset count test",
            target_slide_count=target
        )
        assert len(plan.slides) == target
