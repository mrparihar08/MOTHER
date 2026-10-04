# 03 - Module Connections & Dependency Matrix

This document maps all inter-module dependencies across the MOTHER backend. Every connection listed below has been verified through AST analysis.

---

## 1. Major Module Dependency Table

| Module | Core Purpose | Internal Modules Imported | Imported By (Callers) | Key Functions / Classes Used |
| :--- | :--- | :--- | :--- | :--- |
| `backend.app.app` | Application bootstrap & router registration | `backend.api.database`, `backend.api.models.vitya`, `backend.api.routes.*`, `backend.api.WebApp.*`, `backend.chats.chat`, `backend.chats.presentation.presentation_api`, `backend.chats.routes.rag_routes`, `backend.dora` | `backend.main` | `FastAPI()`, `lifespan()`, `app.include_router()`, `app.mount()` |
| `backend.api.auth` | JWT token issuance, password reset, and auth guards | `backend.api.database`, `backend.api.models.vitya` | `backend.api.routes.*`, `backend.api.WebApp.*`, `backend.chats.chat`, `backend.chats.presentation.presentation_api` | `create_access_token`, `token_required`, `optional_current_user`, `create_reset_token`, `verify_reset_token` |
| `backend.api.database` | Database connection, pooling, sessionmaker & Base | None | `backend.app.app`, `backend.api.auth`, `backend.api.models.vitya`, `backend.api.routes.*`, `backend.api.WebApp.*`, `backend.chats.chat`, `backend.chats.presentation.presentation_api` | `engine`, `Base`, `SessionLocal`, `get_db()` |
| `backend.api.models.vitya` | SQLAlchemy relational data models | `backend.api.database` | `backend.app.app`, `backend.api.auth`, `backend.api.routes.*`, `backend.api.WebApp.*`, `backend.chats.chat`, `backend.chats.presentation.presentation_api` | `User`, `Income`, `Expense`, `Budget`, `SavingsGoal`, `RecurringSubscription`, `UserSettings`, etc. |
| `backend.api.services.ai_service` | Financial calculations, linear forecasting & scoring | None | `backend.api.routes.ai` | `predict`, `compute_financial_health_score`, `generate_ai_financial_executive_summary` |
| `backend.chats.chat` | Conversational dispatcher & router | `backend.api.auth`, `backend.api.database`, `backend.api.models.vitya`, `backend.chats.handlers.*` | `backend.app.app` | `chat()`, `get_chat_history()`, `create_new_conversation()` |
| `backend.chats.handlers.dora_handler`| Medical symptom intent parsing & DORA dispatch | `backend.dora.engine`, `backend.chats.services.gemini_service` | `backend.chats.chat` | `is_health_query()`, `handle_dora_health()` |
| `backend.chats.handlers.chart_handler`| Generates financial charts from database records | `backend.api.routes.ai`, `backend.api.models.vitya` | `backend.chats.chat` | `handle_chart_request()`, `detect_chart_type()` |
| `backend.chats.handlers.file_handler` | Generates on-the-fly CSV, PDF, and DOCX documents | `backend.chats.utils.document_generators`, `backend.chats.utils.media_and_exports` | `backend.chats.chat` | `handle_file_request()`, `detect_file_type()` |
| `backend.chats.handlers.info_handler` | DuckDuckGo web search and OpenWeather queries | `backend.chats.services.web_search_service`, `backend.chats.utils.openweather_util`, `backend.chats.services.gemini_service` | `backend.chats.chat` | `handle_info_request()` |
| `backend.chats.handlers.news_handler` | News aggregator query dispatcher | `backend.chats.services.news_service` | `backend.chats.chat` | `handle_news_request()` |
| `backend.chats.handlers.transaction_handler`| Natural language income/expense recorder | `backend.api.models.vitya` | `backend.chats.chat` | `handle_transaction()`, `extract_amount()` |
| `backend.chats.presentation.presentation_api` | Presentation generation & management router | `backend.chats.presentation.planner`, `backend.chats.presentation.renderers.ppt_renderer`, `backend.chats.presentation.services.*`, `backend.chats.presentation.exporter`, `backend.chats.presentation.schemas` | `backend.app.app` | `preview_plan()`, `generate_presentation()`, `save_presentation_endpoint()` |
| `backend.chats.presentation.planner` | AI & rule-based presentation planning engine | `backend.chats.presentation.schemas`, `backend.chats.presentation.geometry`, `backend.chats.presentation.shapes`, `backend.chats.services.gemini_service`, `backend.chats.services.web_search_service` | `backend.chats.presentation.presentation_api`, `backend.chats.presentation.exporter`, `backend.chats.presentation.renderers.ppt_renderer` | `PromptPlanner.plan_presentation()`, `BoilerplateDetector` |
| `backend.chats.presentation.renderers.ppt_renderer`| python-pptx rendering engine & 21 plugins | `backend.chats.presentation.geometry`, `backend.chats.presentation.shapes`, `backend.chats.presentation.themes`, `backend.chats.presentation.schemas` | `backend.chats.presentation.presentation_api` | `PptRenderer.render()`, `BasePlugin.render()` |
| `backend.chats.presentation.geometry` | Layout resolution, coordinate bounding boxes & grids | `backend.chats.presentation.schemas` | `backend.chats.presentation.planner`, `backend.chats.presentation.renderers.ppt_renderer` | `MixedLayoutResolver`, `FluidGeometrySolver`, `SlideGeometry`, `Box` |
| `backend.chats.presentation.shapes` | Decorative shapes, badges & collision detection | `backend.chats.presentation.geometry`, `backend.chats.presentation.schemas` | `backend.chats.presentation.planner`, `backend.chats.presentation.renderers.ppt_renderer` | `SemanticShapeEngine`, `DecorativeShapeEngine`, `CollisionDetector` |
| `backend.dora.engine` | Machine learning disease classification | None | `backend.dora.routes`, `backend.chats.handlers.dora_handler` | `KnowledgeEngine.predict()`, `KnowledgeEngine.load_model()` |

---

## 2. Coupling & Architectural Boundary Observations

1. **API -> Chats Coupling**:
   - `backend.chats.chat` imports models directly from `backend.api.models.vitya` and auth from `backend.api.auth`.
   - `backend.chats.handlers.chart_handler` invokes `backend.api.routes.ai` internal helpers.
2. **Presentation Engine Isolation**:
   - The presentation subsystem under `backend/chats/presentation/` operates as a self-contained compiler pipeline with minimal dependencies on the rest of the application (except for `User` model and `auth.py` for user persistence).
3. **No Circular Dependencies**:
   - Automated cycle detection confirmed **0 circular dependencies** in the entire codebase.