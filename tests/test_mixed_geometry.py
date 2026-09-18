from __future__ import annotations

import collections
import collections.abc
import sys
from pathlib import Path

# Forward compatibility fix for python-pptx / collections on Python 3.10+
for name in ("Container", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "Iterable", "Callable"):
    if not hasattr(collections, name) and hasattr(collections.abc, name):
        setattr(collections, name, getattr(collections.abc, name))

from backend.chats.presentation.geometry import MixedLayoutResolver, Box


def test_geometry_resolutions():
    print("[TEST] Testing MixedLayoutResolver layout resolution across plugin combinations...")

    test_combinations = [
        {"paragraph", "image"},
        {"bullets", "chart"},
        {"stat", "paragraph"},
        {"stat", "bullets"},
        {"stat", "chart"},
        {"stat", "image"},
        {"pros_cons", "paragraph"},
        {"pros_cons", "bullets"},
        {"pros_cons", "chart"},
        {"callout", "paragraph"},
        {"roadmap", "bullets"},
        {"code_block", "paragraph"},
        {"speaker_card", "bullets"},
        {"diagram", "paragraph", "bullets"},
        {"image", "chart", "bullets"},
        {"stat", "pros_cons", "bullets", "chart"},
    ]

    for kinds in test_combinations:
        resolved = MixedLayoutResolver.resolve(kinds)
        assert len(resolved) == len(kinds), f"Expected {len(kinds)} resolved boxes, got {len(resolved)} for {kinds}"
        
        # Check collision protection between any pair of boxes
        items = list(resolved.items())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                name1, box1 = items[i]
                name2, box2 = items[j]
                intersects = box1.intersects(box2)
                assert not intersects, f"Collision detected between '{name1}' ({box1}) and '{name2}' ({box2}) in set {kinds}"

        print(f"  [OK] Set {kinds} -> {len(resolved)} boxes resolved cleanly with ZERO collisions.")

    print("[SUCCESS] MixedLayoutResolver geometry test passed with 100% precision!")


if __name__ == "__main__":
    test_geometry_resolutions()
