from __future__ import annotations

import collections
import collections.abc
import sys
from pathlib import Path

# Forward compatibility fix for python-pptx / collections on Python 3.10+
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

from backend.chats.presentation.geometry import FluidGeometrySolver, Box, SLIDE_16_9


def test_fluid_geometry_solver():
    print("[TEST] Testing FluidGeometrySolver dynamic layout calculation...")

    test_plugins_cases = [
        # 1-Item Full Slide
        [{"type": "paragraph", "data": {"text": "Single paragraph content test"}}],
        # 2-Item Side-by-Side Split (Paragraph + Image)
        [
            {"type": "paragraph", "data": {"text": "Left narrative column detail..." * 10}},
            {"type": "image", "data": {"url": "https://example.com/img.jpg"}},
        ],
        # 2-Item Vertical Split (Stat + Bullets)
        [
            {"type": "stat", "data": {"label": "99.9% Uptime"}},
            {"type": "bullets", "data": {"points": ["Point 1", "Point 2", "Point 3", "Point 4"]}},
        ],
        # 3-Item 3-Column Split (Image + Chart + Bullets)
        [
            {"type": "image", "data": {"url": "https://example.com/img.jpg"}},
            {"type": "chart", "data": {"values": [10, 20, 30]}},
            {"type": "bullets", "data": {"points": ["Point A", "Point B"]}},
        ],
        # 4-Item 2x2 Grid
        [
            {"type": "stat", "data": {"label": "99.9%"}},
            {"type": "chart", "data": {"values": [10, 20]}},
            {"type": "pros_cons", "data": {"pros": ["A"], "cons": ["B"]}},
            {"type": "bullets", "data": {"points": ["Item 1"]}},
        ],
        # N-Item Vertical Flow Stack (5 items)
        [
            {"type": "callout", "data": {"text": "Notice"}},
            {"type": "stat", "data": {"label": "99%"}},
            {"type": "paragraph", "data": {"text": "Text"}},
            {"type": "bullets", "data": {"points": ["Bullet"]}},
            {"type": "code_block", "data": {"code": "print('hello')"}},
        ],
    ]

    for idx, plugins in enumerate(test_plugins_cases):
        boxes = FluidGeometrySolver.resolve_fluid(plugins, SLIDE_16_9)
        assert len(boxes) == len(plugins), f"Expected {len(plugins)} boxes, got {len(boxes)}"

        # Check collision protection between any pair of boxes
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                box1 = boxes[i]
                box2 = boxes[j]
                intersects = box1.intersects(box2)
                assert not intersects, f"Collision detected between box {i} ({box1}) and box {j} ({box2}) in test case {idx}"

        print(f"  [OK] Test Case {idx+1} ({len(plugins)} items) -> Resolved {len(boxes)} fluid boxes cleanly with ZERO collisions.")

    print("[SUCCESS] FluidGeometrySolver test passed with 100% precision!")


if __name__ == "__main__":
    test_fluid_geometry_solver()
