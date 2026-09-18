# 🌟 Vitya AI — Intelligent Financial & Presentation Intelligence Suite

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python)](https://www.python.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg?style=flat&logo=sqlalchemy)](https://www.sqlalchemy.org/)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-ML-F7931E.svg?style=flat&logo=scikit-learn)](https://scikit-learn.org/)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-AI-4285F4.svg?style=flat&logo=googlecloud)](https://ai.google.dev/)
[![python-pptx](https://img.shields.io/badge/python--pptx-0.6.21+-C41C00.svg?style=flat&logo=microsoftpowerpoint)](https://python-pptx.readthedocs.io/)
[![Pytest](https://img.shields.io/badge/Pytest-Passing-success.svg?style=flat&logo=pytest)](https://docs.pytest.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Vitya AI** (codename **MOTHER**) is an enterprise-grade personal finance management, autonomous PowerPoint deck generation, and AI-powered productivity backend. Powered by **FastAPI**, **SQLAlchemy 2.0**, **Scikit-learn**, and **Google Gemini AI**, Vitya delivers seamless multi-tenant isolation, real-time ML forecasting, multi-stage conversational intelligence, and dynamic presentation layouts.

---

## 📑 Table of Contents

- [Core Capabilities](#-core-capabilities)
  - [1. Personal Finance Tracking](#-1-personal-finance-tracking)
  - [2. Machine Learning Financial Forecasting](#-2-machine-learning-financial-forecasting)
  - [3. Autonomous Presentation & Deck Generation](#-3-autonomous-presentation--deck-generation)
  - [4. Conversational AI & Multi-Stage Intent Router](#-4-conversational-ai--multi-stage-intent-router)
  - [5. RAG (Retrieval-Augmented Generation)](#-5-rag-retrieval-augmented-generation)
  - [6. Multi-Tenant Productivity Workspace](#-6-multi-tenant-productivity-workspace)
  - [7. Enterprise Security & Authentication](#-7-enterprise-security--authentication)
- [System Architecture](#-system-architecture)
- [Technology Stack](#-technology-stack)
- [Project Directory Structure](#-project-directory-structure)
- [API Reference Guide](#-api-reference-guide)
- [Getting Started & Local Development](#-getting-started--local-development)
  - [Prerequisites](#prerequisites)
  - [1. Clone Repository](#1-clone-repository)
  - [2. Virtual Environment Setup](#2-virtual-environment-setup)
  - [3. Install Dependencies](#3-install-dependencies)
  - [4. Configure Environment Variables](#4-configure-environment-variables)
  - [5. Run Development Server](#5-run-development-server)
  - [6. Access Interactive API Docs](#6-access-interactive-api-docs)
- [Presentation Generation CLI](#-presentation-generation-cli)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Cloud Deployment (Render)](#-cloud-deployment-render)
- [Roadmap](#-roadmap)
- [License & Acknowledgments](#-license--acknowledgments)

---

## 🚀 Core Capabilities

### 💰 1. Personal Finance Tracking
- **Income & Expense CRUD**: Comprehensive management of incomes and expenses categorized with timestamps, notes, and amounts.
- **Dynamic CSV Data Exports**: Dedicated, streamable CSV endpoints (`/api/vitya/csv/expenses` and `/api/vitya/csv/incomes`) for seamless offline spreadsheet analysis.
- **Financial Analytics & Trend Insights**: Real-time spending distributions, monthly spending velocity, historical trend calculations, and category breakdowns.

### 🧠 2. Machine Learning Financial Forecasting
- **Non-Blocking Predictive Engine**: Built on Scikit-Learn `LinearRegression`, offloaded to threadpools via `run_in_threadpool` to prevent event-loop latency.
- **Category Expense Prediction**: Forecasts upcoming monthly spending per category (`/api/ai/predict/{category}`).
- **Overspending & Anomaly Detection**: Proactively flags transactions that spike beyond 1.5x to 2x historical moving averages.
- **Tiered Budget & Savings Allocator**: Dynamically allocates savings ratios (10%–30%) based on gross income tiers and proportional necessity budgeting.

### 🎨 3. Autonomous Presentation & Deck Generation
- **Fluid Responsive Geometry**: Core geometry engine in [`geometry.py`](backend/chats/presentation/geometry.py) with bounding box solvers, collision mitigation, responsive layouts, and container nesting.
- **Intelligent Deck Planner**: Multi-stage planner in [`planner.py`](backend/chats/presentation/planner.py) generating structured slide hierarchies, card matrices, stat callouts, timelines, and visual anchors.
- **16+ Professional Designer Archetypes**: Pre-configured architectural styles (Ion Boardroom, Berlin Executive, Quotable Teal & Black, Modern Minimalist, Slate Horizon, Sunset Amber, Midnight Neon, etc.).
- **Native PowerPoint (.pptx) Export**: Generates pixel-perfect, editable `.pptx` presentations ready for executive delivery.

### 🤖 4. Conversational AI & Multi-Stage Intent Router
- **Multi-Layered Intent Cascade**: Classifies natural language inputs to identify transactional requests (e.g., *"Spent $45 on groceries"*), report queries, or informational inquiries.
- **Specialized Media & Utility Handlers**: Dynamically creates QR codes, barcodes, OpenWeather weather cards, and Wikipedia summaries.
- **Google Gemini AI Fallback**: Integrates Google Gemini (`gemini-flash-latest` / `gemini-1.5-flash`) with lazy-loaded service architecture for complex conversational reasoning.

### 🔍 5. RAG (Retrieval-Augmented Generation)
- **Knowledge Base Ingestion**: Endpoints mounted under `/api/rag` for processing and retrieving localized document contexts, policies, or financial guides.

### 📝 6. Multi-Tenant Productivity Workspace
- **Private User Notes**: Full CRUD capabilities for encrypted personal memos and notes.
- **Task Tracking**: Task management with status toggles, priority levels, and multi-tenant security guarantees.

### 🔐 7. Enterprise Security & Authentication
- **Multi-Tenant Data Isolation**: Database-level foreign-key scoping (`user_id`) ensuring zero cross-tenant data leakage.
- **JWT Bearer Authentication**: High-security token generation with configurable expiration and refresh lifecycles.
- **Password Protection**: Passlib bcrypt cryptographic hashing with automatic salt generation.
- **Dynamic Password Recovery**: Secure reset tokens with environment-aware `FRONTEND_URL` resolution for email reset flows.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph ClientLayer [Client Applications]
        WebClient[Web Frontend / React / Vue]
        MobileClient[Mobile App]
        APIConsumer[API / Swagger Docs]
    end

    subgraph FastAPIServer [FastAPI Core Engine]
        Gateway[FastAPI Application - app.py]
        AuthGuard[JWT Auth Middleware & Dependency - auth.py]
        
        subgraph APIRoutes [API Routers]
            UsersR[Users & Auth - /api/users]
            FinanceR[Income & Expenses - /api/income, /api/expense]
            AIR[ML Predictions & Budgeting - /api/ai]
            VityaR[Analytics & CSV Exports - /api/vitya]
            ChatR[Conversational AI - /api/chat]
            PresR[Presentation Engine - /api/presentation]
            RAGR[RAG Knowledge - /api/rag]
            WorkR[Notes & Tasks - /api/notes, /api/tasks]
        end
        
        subgraph PresentationCore [Presentation Pipeline]
            GeoEngine[Fluid Geometry Engine - geometry.py]
            DeckPlan[Slide Deck Planner - planner.py]
            Themes[16 Design Archetypes - themes.py]
            PPTRender[PPTX Renderer - ppt_renderer.py]
        end
    end

    subgraph AsyncAndExternal [Async Workers & External Services]
        MLThreadPool[Scikit-Learn Threadpool Engine]
        GeminiAPI[Google Gemini Generative AI]
        WeatherAPI[OpenWeather API]
        WikiAPI[Wikipedia API]
    end

    subgraph DataStorage [Persistence Layer]
        SQLAlchemy[SQLAlchemy 2.0 ORM]
        DB[(PostgreSQL / SQLite / Supabase)]
    end

    ClientLayer --> |HTTPS / JSON Requests| Gateway
    Gateway --> AuthGuard
    AuthGuard --> APIRoutes
    
    FinanceR --> SQLAlchemy
    UsersR --> SQLAlchemy
    WorkR --> SQLAlchemy
    VityaR --> SQLAlchemy
    
    AIR --> |run_in_threadpool| MLThreadPool
    PresR --> PresentationCore
    PresentationCore --> PPTRender
    
    ChatR --> GeminiAPI
    ChatR --> WeatherAPI
    ChatR --> WikiAPI
    
    SQLAlchemy --> DB
```

---

## 🛠️ Technology Stack

| Layer | Technology | Key Responsibility |
| :--- | :--- | :--- |
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/) (0.100+) | Asynchronous, high-throughput REST API routing |
| **Server** | [Uvicorn](https://www.uvicorn.org/) / [Gunicorn](https://gunicorn.org/) | Production ASGI/WSGI deployment engine |
| **ORM & Database** | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) | Modern mapped declarative models & connection pooling |
| **Data Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Type safety, input sanitation, schema enforcement |
| **Auth & Cryptography** | [PyJWT](https://pyjwt.readthedocs.io/) & [Passlib (bcrypt)](https://passlib.readthedocs.io/) | Bearer token verification and salted password hashing |
| **Machine Learning** | [Scikit-Learn](https://scikit-learn.org/) & [NumPy](https://numpy.org/) | Linear regression expense modeling & anomaly detection |
| **Generative AI** | [Google Gemini](https://ai.google.dev/) (`google-generativeai`) | Contextual conversational agent & reasoning |
| **Presentation Engine** | [python-pptx](https://python-pptx.readthedocs.io/) | Native PowerPoint deck compilation and visual formatting |
| **Visualization & Export** | [Matplotlib](https://matplotlib.org/) & [Pandas](https://pandas.pydata.org/) | Server-rendered financial charts & dynamic CSV streams |
| **Testing Suite** | [Pytest](https://docs.pytest.org/) & [AnyIO](https://anyio.readthedocs.io/) | Automated end-to-end and unit verification |
| **Hosting & Cloud** | [Render](https://render.com/) / PostgreSQL | Cloud-native continuous deployment blueprint (`render.yaml`) |

---

## 📂 Project Directory Structure

```text
MOTHER/
├── backend/
│   ├── app/
│   │   └── app.py                     # FastAPI application setup, CORS, router mounts
│   ├── api/
│   │   ├── auth.py                    # JWT token creation, decoding & user dependency
│   │   ├── database.py                # Database engine, SessionLocal & get_db dependency
│   │   ├── models/
│   │   │   └── vitya.py               # Declarative ORM models (User, Income, Expense, etc.)
│   │   ├── routes/
│   │   │   ├── users.py               # Authentication, registration & reset password
│   │   │   ├── income.py              # Income record endpoints
│   │   │   ├── expense.py             # Expense record endpoints
│   │   │   ├── ai.py                  # ML predictions, anomaly alerts, budget advice
│   │   │   └── vitya.py               # Financial summaries, chart images & CSV exports
│   │   ├── schemas/
│   │   │   └── vitya.py               # Pydantic input/output schemas
│   │   └── WebApp/
│   │       ├── notes.py               # Multi-tenant Notes CRUD
│   │       └── tasks.py               # Multi-tenant Tasks CRUD
│   ├── chats/
│   │   ├── chat.py                    # Primary chat entry point (/api/chat)
│   │   ├── chatbot.py                 # Multi-stage intent classification & router
│   │   ├── gemini_service.py          # Google Gemini AI client integration
│   │   ├── handlers/                  # Specialized intent processors (transaction, news, etc.)
│   │   ├── presentation/
│   │   │   ├── geometry.py            # Fluid responsive layout & bounding box engine
│   │   │   ├── planner.py             # Slide hierarchy and layout planner
│   │   │   ├── presentation_api.py    # Deck generation & template endpoints
│   │   │   ├── renderers/             # PPTX rendering engine
│   │   │   ├── schemas.py             # Deck & slide layout schemas
│   │   │   ├── scripts/               # Master template generator scripts
│   │   │   └── themes.py              # 16 distinct color & typography themes
│   │   ├── routes/
│   │   │   └── rag_routes.py          # RAG document retrieval & search endpoints
│   │   └── utils/                     # Media generators (QR, Barcode, Weather, Wikipedia)
│   └── main.py                        # ASGI application launcher (Uvicorn)
├── scripts/
│   └── generate_all_templates.py      # Standalone deck generator for all 16 archetypes
├── tests/
│   ├── conftest.py                    # Pytest test DB fixtures & mock dependencies
│   ├── test_ai_ml.py                  # Machine learning endpoint tests
│   ├── test_auth.py                   # User authentication & token tests
│   ├── test_fluid_geometry.py         # Fluid layout solver tests
│   ├── test_mixed_geometry.py         # Mixed-content layout tests
│   ├── test_notes_tasks.py            # Multi-tenant isolation tests
│   ├── test_presentation_quality.py   # Deck generator quality & schema checks
│   ├── test_template_rendering.py     # Template rendering verification
│   └── test_vitya_routes.py           # Financial endpoints & CSV exports tests
├── requirements.txt                   # Production & development dependencies
├── render.yaml                        # Infrastructure-as-code deployment blueprint
├── CODE_EXPLANATION_AND_ROADMAP.md    # Detailed architecture reference & roadmap
└── DEVELOPER_GUIDE.md                 # In-depth technical guide for contributors
```

---

## 📡 API Reference Guide

The API is structured around modular, authenticated endpoints:

| Tag | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Health** | `GET` | `/health` | Server health check probe |
| **Users** | `POST` | `/api/users/register` | Register new user account |
| **Users** | `POST` | `/api/users/login` | Authenticate and obtain JWT access token |
| **Users** | `POST` | `/api/users/forgot-password` | Request password reset token & email link |
| **Users** | `POST` | `/api/users/reset-password` | Reset password using valid reset token |
| **Income** | `GET` | `/api/income/` | List all incomes for authenticated user |
| **Income** | `POST` | `/api/income/` | Add a new income entry |
| **Expense** | `GET` | `/api/expense/` | List all expenses for authenticated user |
| **Expense** | `POST` | `/api/expense/` | Record a new expense |
| **AI / ML** | `GET` | `/api/ai/predict/{category}` | Scikit-learn forecast for category expenses |
| **AI / ML** | `GET` | `/api/ai/anomaly` | Anomaly and overspending spike detection |
| **AI / ML** | `GET` | `/api/ai/budget-advice` | Automated tiered savings and budget plan |
| **Vitya** | `GET` | `/api/vitya/summary` | Aggregated financial summary & monthly balances |
| **Vitya** | `GET` | `/api/vitya/csv/expenses` | Export user expenses as downloadable CSV |
| **Vitya** | `GET` | `/api/vitya/csv/incomes` | Export user incomes as downloadable CSV |
| **Chat** | `POST` | `/api/chat/` | Conversational query (transaction parser / Gemini fallback) |
| **Presentation** | `POST` | `/api/presentation/generate` | Generate presentation deck JSON or PPTX |
| **Presentation** | `GET` | `/api/presentation/templates` | Retrieve available presentation themes & templates |
| **RAG** | `POST` | `/api/rag/query` | Query knowledge base documents |
| **Notes** | `GET` / `POST` | `/api/notes/` | User-scoped personal notes CRUD |
| **Tasks** | `GET` / `POST` | `/api/tasks/` | User-scoped task items CRUD |

---

## 💻 Getting Started & Local Development

### Prerequisites
- **Python 3.10+** (Python 3.10 or 3.11 recommended)
- **Git**
- Optional: PostgreSQL (SQLite is supported out-of-the-box for local testing)

### 1. Clone Repository
```bash
git clone https://github.com/mrparihar08/MOTHER.git
cd MOTHER
```

### 2. Virtual Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate on Windows:
venv\Scripts\activate

# Activate on Linux / macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root project directory:

```env
# Server & Security
PORT=10000
ENVIRONMENT=development
SECRET_KEY=your_super_secret_jwt_hmac_key_min_32_chars
FRONTEND_URL=http://localhost:3000

# Database Configuration (SQLite default; PostgreSQL supported)
DATABASE_URL=sqlite:///./instance/test.db
# Or PostgreSQL: postgresql://user:password@localhost:5432/vitya_db

# AI & Third-Party Integrations (Optional for local testing)
GEMINI_API_KEY=your_google_gemini_api_key
OPENWEATHER_API_KEY=your_openweather_api_key

# CORS Allowed Origins (Comma-separated)
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

### 5. Run Development Server
```bash
python backend/main.py
```
Or via Uvicorn with auto-reload:
```bash
uvicorn backend.app.app:app --host 0.0.0.0 --port 10000 --reload
```

### 6. Access Interactive API Docs
Once the server is running, explore and test the endpoints directly in your browser:
- **Swagger UI**: [http://localhost:10000/docs](http://localhost:10000/docs)
- **Health Check**: [http://localhost:10000/health](http://localhost:10000/health)

---

## 🎨 Presentation Generation CLI

Generate all 16 designer presentation archetypes into standalone `.pptx` decks using the built-in batch generation script:

```bash
python scripts/generate_all_templates.py
```

Generated decks will be saved into the `output_templates/` directory, showcasing styles such as:
1. `ion_boardroom` (Deep Indigo & Neon Magenta)
2. `berlin_executive` (Burnt Orange & Charcoal Slate)
3. `quotable_teal` (Cyan Block & Dark Canvas)
4. `modern_minimalist` (Crisp Clean Monochrome)
5. `slate_horizon` (Corporate Navy & Soft Gray)
6. ... and 11 additional architectural styles!

---

## 🧪 Testing & Quality Assurance

Run the automated test suite with `pytest`:

```bash
python -m pytest
```

To run a specific test suite or include verbose logs:
```bash
# Run ML predictive tests
python -m pytest tests/test_ai_ml.py -v

# Run authentication and isolation tests
python -m pytest tests/test_auth.py tests/test_notes_tasks.py -v

# Run presentation geometry tests
python -m pytest tests/test_fluid_geometry.py tests/test_mixed_geometry.py -v
```

---

## ☁️ Cloud Deployment (Render)

This repository includes a production-ready [`render.yaml`](render.yaml) specification:

1. Connect your repository to **Render**.
2. Render detects `render.yaml` automatically and configures:
   - **Web Service**: Gunicorn/Uvicorn ASGI server running `backend.app.app:app`.
   - **Managed PostgreSQL**: Relational database instance with connection string auto-binding.
3. Configure environment secrets (`SECRET_KEY`, `GEMINI_API_KEY`, etc.) in the Render dashboard.

---

## 🗺️ Roadmap

- [x] **Multi-Tenant Personal Finance Engine** (Income, Expenses, CSV Exports)
- [x] **Scikit-Learn Non-Blocking ML Forecasting** (Linear regression & anomalies)
- [x] **Automated PPTX Deck Generator** (16 designer archetypes & fluid geometry)
- [x] **Multi-Stage Intent Classification Chatbot** (Gemini AI integration)
- [x] **RAG Knowledge Retrieval Pipeline**
- [ ] **Direct Open Banking / Plaid Integration** for automatic transaction syncing
- [ ] **AI-Powered Receipt OCR** for automatic receipt data extraction
- [ ] **Multi-Currency & Real-Time FX Conversion Engine**
- [ ] **Interactive Web Deck Previewer** (React canvas presentation editor)

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/mrparihar08/MOTHER/issues).

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License & Acknowledgments

Distributed under the **MIT License**.

Special thanks to:
- The **FastAPI**, **SQLAlchemy**, and **Pydantic** teams for the modern Python backend foundation.
- **Scikit-learn** and **NumPy** for reliable numerical computing and prediction models.
- **Google DeepMind & Gemini Team** for world-class generative AI models.
- The open-source maintainers of **python-pptx** enabling programmatic slide creation.
