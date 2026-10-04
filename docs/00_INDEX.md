# MOTHER Backend Architecture & Documentation System

Welcome to the **MOTHER** (Multimodal Omnipresent Technology for Holistic Enterprise & Research) / **Vitya AI** Backend Architecture Documentation.

This documentation system provides an authoritative, code-verified reference of the entire backend codebase, including its API surfaces, database models, conversational handlers, machine learning engines, and presentation generation pipeline.

---

## 📑 Master Documentation Index

| File | Document | Purpose & Scope |
| :--- | :--- | :--- |
| **[00_INDEX.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/00_INDEX.md)** | **Master Index** | Documentation overview, navigation matrix, verification standards. |
| **[01_ARCHITECTURE.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/01_ARCHITECTURE.md)** | **System Architecture** | High-level system design, subsystems, request lifecycle, boundaries. |
| **[02_FOLDER_STRUCTURE.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/02_FOLDER_STRUCTURE.md)** | **Folder & File Map** | Directory tree, file purposes, lines of code, architectural roles. |
| **[03_MODULE_CONNECTIONS.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/03_MODULE_CONNECTIONS.md)** | **Module Connections** | Cross-module dependency matrix, callers/callees, couplings. |
| **[04_API_FLOW.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/04_API_FLOW.md)** | **API Endpoint Catalog** | Comprehensive catalog of all 70+ FastAPI endpoints with schemas. |
| **[05_DATA_FLOW.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/05_DATA_FLOW.md)** | **Data & Event Lifecycle** | End-to-end data pipelines for Auth, Finance, Chat, DORA, and PPTX. |
| **[06_DATABASE.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/06_DATABASE.md)** | **Database Architecture** | SQLAlchemy models, relational schema, sessions, migrations. |
| **[07_PRESENTATION_ENGINE.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/07_PRESENTATION_ENGINE.md)** | **Presentation Engine** | Two-stage generation pipeline, geometry solver, themes, shapes. |
| **[08_PLANNER.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/08_PLANNER.md)** | **Semantic Planner** | `PromptPlanner`, AI semantic synthesis, layout specs, rule fallbacks. |
| **[09_RENDERER.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/09_RENDERER.md)** | **PPTX Renderer** | `PptRenderer`, layout drawers, element placers, shape engines. |
| **[10_PLUGIN_SYSTEM.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/10_PLUGIN_SYSTEM.md)** | **Presentation Plugins** | 21 element & layout plugins (Charts, Tables, Bento, Flow, etc.). |
| **[11_IMAGE_SYSTEM.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/11_IMAGE_SYSTEM.md)** | **Image Discovery Engine** | Multi-source search (Unsplash, Openverse, Wikimedia), Pollinations. |
| **[12_AUTHENTICATION.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/12_AUTHENTICATION.md)** | **Auth & Security** | JWT tokens, password hashing, route guards, CORS, input hygiene. |
| **[13_ERROR_HANDLING.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/13_ERROR_HANDLING.md)** | **Error Handling** | Resilience patterns, retry logic, fallback behaviors, crash guards. |
| **[14_CONFIG_AND_ENV.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/14_CONFIG_AND_ENV.md)** | **Config & Environment** | Environment variables, secrets management, default parameters. |
| **[15_DEPENDENCIES.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/15_DEPENDENCIES.md)** | **Dependency Matrix** | External library usage, requirements justifications, licenses. |
| **[16_DEPLOYMENT.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/16_DEPLOYMENT.md)** | **Deployment & Startup** | Render configuration, lifespan triggers, Uvicorn settings, mounts. |
| **[17_CHANGELOG.md](file:///c:/Users/preet/OneDrive/Desktop/MOTHER/backend/docs/17_CHANGELOG.md)** | **Architectural Evolution**| Milestone history, major refactors, component transitions. |

---

## 🏛️ Subsystem Map

```
                                  ┌────────────────────────────────┐
                                  │       Client Applications      │
                                  │ (Web UI, Mobile, External API) │
                                  └───────────────┬────────────────┘
                                                  │ HTTP / JSON
                                                  ▼
                                  ┌────────────────────────────────┐
                                  │     FastAPI Application        │
                                  │   (backend/app/app.py:app)     │
                                  └───────┬──────────────┬─────────┘
                  ┌───────────────────────┼──────────────┼────────────────────────┐
                  ▼                       ▼              ▼                        ▼
      ┌──────────────────────┐ ┌────────────────────┐ ┌────────────────┐ ┌────────────────┐
      │   Core & Finance     │ │    Chat & Agent    │ │ DORA Health ML │ │  Presentation  │
      │   (backend/api)      │ │   (backend/chats)  │ │ (backend/dora) │ │     Engine     │
      └──────────┬───────────┘ └─────────┬──────────┘ └────────┬───────┘ └────────┬───────┘
                 │                       │                     │                  │
                 ▼                       ▼                     ▼                  ▼
      ┌──────────────────────┐ ┌────────────────────┐ ┌────────────────┐ ┌────────────────┐
      │ SQLAlchemy / Postgres│ │ Gemini LLM & RAG   │ │ Scikit-Learn   │ │ python-pptx /  │
      │ / Supabase Storage   │ │ Search & Handlers  │ │ Disease Models │ │ Image Services │
      └──────────────────────┘ └────────────────────┘ └────────────────┘ └────────────────┘
```

---

## 🔍 Verification Standards
All documentation in this repository has been generated via static abstract syntax tree (AST) parsing, FastAPI route registry inspection, SQLAlchemy schema reflection, and explicit call-graph analysis of the active codebase. 

- Unverified components or unreachable routes are strictly marked with `[UNVERIFIED]`.
- All line numbers, file paths, and class signatures correspond directly to current disk state.