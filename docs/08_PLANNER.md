# 08 - Semantic Presentation Planner

The Semantic Planner (`backend/chats/presentation/planner.py`) is the cognitive engine of the presentation pipeline.

---

## 1. Domain Classification & Complexity Analysis

Before generating slide content, `PromptPlanner` analyzes the input user prompt:

1. **Domain Detection (`classify_prompt_domain`)**:
   - Matches prompt keywords against specialized vocabularies: `technology`, `business_pitch`, `medical_health`, `education_academic`, `finance_banking`, `marketing_sales`, `creative_design`.
   - Injects domain-specific layout presets and color palettes based on classification.
2. **Complexity Analysis (`analyze_prompt_complexity`)**:
   - Evaluates input token length, technical density, and requested slide depth.
   - Determines optimal slide count (if unspecified) and balances dense slides (e.g., tables, bento grids) with breathing slides (e.g., quotes, stat cards).

---

## 2. Gemini LLM JSON Schema Synthesis

The planner utilizes Google Gemini (via `backend/chats/services/gemini_service.py`) with structured JSON schema prompting:

- Enforces strict Pydantic parsing against `StructuredPresentationPlan`.
- Instructs the LLM to output semantic intents (`ContentIntent`, `VisualIntent`) rather than raw coordinates.
- Validates slide structures: Title slides, Agenda, Content/Split slides, Data Visualizations, Process/Roadmap flows, Conclusion/Summary.

---

## 3. Deterministic Fallback Planning

If Gemini API limits are exceeded or external network calls fail, `PromptPlanner._generate_fallback_plan()` takes over deterministically:
- Employs regex and rule-based text extractors to segment prompt text into distinct thematic slides.
- Automatically assigns slide types based on keyword heuristics:
  - `"timeline"`, `"history"`, `"phases"` -> `roadmap` / `process_flow`
  - `"metrics"`, `"revenue"`, `"roi"` -> `kpi_grid` / `chart`
  - `"versus"`, `"comparison"`, `"pros and cons"` -> `pros_cons` / `split`
  - `"architecture"`, `"components"`, `"features"` -> `bento_grid`

---

## 4. Boilerplate & AI Instruction Sanitization

- `BoilerplateDetector`: Strips generic AI conversational chatter (e.g., *"Here is a 5-slide presentation on..."*, *"I hope this helps!"*) from generated headers and body paragraphs.
- `clean_ai_instructions`: Removes markdown code fences (` ```json `), trailing asterisks, and system prompts before schema deserialization.