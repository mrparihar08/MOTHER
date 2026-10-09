# MOTHER Project Architecture Specification

**Document Version**: 1.0.0  
**Status**: Approved Architecture Audit (Phase 1)  
**Date**: October 2026  
**System**: MOTHER (Multimodal Omnipresent Technology for Holistic Enterprise & Research)

---

## 1. System Vision & Architecture Overview

The **MOTHER** platform is an enterprise-grade multi-domain platform structured into a **Shared Platform Core** powering three specialized, sovereign business modules:

```
                               ┌────────────────────────────────────────────────────────┐
                               │                    MOTHER PLATFORM                     │
                               │                  Master Web Dashboard                  │
                               └───────────────────────────┬────────────────────────────┘
                                                           │
        ┌──────────────────────────────────────────────────┼──────────────────────────────────────────────────┐
        │                                                  │                                                  │
        ▼                                                  ▼                                                  ▼
┌───────────────────────────────┐          ┌───────────────────────────────┐          ┌───────────────────────────────┐
│     PRESENTATION STUDIO       │          │           DORA DR.            │          │    VIDYA F.E.I ADVISOR        │
│  Autonomous Deck Synthesizer  │          │   Clinical Triage & Health    │          │  Finance, Expense, Income & AI│
├───────────────────────────────┤          ├───────────────────────────────┤          ├───────────────────────────────┤
│ • 2-Stage Planning Pipeline   │          │ • 130+ Symptom ML Triage      │          │ • Double-Entry Ledgers (Inc/Exp)│
│ • 16:9 Spatial Layout Engine  │          │ • Scikit-Learn Disease Model  │          │ • 0-100 Financial Health Score│
│ • 21 Content & Chart Plugins  │          │ • Urgency & Department Referral│         │ • Linear ML Trend Forecasting │
│ • Multi-Source Image Engine   │          │ • Emergency Symptom Detection │          │ • Budget Caps & Anomaly Guard │
│ • Edge-TTS Narration Audio    │          │ • Multilingual Triage (HI/EN) │          │ • Savings Goals & Subscriptions│
│ • Brand Profiles & Custom CSS │          │ • BMI & Health Risk Assessment│          │ • Gemini AI Financial Briefs  │
└───────────────┬───────────────┘          └───────────────┬───────────────┘          └───────────────┬───────────────┘
                │                                          │                                          │
                └──────────────────────────────────────────┼──────────────────────────────────────────┘
                                                           │
                                                           ▼
                               ┌────────────────────────────────────────────────────────┐
                               │                  SHARED PLATFORM CORE                  │
                               ├────────────────────────────────────────────────────────┤
                               │ • Central JWT Auth & Role Authorization (auth.py)      │
                               │ • SQLAlchemy ORM (16 DB Models, Connection Pooling)    │
                               │ • User Profile, Security, & System Settings            │
                               │ • AI Provider Gateway (Google Gemini Client)           │
                               │ • Shared Productivity Layer (Notes, Tasks, Calendar)   │
                               │ • File Storage, Static Assets & Upload Validation      │
                               │ • Conversational Intent Dispatcher & RAG Search        │
                               └────────────────────────────────────────────────────────┘
```

---

## 2. The Three Sovereign Modules

### Module 1: Presentation Studio
- **Domain Focus**: Automated generative PowerPoint deck engineering, spatial slide layout calculation, visual content generation, and slide deck delivery.
- **Key Capabilities**:
  - **Stage 1 (Semantic Planning)**: Natural language prompt parsing into structured JSON slide specifications (`PresentationPlan`) via Google Gemini.
  - **Stage 2 (Spatial Resolution & Rendering)**: 16:9 widescreen layout solver (12,192,000 x 6,858,000 EMUs) calculating 2D bounding boxes without collisions.
  - **21 Slide Plugins**: Paragraph, Text, Bullets, Chart, Table, BentoGrid, KPIGrid, ProcessFlow, Timeline, SplitLayout, Stats, Comparison, Quote, etc.
  - **Visual Asset Discovery**: Automated license-checked image sourcing from Unsplash, Openverse, Wikimedia Commons, and Pollinations AI.
  - **Voiceover Synthesis**: Edge-TTS slide narration generated into timed MP3 audio files.
  - **Brand Profiles**: Custom organizational colors, corporate typography, and logo watermarking.

### Module 2: Dora Dr.
- **Domain Focus**: Clinical health intelligence, offline medical machine learning diagnostics, symptom triage, preventative healthcare advice, and specialist doctor routing.
- **Key Capabilities**:
  - **Machine Learning Engine**: TF-IDF vectorizer + multiclass classifier trained on clinical disease datasets with 130+ symptoms and 40+ medical conditions.
  - **Symptom NLP Extraction**: Natural language detection and fuzzy-matching of user-described symptoms in conversation.
  - **Emergency Interceptor**: Hard-coded safety triggers flagging critical life-threatening conditions (chest pain, stroke, severe bleeding, anaphylaxis) with immediate emergency hotline warnings.
  - **Clinical Consultation**: Gemini-backed medical guidance providing precautions, lab test recommendations, and department specialist matching.
  - **Health Risk Assessment**: Metric-based BMI, lifestyle risk factors, and metabolic profiles.
  - **Multilingual Healthcare**: Native support for English, Hindi (हिन्दी), and Hinglish clinical explanations.

### Module 3: Vidya F.E.I Advisor
- **Domain Focus**: Personal and enterprise wealth management, double-entry financial accounting, algorithmic spending analytics, and AI fiduciary advisory.
- **Core Meaning of F.E.I**:
  - **F — Finance**: Net worth overview, account balance aggregation, cashflow trends, financial charts, and CSV ledger reporting.
  - **E — Expense**: Granular categorization, monthly budget caps, spending waste detection, 2x std-dev anomaly alerts, and automated receipt OCR scanning.
  - **I — Income & Intelligence**: Primary and passive income stream tracking, milestone-based savings goals, recurring subscription forecasting, scikit-learn linear trend projection, 0–100 composite Financial Health Score, and Gemini executive briefings.

---

## 3. Shared Platform Core

The Shared Platform Core provides infrastructure services consumed identically across all three modules:

1. **Authentication & Identity**:
   - Access tokens (`HS256`, 24-hour lifetime) and Password Reset tokens (15-minute lifetime).
   - Fast route guards: `token_required` (strict) and `optional_current_user` (public/hybrid access).
   - Identity schema: `User` table with profile picture, bio, credentials, and relationship cascading.

2. **Database & Data Persistence**:
   - Unified SQLAlchemy 2.0 ORM engine supporting SQLite (local dev/fallback) and PostgreSQL (Render / Supabase).
   - Thread-safe session generator (`get_db`) with automatic pooling.
   - Declarative schema initialization via FastAPI lifespan hooks.

3. **AI Gateway**:
   - Google Gemini 1.5/2.0 API gateway (`gemini_service.py`) with automatic key rotation, model fallback ladders, and structured JSON parsing.

4. **Storage & Media Services**:
   - Sanitized static file delivery via `/uploads` and `/assets`.
   - Dedicated output stores for temporary `.pptx` decks (`outputs/store`) and voiceover audio (`outputs/voiceovers`).
   - Hardened filename hygiene and path-traversal prevention (`security.py`).

5. **Cross-Module Productivity & Agent Chat**:
   - Shared productivity utilities: Notes (`/api/notes`), Tasks (`/api/tasks`), and Calendar Events (`/api/calendar`).
   - Central Conversational Dispatcher (`/api/chat`) equipped with intent classification routing queries to DORA, Financial Ledgers, Chart Generators, or RAG Documents.

---

## 4. Frontend Architectural Layout

The MOTHER Frontend operates as a cohesive Single Page Application (SPA) powered by React:

- **Root Shell & Navigation**: Persistent top bar and collapsible sidebar offering instant 1-click switching between:
  1. `Presentation Studio` (`/presentation`)
  2. `Dora Dr.` (`/dora` or `/apps/dora`)
  3. `Vidya F.E.I Advisor` (`/finance` or `/apps/finance`, `/apps/financial-health`)
- **Shared State**:
  - `AuthContext`: Manages login sessions, profile data, and JWT persistence.
  - `ThemeContext`: Manages dark/light appearance tokens and custom accent colors.
- **Module Isolation**:
  - Each module possesses its own internal view states, toolbars, dialogs, and workspace canvases.
  - Switching between modules preserves active user authentication and maintains in-flight background tasks.

---

## 5. Security & Isolation Boundaries

| Boundary Dimension | Enforcement Mechanism |
| :--- | :--- |
| **API Authentication** | Fast Bearer header inspection; rejected with 401 Unauthorized before route execution. |
| **Data Isolation** | All database queries strictly filtered by `user_id == current_user.id` at SQL query level. |
| **Model Isolation** | DORA ML engine operates entirely in memory, completely isolated from user financial databases. |
| **File Access** | Strict path resolution checks verifying target file resides within allowed directories (`security.py`). |
| **CORS Policy** | Whitelisted frontend origins and regex matching for local dev and official Render domains. |

---

## 6. Verification & Health Monitoring

The system exposes unified and module-specific health endpoints:
- System Root: `GET /` and `GET /health`
- Presentation Engine: `GET /api/presentation/health`
- Dora Engine: `GET /api/dora/`
- Vidya Overview: `GET /api/vitya/financial_overview`

---

## 7. Phase 2 & Phase 3 Formalization Record

- **Domain Packaging**: Clean Python package structure established for `backend.presentation`, `backend.dora`, and `backend.finance`.
- **API Alias Implementation**: `/api/ai` and `/api/analyse` mounted simultaneously on `analyse.router` for 100% frontend and backward compatibility.
- **Route Order Resolution**: Static route `/api/presentation/templates` prioritized before dynamic `/{presentation_id}` single-segment path matcher.
- **Circular Dependency Elimination**: `backend/presentation/services/image_manager.py` updated to import `generate_ai_image` directly from `backend.presentation.services.ai_image_service` rather than through the chats adapter.
- **Model Loading Optimization**: `backend/dora/engine.py` updated to load serialized joblib artifacts (`disease_model.pkl`, `tfidf_vectorizer.pkl`, `label_encoder.pkl`) without redundant retraining or risk of file-locking crashes.
- **Automated Verification**: Full test suite verified at **144 / 144 passing tests (100%)** including domain boundary, alias compatibility, and user data isolation tests.

