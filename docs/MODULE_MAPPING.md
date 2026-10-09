# MOTHER Module Mapping & Boundary Definition

**Document Version**: 1.0.0  
**Status**: Comprehensive Codebase Audit (Phase 1)  
**Date**: October 2026  

---

## 1. Overview Matrix

The MOTHER ecosystem consists of 3 dedicated business modules powered by 1 Shared Platform Core. The complete codebase mapping across backend files, database models, API routers, and React frontend components is structured below:

| Dimension | Module 1: Presentation Studio | Module 2: Dora Dr. | Module 3: Vidya F.E.I Advisor | Shared Platform Core |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Domain** | Autonomous PPTX Deck Generation | Clinical Diagnosis & Medical Triage | Finance, Expense, Income & AI Advisory | Authentication, DB, Users, Config |
| **Backend Directory** | `backend/presentation/` | `backend/dora/` | `backend/finance/`, `backend/api/routes/subscriptions.py` | `backend/api/`, `backend/app/`, `backend/chats/` |
| **API Route Prefix** | `/api/presentation` | `/api/dora` | `/api/income`, `/api/expense`, `/api/vitya`, `/api/analyse`, `/api/ai`, `/api/savings`, `/api/subscriptions` | `/api/users`, `/api/settings`, `/api/chat`, `/api/rag`, `/api/notes`, `/api/tasks`, `/api/calendar` |
| **Primary DB Models**| `PresentationBrand` | Stateless / In-Memory (Optional user health logs) | `Income`, `Expense`, `Budget`, `SavingsGoal`, `RecurringSubscription` | `User`, `UserSettings`, `SupportTicket`, `Note`, `Task`, `CalendarEvent`, `Conversation`, `ChatMessage`, `Message` |
| **AI Integrations** | Gemini 1.5/2.0 (Plan/Refine), Pollinations AI, Unsplash, Openverse, Wikimedia | Scikit-Learn TF-IDF Disease Classifier, Gemini 1.5/2.0 (Clinical Triage) | Scikit-Learn Linear Regression, Gemini 1.5/2.0 (Executive Brief & OCR Receipt) | Gemini Gateway (`gemini_service.py`), DuckDuckGo Search, OpenWeather, Edge-TTS |
| **Frontend Location**| `frontend/src/components/presentation/` | `frontend/src/components/apps/DoraHealthApp.jsx` (+ `Drsym-frontend`) | `frontend/src/components/apps/FinanceApp.jsx`, `FinancialHealthApp.jsx`, `AnalyticsApp.jsx`, `SavingsApp.jsx`, `SubscriptionsApp.jsx`, `ChatCharts.jsx` | `frontend/src/components/auth/`, `frontend/src/components/profile/`, `frontend/src/context/`, `frontend/src/components/sidebar/` |

---

## 2. Module 1: Presentation Studio Mapping

### Backend Components
- **API Router**:
  - `backend/presentation/presentation_api.py`: 21 endpoints managing 2-stage planning, compilation, saving, slide rewording, image search, and audio synthesis.
- **Planning Engine**:
  - `backend/presentation/planner.py`: `PromptPlanner`, Gemini structured JSON parser, domain classifier, visual layout selector, and rule-based slide fallback generator.
- **Rendering & Geometry Engine**:
  - `backend/presentation/renderers/ppt_renderer.py`: Slide compiler with 21 modular layout plugins (Charts, Tables, Bento grids, Split layouts, Timelines, etc.).
  - `backend/presentation/geometry.py`: 16:9 widescreen layout coordinate solver (12,192,000 x 6,858,000 EMUs) and collision avoidance.
  - `backend/presentation/shapes.py`: Vector card containers, metric pills, decorative badges.
  - `backend/presentation/themes.py`: 14 designer theme palettes (Modern Dark, Minimal Light, Corporate Blue, Elegant Gold, Cyber Neon, etc.).
  - `backend/presentation/exporter.py`: PPTX template builder and binary stream compiler.
  - `templates/base_template.pptx`: Master widescreen presentation base slide template.
- **Services & Storage**:
  - `backend/presentation/services/presentation_store.py`: In-memory and disk persistence for active presentations.
  - `backend/presentation/services/voiceover_service.py`: Edge-TTS audio generator synthesizing per-slide speech MP3s.
  - `backend/presentation/services/image_manager.py`: Multi-source image retrieval and attribution resolver.
  - `backend/presentation/services/image_search/*`: Openverse, Wikimedia, Unsplash connectors, and CC license verifier.
  - `backend/presentation/services/ai_image_service.py`: Generative image synthesis via Pollinations AI.
  - `backend/presentation/services/cleanup_service.py`: Automated expired deck and audio purger.
  - `backend/presentation/services/security.py`: File path sanitizer preventing traversal attacks.
- **Data Contracts & Schemas**:
  - `backend/presentation/schemas.py`: Pydantic definitions for `PresentationPlan`, `SlideSpec`, and the 21 slide plugins.
  - `backend/api/models/vitya.py`: `PresentationBrand` table (brand logo, colors, font, footer).

### Frontend Components (`frontend/src/components/presentation/`)
- `Presentation.jsx`: Main orchestration container, workflow tabs, state manager.
- `PresentationSetup.jsx`: Creation wizard for topic prompt, target audience, slide count, and visual theme.
- `PresentationStage1Preview.jsx`: Stage 1 slide outline inspector and editor.
- `PresentationEditor.jsx`: Full WYSIWYG canvas presentation editor.
- `editor/`:
  - `SlideCanvas.jsx`: Dynamic slide viewport with zoom and pan controls.
  - `CanvasWorkspace.jsx` & `CanvasElement.jsx`: Individual drag-and-drop slide elements.
  - `SlideSidebar.jsx`: Slide thumbnail strip and slide reordering.
  - `PropertiesPanel.jsx`: Element formatting, font sizes, colors, and layout configurations.
  - `ShapeCatalogModal.jsx`: Vector shapes and decorative containers catalog.
  - `ImageSearchModal.jsx`: Multi-source search modal (Unsplash, Wikimedia, Openverse).
  - `GeminiImageModal.jsx`: AI generative image prompt dialog.
  - `AiRefineModal.jsx` & `AiImageRefineModal.jsx`: Contextual slide rephrasing and image enhancement.
  - `VoiceoverStudioModal.jsx`: Narration voice selection, script adjustment, and audio player.
  - `ExportModal.jsx` & `PresentModal.jsx`: PPTX export options and full-screen presentation mode.
  - `SavedPresentationsModal.jsx`: User presentation library manager.

---

## 3. Module 2: Dora Dr. Mapping

### Backend Components
- **API Router**:
  - `backend/dora/routes.py`: 6 endpoints serving health intelligence, disease predictions, triage chat, risk assessments, and clinical catalogs.
- **Machine Learning Engine**:
  - `backend/dora/engine.py`: `KnowledgeEngine` orchestrating clinical inference, symptom matching, specialist mapping, precautions, and diagnostic test recommendations.
  - `backend/dora/artifacts/disease_model.pkl`: Serialized Scikit-Learn classification model.
  - `backend/dora/artifacts/tfidf_vectorizer.pkl`: Serialized TF-IDF text vectorizer for symptom matching.
  - `backend/dora/artifacts/label_encoder.pkl`: Disease label encoder.
  - `backend/dora/dataset.csv`: Medical training dataset covering 130+ symptoms and 40+ disease categories.
- **Conversational Handler**:
  - `backend/chats/handlers/dora_handler.py`: Chatbot intent dispatcher detecting clinical health queries (`is_health_query`) and executing emergency symptom triage.

### Frontend Components
- `frontend/src/components/apps/DoraHealthApp.jsx`: Complete clinical health suite (1,559 LOC):
  - **Diagnostic Triage**: Interactive symptom selector with 130+ searchable conditions, severity sliders, duration trackers.
  - **Clinical Results Card**: Predicted condition confidence, specialist doctor referral, recommended precautions, and diagnostic lab tests.
  - **Emergency Warning Interceptor**: Prominent emergency hotline badges (112 / 911) for acute red-flag symptoms.
  - **AI Doctor Chat**: Multilingual conversational health guidance supporting English, Hindi (हिन्दी), and Hinglish with speech synthesis.
  - **Health Risk Calculator**: Comprehensive BMI, metabolic profile, and preventative lifestyle guidance.
  - **Clinical Report Export**: Formatted medical report generation with print and download support.
- Specialized Prototype (`DORA/Drsym-frontend`):
  - Interactive clickable 2D human body map (`BodyMap.jsx`), organ category selector (`SymptomCategory.jsx`).

---

## 4. Module 3: Vidya F.E.I Advisor Mapping

### Backend Components
- **Financial Ledgers & Routing**:
  - `backend/finance/routes/expense.py`: Expense creation, pagination, category filtering, updating, deletion (`/api/expense`).
  - `backend/finance/routes/income.py`: Income stream logging, source categorizing, updating, deletion (`/api/income`).
  - `backend/finance/routes/vitya.py`: Financial overview aggregation, CSV ledger exports, trend metrics, Matplotlib chart generator (`/api/vitya`).
  - `backend/finance/analysis/savings.py`: Savings target management and progress deposits (`/api/savings`).
  - `backend/api/routes/subscriptions.py`: Recurring subscription management, billing cycle forecasting (`/api/subscriptions`).
- **AI Financial Intelligence**:
  - `backend/finance/analysis/analyse.py`: Linear regression expense projection (`_fit_and_predict_linear_model`), overspending detection, 2x std-dev spending anomaly detection, waste analysis, monthly budget caps, budget alerts (`/api/analyse` and `/api/ai`).
  - `backend/api/services/ai_service.py`: 0–100 composite Financial Health Score calculation (`compute_financial_health_score`) and Gemini fiduciary executive briefing (`generate_ai_financial_executive_summary`).
  - `backend/chats/services/receipt_service.py`: Multimodal Gemini receipt OCR and itemized transaction extraction.
- **Chat Handlers**:
  - `backend/chats/handlers/transaction_handler.py`: NLP-driven transaction logging directly from chat conversation.
  - `backend/chats/handlers/chart_handler.py`: Dynamic chart payload generation for financial visualizations.
  - `backend/chats/handlers/receipt_handler.py`: Image receipt scan handler.
- **Database Models** (`backend/api/models/vitya.py`):
  - `Expense`, `Income`, `Budget`, `SavingsGoal`, `RecurringSubscription`.

### Frontend Components
- `frontend/src/components/apps/FinanceApp.jsx`: Double-entry income and expense tracker, transaction table, Recharts breakdown.
- `frontend/src/components/apps/FinancialHealthApp.jsx`: AI Financial Health Score gauge (0–100), Gemini executive summary cards, budget caps manager, overspending alerts, waste analysis.
- `frontend/src/components/apps/SavingsApp.jsx`: Savings goals cards, target milestones, deposit modal.
- `frontend/src/components/apps/SubscriptionsApp.jsx`: Recurring subscriptions tracker, renewal calendar, annual cost projections.
- `frontend/src/components/apps/AnalyticsApp.jsx`: Interactive activity trends, category comparison charts.
- `frontend/src/components/chatbot/ChatCharts.jsx`: In-chat interactive financial charts.

---

## 5. Shared Platform Core Mapping

### Backend Components
- **Authentication & Authorization**:
  - `backend/api/auth.py`: JWT token generation, password hashing (Passlib/Bcrypt), route dependencies (`token_required`, `optional_current_user`).
  - `backend/api/routes/users.py`: Registration, login, profile editing, password resets, support ticket submission, GDPR data dump.
- **User Settings & Preferences**:
  - `backend/api/routes/settings.py`: UI theme, accent colors, AI model preferences, password changes, subscription plans.
- **Database Engine**:
  - `backend/api/database.py`: SQLAlchemy connection factory, engine configuration, SQLite/PostgreSQL pooling, `get_db` session manager.
  - `backend/api/models/vitya.py`: `User`, `UserSettings`, `SupportTicket`.
- **AI Gateway & RAG**:
  - `backend/chats/services/gemini_service.py`: Centralized Google Gemini client with token limiters and error retries.
  - `backend/chats/services/rag_service.py` & `backend/chats/routes/rag_routes.py`: Semantic document chunking, in-memory RAG document index.
  - `backend/chats/services/web_search_service.py`: DuckDuckGo real-time web search.
  - `backend/chats/services/wikipedia_service.py`: MediaWiki knowledge lookup.
  - `backend/chats/utils/openweather_util.py`: Real-time weather integration.
- **Shared Productivity**:
  - `backend/api/WebApp/notes.py` (`Note` model): Scratchpad and markdown note-taking.
  - `backend/api/WebApp/tasks.py` (`Task` model): Todo checklist manager.
  - `backend/api/WebApp/calendar.py` (`CalendarEvent` model): Event and schedule calendar.
- **Agent Chat & Dispatch**:
  - `backend/chats/chat.py`: Central conversational entrypoint coordinating intent classification across Dora, Finance, Web Search, and General AI.
  - `backend/chats/chatbot.py`: Rule-based intent matchers and contextual prompt builder.
  - `backend/chats/utils/intent_router.py`: Keyword and semantic intent classifier.

### Frontend Components
- **Authentication Shell**:
  - `frontend/src/context/AuthContext.jsx`: Session state, JWT storage, auto-logout on 401.
  - `frontend/src/components/auth/`: `Login.jsx`, `Register.jsx`, `ForgotPassword.jsx`, `ResetPassword.jsx`, `Profile.jsx`, `ProfileEdit.jsx`.
- **System Settings & Appearance**:
  - `frontend/src/context/ThemeContext.jsx`: Dark/light mode theme provider.
  - `frontend/src/components/profile/`: `SettingsPage.jsx`, `SecurityPrivacyPage.jsx`, `AppearancePage.jsx`, `NotificationsPage.jsx`, `SubscriptionPage.jsx`, `AboutPage.jsx`, `HelpSupportPage.jsx`.
- **Workspace Navigation & Shared UI**:
  - `frontend/src/App/Dashboard.jsx`: Primary desktop layout, active app switcher, search command bar.
  - `frontend/src/components/sidebar/Sidebar.jsx`: Collapsible navigation sidebar.
  - `frontend/src/components/common/CommandPalette.jsx`: Quick search (`Ctrl+K` / `Cmd+K`) across apps and actions.
  - `frontend/src/services/api.js`: Unified Axios client with automatic Bearer token interceptor and error formatting.

---

## 6. Resolved Specifications & Operational Assumptions
 
### 1. F.E.I Clarification (RESOLVED)
- **Specification**: **F.E.I** officially denotes **Finance, Expense, Income & Intelligence**.
- **Implementation**: The module encapsulates financial overview, cashflow tracking, income streams, expense ledger with category caps, spending waste detection, 2x std-dev anomaly alerts, receipt OCR scanning, savings goals, recurring subscription forecasting, and 0–100 Financial Health Score. All predictions explicitly communicate non-guaranteed advisory status.
 
### 2. Frontend Repository Housing (RESOLVED)
- **Specification**: The React frontend is housed directly at `frontend/` within the MOTHER repository root (`c:\Users\preet\OneDrive\Desktop\MOTHER\frontend`), matching `render.yaml`.
- **Implementation**: Production build compiles with zero errors (`build/` generated successfully). Direct deep-link routing enabled for `/presentation`, `/dora`, and `/finance` / `/fei`.
 
### 3. Dora Dr. Model Loading (RESOLVED)
- **Specification**: Offline Scikit-Learn clinical models (`disease_model.pkl`, `tfidf_vectorizer.pkl`, `label_encoder.pkl`) are pre-trained and serialized in `backend/dora/artifacts/`.
- **Implementation**: `KnowledgeEngine` checks for pre-trained disk artifacts and loads them directly via `joblib.load()` with Windows file-locking guards, avoiding startup training latencies and memory write contention.
