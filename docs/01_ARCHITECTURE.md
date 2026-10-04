# 01 - Backend Architecture Overview

## 1. High-Level Architectural Paradigm
The MOTHER backend is built upon **FastAPI (ASGI)**, utilizing a modular, multi-domain service-oriented architecture. The system integrates real-time personal finance management, conversational agent capabilities with retrieval-augmented generation (RAG), machine learning disease diagnostics (DORA), and an automated PowerPoint presentation design and rendering engine.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   ENTRYPOINT LAYER                                     │
│  backend/main.py -> Uvicorn ASGI Runner -> backend/app/app.py:app                      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                             MIDDLEWARE & SECURITY LAYER                                │
│  - CORSMiddleware (Configurable origins, Regex localhost/Render matching)               │
│  - JWT Bearer Authentication (HS256 Token Validation, auto_error=False)                │
│  - Lifespan Context Manager (SQLAlchemy metadata auto-table creation)                  │
│  - Static Mounts: /uploads, /assets                                                    │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                                 ROUTER / DISPATCH LAYER                                │
│  ├── /api/users          (Auth, Profile, Password Reset, GDPR Data Export)             │
│  ├── /api/income         (Income Stream CRUD)                                          │
│  ├── /api/expense        (Expense Transaction CRUD)                                    │
│  ├── /api/vitya          (Financial Charts, CSV Exports, Trend Analytics)              │
│  ├── /api/ai             (Linear AI Prediction, Anomaly, Budget Caps, Health Score)    │
│  ├── /api/chat           (Conversational Agent, Intent Router, Multi-Handler Dispatch) │
│  ├── /api/rag            (Document Ingestion, Chunking, In-Memory RAG Store)           │
│  ├── /api/presentation   (2-Stage Presentation Generator, Shapes, Voiceover)           │
│  ├── /api/notes          (Quick Note Storage CRUD)                                     │
│  ├── /api/tasks          (Task Management CRUD)                                        │
│  ├── /api/calendar       (Calendar Events CRUD)                                        │
│  ├── /api/settings       (Theme, UI Preferences, Subscriptions, Password Management)   │
│  ├── /api/savings        (Savings Goals, Progress Tracking, Deposits)                  │
│  ├── /api/subscriptions  (Recurring Subscriptions Management & Forecasting)            │
│  └── /api/dora           (DORA Health ML Symptoms Analysis & Diagnosis)                │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                           SERVICES & PROCESSING ENGINES                                │
│  ├── Finance Analytics: ai_service.py (Linear Regression, Health Score, Health Advisory)│
│  ├── Chat Handlers: Intent classifier -> Dora, File, News, Wiki, Chart, Transaction    │
│  ├── Presentation Engine: PromptPlanner -> GeometrySolver -> PptRenderer -> Plugins    │
│  ├── Image Discovery: UnsplashService, Openverse, Wikimedia, AIImageService            │
│  ├── Medical ML Engine: KnowledgeEngine (TF-IDF Vectorizer + Classifier Artifacts)     │
│  └── Voiceover Synthesizer: Edge-TTS slide audio generation                            │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                              PERSISTENCE & STORAGE LAYER                               │
│  ├── Database: PostgreSQL (Supabase / Render) with SQLite Fallback (SQLAlchemy ORM)    │
│  ├── Model Store: In-memory presentation cache (PresentationStore)                     │
│  ├── Disk Storage: outputs/, uploads/, assets/                                         │
│  └── Artifact Storage: dora/artifacts/*.pkl (Disease Models)                           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Subsystems

### A. Vitya Personal Finance & Productivity Subsystem
- **Modules**: `backend/api/routes/*`, `backend/api/models/vitya.py`, `backend/api/services/ai_service.py`, `backend/api/WebApp/*`
- **Responsibilities**:
  - Full CRUD operations for incomes, expenses, budgets, savings goals, and subscriptions.
  - Linear regression forecasting for category expenditures (`_fit_and_predict_linear_model`).
  - Anomaly detection, waste analysis, and financial health score computation (0-100 metric).
  - Executive financial summary generation powered by Google Gemini.
  - Productivity tools: Markdown notes, task tracker, and calendar events.

### B. Chat & Multi-Handler Agent Subsystem
- **Modules**: `backend/chats/chat.py`, `backend/chats/handlers/*`, `backend/chats/services/*`
- **Responsibilities**:
  - Natural language interface coordinating structured multi-domain intent extraction.
  - Domain-specific handlers:
    - `dora_handler.py`: Routes medical queries to DORA engine.
    - `transaction_handler.py`: Parses and executes natural language income/expense operations.
    - `chart_handler.py`: Detects requests for financial visualizations and generates chart data.
    - `file_handler.py`: Generates on-the-fly CSV, DOCX, and PDF documents.
    - `info_handler.py`: Integrates live DuckDuckGo web search and OpenWeather data.
    - `news_handler.py`: Multi-source news aggregator (NewsAPI, Mediastack, Currents).
    - `wiki_handler.py`: Wikipedia encyclopedic summary extraction.
    - `chatbot_handler.py`: General LLM conversational fallback using Google Gemini.

### C. DORA (Diagnostic Operational Research Assistant) Subsystem
- **Modules**: `backend/dora/engine.py`, `backend/dora/routes.py`, `backend/dora/artifacts/*`
- **Responsibilities**:
  - Offline, high-performance disease prediction based on patient symptoms.
  - Utilizes pre-trained TF-IDF vectorizer (`tfidf_vectorizer.pkl`), label encoder (`label_encoder.pkl`), and trained classifier (`disease_model.pkl`).
  - Symptom extraction parser that cleans user input and matches with known clinical dictionaries.
  - Health assessment algorithm generating severity and department recommendations.

### D. Advanced Presentation Generation Engine
- **Modules**: `backend/chats/presentation/*`
- **Responsibilities**:
  - Two-Stage presentation workflow: Stage 1 (Semantic Planning & JSON Schema Generation) and Stage 2 (Physical Layout Resolution & PPTX Rendering).
  - Multi-source visual discovery with licensing checks (Unsplash, Openverse, Wikimedia, Pollinations AI).
  - 21 Modular Presentation Plugins rendering complex slide layouts (Bento grids, KPI grids, Timelines, Code blocks, Process flows, Split layouts, Comparisons).
  - Geometric layout solver preventing bounding box collisions and enforcing typographic hierarchy.
  - Slide narration voiceover synthesis via Microsoft Edge TTS.

---

## 3. Runtime Boundaries & Lifecycle

1. **Startup (`lifespan`)**:
   - Initializes database tables via `Base.metadata.create_all(bind=engine)`.
   - Cleans up orphaned or temporary export files from previous runs.
   - Loads ML models into memory upon first call or module load.
2. **Request Cycle**:
   - FastAPI dependency injection supplies database sessions (`get_db`) with automatic commit/rollback protection.
   - Authentication dependency (`token_required` / `optional_current_user`) decodes and validates JWT credentials.
3. **Shutdown**:
   - Closes active database connection pools.
   - Reclaims ephemeral memory buffers and background task resources.