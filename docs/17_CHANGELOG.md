# 17 - Backend Architectural Changelog

This changelog records the architectural evolution and major milestones of the MOTHER backend.

---

### [v2.4.0] - DORA Medical ML & Edge-TTS Voiceover Engine
- Integrated DORA (Diagnostic Operational Research Assistant) offline symptom diagnosis using scikit-learn models.
- Added Microsoft Edge-TTS integration for automated slide voiceover generation.
- Added multi-source image search pipeline (Openverse, Wikimedia Commons, Unsplash, Pollinations AI).

### [v2.0.0] - Two-Stage Presentation Design Compiler
- Refactored presentation generation into a strict 2-stage compiler pipeline (`PromptPlanner` -> `PptRenderer`).
- Built 21 modular presentation plugins (Bento grids, KPI cards, Timelines, Split layouts, Pros/Cons, Code blocks).
- Integrated `FluidGeometrySolver` and `CollisionDetector` to eliminate shape-text collisions.
- Added 14 responsive presentation theme presets with automated contrast ratio checking.

### [v1.5.0] - AI Financial Intelligence & Health Scoring
- Implemented linear regression expense forecasting (`backend/api/services/ai_service.py`).
- Added financial health score (0-100) computation and AI executive financial summaries via Google Gemini.
- Added savings goals and recurring subscription management.

### [v1.0.0] - Core Vitya AI Backend Launch
- Initial release of FastAPI application with PostgreSQL / SQLite support.
- Implemented JWT authentication, user registration, profile editing, and password reset workflows.
- Built core income, expense, notes, tasks, and calendar event management endpoints.