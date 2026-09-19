from __future__ import annotations

import collections
import collections.abc
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

from backend.chats.presentation.schemas import PresentationPlan, SlideSpec, SlidePluginBullets
from backend.chats.presentation.renderers.ppt_renderer import PptRenderer

def test_ribbon_properties_rendering():
    slides = [
        SlideSpec(
            layout="title_slide",
            title="Ribbon Integration Test",
            subtitle="Testing Custom Fonts and Alignments",
            font_family="Georgia",
            title_color="#EC4899",
            title_align="center",
            effect="subtle-glow",
            card_effect="gradient",
            plugins=[
                SlidePluginBullets(
                    type="bullets",
                    data={
                        "points": ["Point A", "Point B", "Point C"]
                    }
                )
            ]
        )
    ]

    plan = PresentationPlan(
        title="Ribbon Integration Test",
        font_family="Georgia",
        effect="subtle-glow",
        card_effect="gradient",
        slides=slides
    )

    renderer = PptRenderer()
    prs = renderer.render(plan)
    assert len(prs.slides) == 1
    print("SUCCESS: Ribbon properties successfully parsed and rendered into PPTX!")

if __name__ == "__main__":
    test_ribbon_properties_rendering()
