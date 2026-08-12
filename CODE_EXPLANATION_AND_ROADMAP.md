# Vitya AI — Codebase Architecture & Implementation Roadmap

## 1. Executive Summary

**Vitya AI** is an intelligent personal finance and productivity web application backend built using **FastAPI**, **SQLAlchemy**, **Scikit-learn**, and **Google Gemini AI**. The application empowers users to track income and expenses, generate financial predictions and budget advice, manage personal notes and tasks with strict multi-tenant isolation, and interact with a multi-layered conversational AI chatbot.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/) | High-performance asynchronous REST API framework |
| **Server** | [Uvicorn](https://www.uvicorn.org/) | ASGI Web Server implementation |
| **Database ORM** | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) | Relational database mapping & session handling |
| **Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Request data parsing & schema validation |
| **Authentication** | [PyJWT](https://pyjwt.readthedocs.io/) / [Jose](https://python-jose.readthedocs.io/) | JWT Token generation and Bearer HTTP verification |
| **Password Security**| [Passlib (bcrypt)](https://passlib.readthedocs.io/) | Password hashing and verification |
| **Machine Learning** | [Scikit-Learn](https://scikit-learn.org/) & [NumPy](https://numpy.org/) | Non-blocking linear regression, overspending & anomaly detection |
| **AI LLM** | [Google GenAI (Gemini)](https://ai.google.dev/) | Generative text responses and fallback AI capabilities |
| **Export / Media** | [Matplotlib](https://matplotlib.org/) & [Pandas](https://pandas.pydata.org/) | Data visualization, charts, and CSV report export |
| **Database Options** | PostgreSQL / Supabase / SQLite | Dynamic DB URL resolution |

---

## 3. High-Level System Architecture

```mermaid
flowchart TD
    Client[Web / Mobile Client] --> |HTTPS Requests + JWT| FastAPI[FastAPI Server - main.py / app.py]
    
    FastAPI --> Auth[JWT Auth Middleware - auth.py]
    Auth --> Routes[API Routers]

    subgraph API Routers
        UserRoute[Users / Profile / Password]
        FinanceRoute[Income & Expense Management]
        AIRoute[ML Analytics & Financial Predictions]
        ExportRoute[CSV & Chart Visualizations]
        ChatRoute[Conversational Assistant]
        ProductivityRoute[Notes & Tasks - User Isolated]
    end

    Routes --> UserRoute
    Routes --> FinanceRoute
    Routes --> AIRoute
    Routes --> ExportRoute
    Routes --> ChatRoute
    Routes --> ProductivityRoute

    ChatRoute --> Handlers[Chat Handler Cascade]
    Handlers --> |Intent: Transaction| TxHandler[Add Expense/Income]
    Handlers --> |Intent: News/Wiki/File| ExtHandler[Third-party / Utility Handlers]
    Handlers --> |Fallback| GeminiService[Google Gemini AI API]

    AIRoute --> |run_in_threadpool| ScikitEngine[Scikit-Learn Regression Engine]
    FinanceRoute --> DB[(SQLAlchemy Engine / DB)]
    UserRoute --> DB
    ProductivityRoute --> DB
```

---

## 4. Codebase Directory Structure & Module Breakdown

```text
backend/
├── app/
│   └── app.py              # Central FastAPI app initialization, middleware, routes mounting
├── api/
│   ├── auth.py             # JWT token creation & authentication dependencies
│   ├── database.py         # SQLAlchemy engine, session maker, DB session dependency
│   ├── models/
│   │   └── vitya.py        # SQLAlchemy ORM models (User, Income, Expense, Note, Task, etc.)
│   ├── routes/
│   │   ├── users.py        # Auth & profile management endpoints
│   │   ├── income.py       # User income CRUD
│   │   ├── expense.py      # User expense CRUD
│   │   ├── ai.py           # Non-blocking prediction, waste analysis, anomaly & budget engine
│   │   └── vitya.py        # Analytics, CSV exports (/csv/expenses, /csv/incomes), trend graphs
│   ├── schemas/
│   │   └── vitya.py        # Pydantic schemas for data validation
│   └── WebApp/
│       ├── notes.py        # Authenticated Notes CRUD endpoints
│       └── tasks.py        # Authenticated Tasks CRUD endpoints
├── chats/
│   ├── chat.py             # Primary /api/chat router entry point
│   ├── chatbot.py          # Chatbot intent router
│   ├── gemini_service.py   # Google Gemini API integration (lazy initialization)
│   ├── presentation_api.py # Presentation & PPT generation endpoints
│   ├── handlers/           # Specialized chat intent handlers (transaction, chart, news, wiki, etc.)
│   └── utils/              # Helper utilities (text parsing, themes, weather, wikipedia)
├── main.py                 # Application launcher (Uvicorn runner for Render/Local)
└── tests/                  # Automated pytest test suites
    ├── conftest.py         # Fixtures for isolated testing database
    ├── test_ai_ml.py       # Non-blocking ML prediction tests
    ├── test_auth.py        # Auth security tests
    ├── test_notes_tasks.py # Multi-tenant isolation tests
    └── test_vitya_routes.py# CSV routes and reset link tests
```

---

## 5. Key System Workflows Explained

### 5.1 Authentication & Security (`backend/api/auth.py` & `users.py`)
- **Registration**: Hashes raw passwords using `bcrypt` via `Passlib` and generates a 48-hour access token upon successful registration.
- **Login**: Verifies credentials and returns a signed JWT containing `user_id`.
- **Protected Endpoints**: Utilize FastAPI's `Depends(token_required)` dependency to extract the Bearer token, decode the payload, and inject the authenticated `current_user` object.
- **Password Reset**: Generates a short-lived (15-minute) token with `"purpose": "password_reset"` using dynamic `FRONTEND_URL` configuration.

### 5.2 Multi-Tenant Data Isolation (`backend/api/models/vitya.py`, `notes.py`, `tasks.py`)
- **User Scoping**: Both `Note` and `Task` models contain `user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)`.
- **Strict Authorization**: Notes and Tasks API endpoints require `Depends(token_required)` and query strictly by `Note.user_id == current_user.id` and `Task.user_id == current_user.id`.

### 5.3 Non-Blocking Financial Intelligence & ML Engine (`backend/api/routes/ai.py`)
- **Expense Prediction (`/api/ai/predict/{category}`)**: Trains a `LinearRegression` model on historical category amounts to forecast next month's spending. Execution is offloaded to worker threads via `run_in_threadpool`, ensuring the main event loop is never blocked.
- **Overspending Alert (`/api/ai/overspending/{category}`)**: Checks if the latest transaction exceeds 1.5x the historical category average.
- **Smart Budget Planning (`/api/ai/budget-plan`)**: 
  1. Calculates income-tiered savings (10% for <₹20k, 20% for <₹50k, 30% for higher).
  2. Allocates usable funds proportionately across category spending history with a 5% floor guarantee per active category.
- **Waste & Anomaly Detection (`/api/ai/waste-analysis`, `/api/ai/anomaly/{category}`)**: Identifies spending spikes (>2x average) and flags high-velocity expense categories.

### 5.4 Multi-Stage AI Assistant (`backend/chats/`)
When a user sends a message to `/api/chat/`, the request flows through a priority cascade:
1. **Specialized Handlers**: Checked in order: File downloads -> News search -> Wikipedia lookup.
2. **Intent Classifier (`chatbot.py`)**:
   - **Transaction Handler**: Parses natural language expenses/incomes (e.g. *"Spent 250 on groceries"*).
   - **Chart Handler**: Generates visual financial charts based on chat prompt.
   - **Utility Handler**: Performs calculations or unit conversions.
   - **Info Handler**: Responds to platform capability questions.
3. **Gemini Fallback (`gemini_service.py`)**: Direct call to `gemini-flash-latest` model for unhandled natural language queries.

---

## 6. Completed Audits & Resolved Maintenance Items

> [!NOTE]
> **Recently Completed Security & System Upgrades**:
> 1. ✅ **Multi-Tenant User Isolation in Notes & Tasks**: Added `user_id` foreign keys to `Note` and `Task` models and enforced `token_required` scoping across all CRUD routes.
> 2. ✅ **Route Disambiguation**: Resolved `@router.get("/csv")` route collision in `vitya.py` by establishing distinct `/csv/expenses` and `/csv/incomes` endpoints.
> 3. ✅ **Dynamic Environment URLs**: Replaced hardcoded `localhost` password reset URLs with environment-driven `FRONTEND_URL` resolution.
> 4. ✅ **Non-blocking Async ML Execution**: Offloaded Scikit-learn CPU-bound computations to thread pools via `run_in_threadpool`.
> 5. ✅ **Automated Testing Suite**: Added comprehensive `pytest` test suite covering authentication, user isolation, distinct routes, and ML predictions.

---

## 7. Actionable Next Steps & Development Roadmap

### Phase 1: Security, Data Privacy & Infrastructure (Status: Completed ✅)
- [x] **Multi-Tenant Data Isolation**: Add `user_id` foreign key to `Note` and `Task` models and filter query results by `current_user.id`.
- [x] **Route Clean Up**: Disambiguate CSV endpoints in `vitya.py` into `/csv/expenses` and `/csv/incomes`.
- [x] **Environment Variable Hardening**: Replace hardcoded `localhost` URLs with `FRONTEND_URL` from `.env`.
- [x] **Non-blocking ML Execution**: Wrap CPU-bound Scikit-learn operations with `run_in_threadpool`.
- [x] **Automated Test Coverage**: Build `tests/` directory with `pytest` suite for Auth, Notes/Tasks isolation, CSV routes, and ML predictions.

### Phase 2: System Quality & Database Operations (Target: Sprint 2)
- [ ] **Alembic Database Migrations**: Integrate Alembic for schema migrations instead of relying solely on `Base.metadata.create_all()` at startup.
- [ ] **Async Worker Tasks**: Offload heavy presentation generation (`presentation_api.py`) and PDF exports to background workers.
- [ ] **Centralized Structured Logging**: Enhance logging with structured JSON output and custom exception middleware.
- [ ] **Input Sanitization & Validation**: Add strict Pydantic rules for transaction amounts (> 0), valid date formats, and file upload validation.

### Phase 3: Feature Enhancements & Advanced Intelligence (Target: Sprint 3)
- [ ] **Chat Memory & Persistence**: Connect `ChatMessage` and `Conversation` models in `vitya.py` to the chat pipeline to enable multi-turn conversational context.
- [ ] **Budget Cap Alerts**: Allow users to set fixed monthly category budgets and trigger push/email notifications when approaching limits.
- [ ] **Multi-Currency Support**: Support currency selection per user with conversion rates.
- [ ] **Interactive Dashboard Integration**: Enhance API response payloads with predefined UI component metadata for seamless frontend rendering.

---

## 🙏 Special Thanks & Acknowledgments

Heartfelt gratitude to everyone who contributed to making **Vitya AI** a reality:

- **Open Source Community**: Special thanks to the creators and maintainers of **FastAPI**, **SQLAlchemy**, **Pydantic**, and **Scikit-Learn** for providing world-class tools.
- **Google DeepMind & Gemini Team**: Thank you for empowering smart, context-aware artificial intelligence via the Google Gemini AI Platform.
- **Cloud & Infrastructure Partners**: Gratitude to cloud hosting providers for enabling reliable, seamless application deployment.
- **Our Beta Testers & Community**: Special thanks to our early adopters and users whose continuous feedback drives the evolution of Vitya AI into an empowered financial assistant.
