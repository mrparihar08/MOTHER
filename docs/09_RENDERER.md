# 09 - Presentation PPTX Renderer

The `PptRenderer` (`backend/chats/presentation/renderers/ppt_renderer.py`) is the physical rendering compiler that transforms a `PresentationPlan` into a native `.pptx` presentation.

---

## 1. Renderer Architecture & Lifecycle

```
PresentationPlan
      │
      ▼
PptRenderer.render()
      │
      ├── 1. Initialize python-pptx Presentation(master_template.pptx)
      ├── 2. Apply 16:9 Widescreen Dimension Constraints (12.19M x 6.85M EMUs)
      ├── 3. Iterate over each SlideSpec in Plan:
      │       ├── A. Add Slide with designated layout index
      │       ├── B. Draw Slide Background (Solid / Gradient Card)
      │       ├── C. Draw Header, Category Tag, & Footer Notes
      │       ├── D. Compute Spatial Grid via MixedLayoutResolver
      │       ├── E. Render Decorative Visual Shapes via ShapePlugin
      │       ├── F. Dispatch Element Plugins (Chart, Table, Bento, KPI, etc.)
      │       └── G. Inject Presenter Notes into Slide Notes Slide
      └── 4. Return compiled Presentation object to Exporter
```

---

## 2. Text Frame & Typography Solver

- `calculate_title_font_size(title_text)`: Dynamically computes title point size (36pt down to 22pt) to prevent multi-line overflow.
- `configure_text_frame(tf)`: Enforces zero internal margins, auto-wrapping (`tf.word_wrap = True`), and proper line spacing.
- `set_run_style(run, font_name, size_pt, color_rgb, bold, italic)`: Guarantees consistent typography across all shapes and cards.

---

## 3. Placeholder Discovery & Safe Fallbacks

`PptRenderer` implements robust placeholder discovery:
- `find_placeholder_by_types(slide, [PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE])` locates native template placeholders.
- If placeholders are missing or corrupt, `write_text_or_fallback()` dynamically creates a free-standing textbox with verified geometric bounds.