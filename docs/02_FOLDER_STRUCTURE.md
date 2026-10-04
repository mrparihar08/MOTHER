# 02 - Complete Folder & File Structure

This document provides a comprehensive inventory of every file in the `backend/` directory, detailing its purpose, line count, and architectural category.

```
backend/
├── main.py                                      # CLI & Production Entrypoint
├── app/
│   └── app.py                                   # FastAPI Application Factory & Router Assembly
├── api/
│   ├── auth.py                                  # JWT Auth & Security Dependencies
│   ├── database.py                              # SQLAlchemy Database Connection & Session Provider
│   ├── supabase_client.py                       # Supabase Storage Client Factory
│   ├── models/
│   │   ├── __init__.py                          # Package Marker
│   │   └── vitya.py                             # 16 Database Models & TimestampMixin
│   ├── routes/
│   │   ├── __init__.py                          # Package Marker
│   │   ├── ai.py                                # AI Financial Predictions & Advisory Endpoints
│   │   ├── expense.py                           # Expense CRUD Endpoints
│   │   ├── income.py                            # Income CRUD Endpoints
│   │   ├── savings.py                           # Savings Goals Endpoints
│   │   ├── settings.py                          # User & Preference Settings Endpoints
│   │   ├── subscriptions.py                     # Recurring Subscriptions Endpoints
│   │   ├── users.py                             # Authentication & Profile Endpoints
│   │   └── vitya.py                             # Financial Analytics & CSV Export Endpoints
│   ├── schemas/
│   │   ├── __init__.py                          # Package Marker
│   │   ├── ai_schema.py                         # Lightweight AI Schemas
│   │   └── vitya.py                             # 46 Comprehensive Pydantic Validation Models
│   ├── services/
│   │   ├── __init__.py                          # Package Marker
│   │   └── ai_service.py                        # Financial Analytics & Health Scoring Logic
│   └── WebApp/
│       ├── calendar.py                          # Calendar Event Endpoints
│       ├── notes.py                             # User Notes Endpoints
│       └── tasks.py                             # Task Management Endpoints
├── chats/
│   ├── chat.py                                  # Conversational Router & Intent Dispatcher
│   ├── chatbot.py                               # Lightweight Chatbot Fallback Helper
│   ├── handlers/
│   │   ├── chart_handler.py                     # Financial Chart Dispatcher
│   │   ├── chatbot_handler.py                   # General Gemini LLM Fallback
│   │   ├── dora_handler.py                      # DORA Health Query Dispatcher
│   │   ├── file_handler.py                      # Document Generation (CSV, PDF, DOCX)
│   │   ├── info_handler.py                      # Web Search & Weather Dispatcher
│   │   ├── news_handler.py                      # Multi-source News Dispatcher
│   │   ├── transaction_handler.py               # Natural Language Transaction Parser
│   │   ├── utility_handler.py                   # System Utility Calculations
│   │   └── wiki_handler.py                      # Wikipedia Query Handler
│   ├── routes/
│   │   └── rag_routes.py                        # RAG Document Management Endpoints
│   ├── services/
│   │   ├── ai_image_service.py                  # Pollinations AI Image Generator
│   │   ├── gemini_service.py                    # Google Gemini LLM Client
│   │   ├── image_enhancer.py                    # Image Enhancement & Upscaling
│   │   ├── news_service.py                      # News API Clients (NewsAPI, Mediastack, Currents)
│   │   ├── rag_service.py                       # In-Memory RAG Store & Tokenizer
│   │   ├── unsplash_service.py                  # Unsplash Image Search & URL Extractor
│   │   ├── web_search_service.py                # DuckDuckGo HTML Search Scraper
│   │   └── wikipedia_service.py                 # Wikipedia API Wrapper
│   ├── utils/
│   │   ├── categories.py                        # Category Classification Rules
│   │   ├── document_generators.py               # ReportLab & python-docx Generators
│   │   ├── media_and_exports.py                 # QR Code & Barcode Generators
│   │   ├── openweather_util.py                  # OpenWeatherMap API Client
│   │   ├── presentation_generators.py           # Legacy PPTX Generation Fallbacks
│   │   ├── rules.py                             # Rule-Based Message Matching
│   │   ├── text_utils.py                        # Text Cleaning, Bullets & Table Parsing
│   │   └── themes.py                            # Basic Color Theme Helpers
│   └── presentation/
│       ├── presentation_api.py                  # Presentation Router & Controller
│       ├── schemas.py                           # 46 Presentation Engine Pydantic Schemas
│       ├── planner.py                           # Semantic Planner & Domain Classifier
│       ├── geometry.py                          # Layout Resolver, Bounding Boxes & Grids
│       ├── shapes.py                            # Decorative Shapes & Collision Engine
│       ├── themes.py                            # Color Theory & Contrast Ratio Engine
│       ├── exporter.py                          # PPTX & PDF File Exporters
│       ├── renderers/
│       │   ├── __init__.py                      # Package Marker
│       │   └── ppt_renderer.py                  # Master PptRenderer & 21 Content Plugins
│       ├── scripts/
│       │   ├── generate_master_template.py      # Master PPTX Layout Template Generator
│       │   └── templates.py                     # 14 Theme Layout Presets
│       └── services/
│           ├── cleanup_service.py               # Background Storage Cleanup Task
│           ├── image_manager.py                 # Plan Image Resolution & Caching
│           ├── presentation_store.py            # In-Memory Presentation Store & Cache
│           ├── security.py                      # Path Traversal & URL Sanitizer
│           ├── voiceover_service.py             # Edge-TTS Slide Voiceover Generator
│           └── image_search/
│               ├── __init__.py                  # Image Search Package Marker
│               ├── image_service.py             # Unified Multi-Source Image Service
│               ├── image_selector.py            # Query Builder, Scoring & Ranker
│               ├── license_checker.py           # Creative Commons & Attribution Evaluator
│               ├── openverse.py                 # Openverse API Client
│               └── wikimedia.py                 # Wikimedia Commons Search Client
├── dora/
│   ├── __init__.py                              # DORA Package Marker & Router Export
│   ├── engine.py                                # KnowledgeEngine Diagnostic ML Logic
│   ├── routes.py                                # DORA Health API Endpoints
│   ├── dataset.csv                              # Disease Symptoms Training Dataset
│   └── artifacts/
│       ├── disease_model.pkl                    # Scikit-learn Classifier
│       ├── label_encoder.pkl                    # Disease Target Label Encoder
│       └── tfidf_vectorizer.pkl                 # Symptom Feature TF-IDF Vectorizer
└── tests/
    ├── test_dora_integration.py                 # DORA ML Engine & Endpoint Unit Tests
    ├── test_image_discovery.py                  # Image Search & License Checker Tests
    ├── test_layout_engine.py                    # Geometry Solver & Collision Tests
    ├── test_master_template.py                  # Master PPTX Template Verification
    ├── test_semantic_planner.py                 # AI Planner & Schema Validation Tests
    ├── test_shape_engine.py                     # Decorative Shape Placement Tests
    └── test_template_presets.py                 # 14 Theme Layout Preset Tests
```

---

## 📊 File Size & Code Distribution Metrics

| Component | File Count | Approximate LOC | Key Technologies |
| :--- | :---: | :---: | :--- |
| **Presentation Engine** | 19 | ~12,500 | `python-pptx`, `Pydantic`, `Edge-TTS`, `Pillow` |
| **API & Finance Core** | 16 | ~4,200 | `FastAPI`, `SQLAlchemy`, `scikit-learn`, `python-jose` |
| **Chat & Agent Handlers** | 20 | ~3,800 | `Google Gemini`, `DuckDuckGo`, `NewsAPI`, `ReportLab` |
| **DORA Health ML** | 4 | ~750 | `scikit-learn`, `pandas`, `TF-IDF`, `Joblib` |
| **Automated Unit Tests** | 7 | ~1,600 | `pytest`, `httpx`, `fastapi.testclient` |
| **App Entry & Config** | 2 | ~150 | `Uvicorn`, `CORS`, `StaticFiles` |
| **TOTALS** | **68 Python Files** | **~23,000 LOC** | Fully Python 3.10+ Compliant |