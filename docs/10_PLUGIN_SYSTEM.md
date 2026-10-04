# 10 - Presentation Plugin System

The rendering pipeline utilizes 21 specialized content plugins inheriting from `BasePlugin` (`backend/chats/presentation/renderers/ppt_renderer.py`).

---

## 1. Plugin Catalog & Specifications

| Plugin Class | Target Slide / Element | Visual Output & Layout Behavior |
| :--- | :--- | :--- |
| `BasePlugin` | Abstract Base | Defines lifecycle `render(slide, spec, box, theme)` and helper drawing utilities |
| `TextPlugin` | Headline / Single Text | Renders clean hero text or central quote with bold styling |
| `ParagraphPlugin` | Standard Text Body | Multi-line structured body text with auto-line height |
| `Paragraph2ColPlugin` | 2-Column Text | Splits content into two balanced columns with gutter separation |
| `BulletsPlugin` | Bulleted Lists | Custom styled bullet points with accent colored bullet marks |
| `ChartPlugin` | Charts & Graphs | Native PowerPoint Bar, Column, Line, and Pie charts via `python-pptx.chart` |
| `TablePlugin` | Tabular Data | Alternating row colored table with bold header row and cell alignment |
| `ImagePlugin` | Photography / Visuals | Downloaded image inserted into container box with aspect-ratio preserving crop |
| `StatPlugin` | Hero Statistics | Giant numeric callout (60pt+) with subscript description card |
| `CalloutPlugin` | Highlighted Notice | Distinct background card with accent left border and warning/info badge |
| `KPIGridPlugin` | 2x2 or 1x4 KPI Cards | Grid of elevated metric cards with individual progress badges |
| `ProsConsPlugin` | Comparison Matrix | Side-by-side green (Pros) and red/neutral (Cons) evaluation cards |
| `RoadmapPlugin` | Horizontal Milestones | Step-by-step milestone cards connected by an accent milestone arrow bar |
| `ProcessFlowPlugin` | Step-by-Step Flow | Numbered process steps (1, 2, 3, 4) with transition connectors |
| `BentoGridPlugin` | Modern Bento Layout | Multi-cell asymmetric cards (1 large hero cell + 2-3 supporting cells) |
| `SplitLayoutPlugin`| 50/50 Split Slide | Half slide visual/image and half slide structured text/bullets |
| `SpeakerCardPlugin`| Speaker / Team Bio | Avatar container, speaker name, designation badge, and social handles |
| `CodeBlockPlugin` | Source Code Listing | Dark IDE background card (`#1e1e1e`), monospaced font, line numbers |
| `DiagramPlugin` | Conceptual Diagram | Visual hierarchy nodes and relationship links |
| `ShapePlugin` | Visual Primitives | Draws geometric badges, decorative cards, and accent stripes |
| `NotesPlugin` | Slide Presenter Notes| Injects presentation script into the PPTX slide notes section |

---

## 2. Plugin Execution Lifecycle

1. `can_handle(element_spec)` checks if plugin matches element `type`.
2. `resolve_box(grid_box)` maps target spatial coordinates.
3. `draw_background(slide, box, theme)` creates container card shape.
4. `draw_content(slide, box, spec, theme)` populates text, shapes, or native charts.
5. `apply_accents(slide, box, theme)` attaches subtle icon or category badge.