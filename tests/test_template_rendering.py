from __future__ import annotations

import collections
import collections.abc
import sys
from pathlib import Path

# Forward compatibility fix for python-pptx / collections on Python 3.10+
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

from backend.chats.presentation.schemas import (
    PresentationPlan,
    SlideSpec,
    SlidePluginText,
    SlidePluginBullets,
    SlidePluginNotes,
)
from backend.chats.presentation.renderers.ppt_renderer import PptRenderer
from backend.chats.presentation.scripts.generate_master_template import create_master_template


from backend.chats.presentation.planner import resolve_template_path
from backend.chats.presentation.scripts.templates import list_available_templates, TEMPLATE_PRESETS


def test_template_rendering():
    print("[TEST] Ensuring Master Slide Template exists...")
    template_path = Path(resolve_template_path("base_template"))
    assert template_path.exists(), "base_template.pptx should exist!"
    print(f"[TEST] Master Template verified at: {template_path}")

    # Build sample 4-slide plan
    slides = [
        SlideSpec(
            layout="title_slide",
            title="AI Revolution in Enterprise",
            subtitle="Building Master-Slide Presentation Systems",
            plugins=[SlidePluginNotes(type="notes", data={"text": "Welcome everyone to today's keynote presentation."})],
        ),
        SlideSpec(
            layout="bullets_slide",
            title="Core Architecture Components",
            subtitle="Key Highlights of the Platform",
            plugins=[
                SlidePluginBullets(
                    type="bullets",
                    data={
                        "points": [
                            "Master Slide Template Engine (.pptx base file)",
                            "Dynamic Structured Output from LLM",
                            "Automatic Layout & Font Scaling Logic",
                            "Native Editable Shapes & Containers",
                        ]
                    },
                )
            ],
        ),
        SlideSpec(
            layout="mixed_content_slide",
            title="Two-Column Comparison Layout",
            subtitle="Comparing Legacy vs Master Slide Approach",
            plugins=[
                SlidePluginBullets(
                    type="bullets",
                    data={
                        "title": "Legacy Approach",
                        "points": ["Draws every shape on blank canvas", "Harder to maintain brand fonts", "No reusable slide masters"],
                        "box": [0.8, 1.5, 5.6, 5.0],
                    },
                ),
                SlidePluginBullets(
                    type="bullets",
                    data={
                        "title": "Master Slide Approach",
                        "points": ["Pre-designed layout templates", "Consistent brand logos & headers", "Fully editable native placeholders"],
                        "box": [6.8, 1.5, 5.6, 5.0],
                    },
                ),
            ],
        ),
        SlideSpec(
            layout="section_slide",
            title="Next Steps & Strategic Roadmap",
            subtitle="Transforming AI Presentation Generation",
            plugins=[SlidePluginText(type="text", data={"text": "Thank you! Q&A Session"})],
        ),
    ]

    plan = PresentationPlan(
        title="AI Revolution in Enterprise",
        theme={"name": "light"},
        slides=slides,
    )

    print("[TEST] Rendering Presentation from Master Template...")
    renderer = PptRenderer(template_file=str(template_path))
    prs = renderer.render(plan)

    # Confirm that dummy template slides were cleared so slide count strictly equals plan slides count
    assert len(prs.slides) == 4, f"Exported PPTX slide count should be 4, got {len(prs.slides)}"

    output_dir = Path("./outputs").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "test_master_slide_output.pptx"

    try:
        prs.save(str(out_file))
    except PermissionError:
        out_file = output_dir / "test_master_slide_output_temp.pptx"
        prs.save(str(out_file))
    assert out_file.exists(), "Output pptx file should be created!"
    print(f"[SUCCESS] Test passed! Presentation saved to: {out_file}")
    print(f"[INFO] Slide Count in exported PPTX: {len(prs.slides)}")


def test_preset_templates_resolution_and_rendering():
    presets_to_test = ["corporate_light", "emerald_nature", "executive_gold", "cyber_neon", "sidebar_executive"]
    for preset_key in presets_to_test:
        path_str = resolve_template_path(preset_key)
        assert Path(path_str).exists(), f"Preset template '{preset_key}' should be resolved and generated!"

        renderer = PptRenderer(template_file=path_str)
        plan = PresentationPlan(
            title=f"Test {preset_key}",
            slides=[
                SlideSpec(layout="title_slide", title="Cover Slide", subtitle="Preset test"),
                SlideSpec(layout="bullets_slide", title="Content Slide", plugins=[SlidePluginBullets(type="bullets", data={"points": ["Point 1", "Point 2"]})]),
            ],
        )
        prs = renderer.render(plan)
        assert len(prs.slides) == 2, f"Rendered preset presentation should have exactly 2 slides, got {len(prs.slides)}"


def test_list_available_templates():
    templates = list_available_templates()
    assert len(templates) == len(TEMPLATE_PRESETS)
    keys = {t["key"] for t in templates}
    assert "corporate_light" in keys
    assert "emerald_nature" in keys
    assert "sidebar_executive" in keys


if __name__ == "__main__":
    test_template_rendering()
    test_preset_templates_resolution_and_rendering()
    test_list_available_templates()

