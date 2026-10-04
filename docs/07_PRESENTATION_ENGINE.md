# 07 - Presentation Generation Engine

The Presentation Generation Engine in MOTHER is an enterprise-grade slide design compiler that transforms natural language prompts into formatted Microsoft PowerPoint (`.pptx`) presentations.

---

## 1. Two-Stage Compilation Architecture

The engine decouples semantic layout planning from visual drawing through a strict two-stage compilation pipeline:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                STAGE 1: SEMANTIC PLANNING                              │
│                                                                                        │
│  User Request (Prompt, Count, Theme, Style)                                            │
│        │                                                                               │
│        ▼                                                                               │
│  PromptPlanner (planner.py)                                                            │
│        ├── Domain Classification & Complexity Analysis                                 │
│        ├── Gemini LLM JSON Schema Synthesis                                            │
│        ├── Rule-Based Deterministic Fallback Engine                                    │
│        ├── Agenda & Content Structuring                                                │
│        └── Image Resolution via ImageManager (Unsplash, Openverse, Wikimedia)          │
│        │                                                                               │
│        ▼                                                                               │
│  StructuredPresentationPlan / PresentationPlan (JSON Specification)                    │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ (Enriched JSON Specification)
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                             STAGE 2: LAYOUT RESOLUTION & RENDERING                     │
│                                                                                        │
│  Layout Specification & Spatial Solving (geometry.py)                                  │
│        ├── MixedLayoutResolver & FluidGeometrySolver                                   │
│        ├── Dynamic Grid System & Bounding Box Conflict Detection                       │
│        └── Safe Margin & Content Height/Width Solvers                                  │
│        │                                                                               │
│        ▼                                                                               │
│  Decorative & Semantic Shape Injection (shapes.py)                                     │
│        ├── SemanticShapeEngine (KPI Cards, Metric Badges, Process Arrows)              │
│        ├── DecorativeShapeEngine (Subtle background cards, accent stripes)             │
│        └── CollisionDetector (Guarantees zero overlap with content boxes)              │
│        │                                                                               │
│        ▼                                                                               │
│  Theme & Color Palette Resolution (themes.py & templates.py)                           │
│        ├── Contrast Ratio Calculation (WCAG AA Compliance: Luminance >= 4.5:1)         │
│        └── Theme Palette Binding (14 Preset Theme Palettes + Brand Overrides)          │
│        │                                                                               │
│        ▼                                                                               │
│  PPTX Compilation Engine (renderers/ppt_renderer.py)                                   │
│        ├── Master Slide Template Loader (generate_master_template.py)                  │
│        ├── 21 Presentation Element & Layout Plugins                                    │
│        └── python-pptx Native Drawing & Shape Geometry Injection                       │
│        │                                                                               │
│        ▼                                                                               │
│  Output File Generation (exporter.py) -> outputs/<uuid>.pptx                           │
│        └── Optional Slide Voiceover Narration Synthesis via Edge-TTS                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Geometry & Spatial Layout System (`backend/chats/presentation/geometry.py`)

- **Standard Widescreen Dimensions**: 16:9 Aspect Ratio (13.333 inches width $	imes$ 7.5 inches height = 12,192,000 $	imes$ 6,858,000 EMUs).
- **Core Classes**:
  - `SlideGeometry`: Defines slide boundaries, margins (left, right, top, bottom), header reservation, and footer reservation.
  - `Box`: Immutable 2D rectangle model (`left`, `top`, `width`, `height`) supporting intersection tests, shrink/expand transforms, and grid partitioning.
  - `FluidGeometrySolver`: Dynamically allocates variable width/height columns based on content weight.
  - `MixedLayoutResolver`: Maps high-level slide types (`split_left_image`, `bento_grid`, `kpi_cards`, `process_horizontal`) into concrete `Box` collections.
  - `TemplateDetector`: Inspects existing template placeholders to map dynamic content directly into pre-authored slide masters.

---

## 3. Shape & Collision System (`backend/chats/presentation/shapes.py`)

- **Visual Roles**:
  - `CONTAINER`: Background bounding card encapsulating text/charts.
  - `ACCENT`: Edge highlights, gradient bars, category tags.
  - `METRIC_CARD`: Elevated KPI container with numeric badge.
  - `CONNECTOR`: Directional arrows in process flows and timelines.
- **Collision Detection**:
  - `CollisionDetector.find_safe_regions()` computes unoccupied polygonal regions on a slide and rejects decorative shapes that overlap text bounding boxes by even 1%.
- **Validation**:
  - `DecorationQualityValidator` evaluates slide aesthetic density, enforcing maximum limits (e.g., no more than 4 decorative accents per slide) to prevent visual clutter.

---

## 4. Color & Typography Theming System (`backend/chats/presentation/themes.py`)

- **Contrast Checking**: `calculate_contrast_ratio(rgb1, rgb2)` uses relative luminance formulas to ensure foreground text is always legible against solid or container backgrounds.
- **Dynamic Inversion**: If a dark theme card is rendered on a light background, `ensure_readable_text_color()` automatically inverts font colors.
- **14 Built-in Themes**:
  - `ion` (Tech / Cyber), `berlin` (Modern Corporate), `quotable` (Editorial / Bold), `geometric` (Modern Minimalist), `crop` (Vibrant Startup), `atlas` (Executive Navy), `dividend` (Finance / Forest Green), `savon` (Warm Organic), `wood` (Earthy Classic), `artistic` (Creative Coral), `circuit` (Deep Dark Tech), `celestial` (Midnight Violet), `glassmorphism` (Translucent Soft Dark), `default` (Clean Slate).