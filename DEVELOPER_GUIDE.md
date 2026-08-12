# Vitya AI — Developer Guide

## 1. Purpose

This guide provides developers with a comprehensive reference to understand, build, extend, and maintain the **Vitya AI** backend architecture.

Vitya AI is designed as a modular, high-performance personal finance & productivity API offering:
- Multi-tenant User Authentication & Authorization
- Income & Expense Tracking with User Isolation
- Non-blocking Machine Learning Financial Insights
- Multi-stage Conversational AI Assistant (Google Gemini Integration)
- Authenticated Notes & Task Management

---

## 2. Architecture & Design Principles

The application is structured into three primary architectural layers:

### A. Presentation / Client Layer
Handles user interactions via web frontend, mobile applications, or API clients sending JSON HTTP requests.

### B. API & Application Layer (FastAPI)
Acts as the central request router, handling input validation (Pydantic), authentication dependencies (PyJWT/Passlib), background worker dispatching (`run_in_threadpool`), and business logic orchestration.

### C. Data & Model Layer (SQLAlchemy 2.0)
Manages relational data persistence, schema migrations, object-relational mapping (ORM), and transaction boundaries.

---

## 3. Directory Structure

```text
backend/
├── app/
│   └── app.py              # Application initialization, middleware, router mounts
├── api/
│   ├── auth.py             # Security dependencies, JWT token generation & verification
│   ├── database.py         # SQLAlchemy engine, session maker, DB session dependency
│   ├── models/
│   │   └── vitya.py        # SQLAlchemy ORM models (User, Income, Expense, Note, Task, etc.)
│   ├── routes/
│   │   ├── users.py        # Auth & user profile endpoints
│   │   ├── income.py       # Income CRUD operations
│   │   ├── expense.py      # Expense CRUD operations
│   │   ├── ai.py           # Non-blocking ML prediction & financial insights
│   │   └── vitya.py        # CSV report exports & financial analytics
│   ├── schemas/
│   │   └── vitya.py        # Pydantic schemas for data validation
│   └── WebApp/
│       ├── notes.py        # User-isolated Notes CRUD
│       └── tasks.py        # User-isolated Tasks CRUD
├── chats/
│   ├── chat.py             # Main chat router
│   ├── chatbot.py          # Intent classification engine
│   ├── gemini_service.py   # Google Gemini API integration (lazy loaded)
│   ├── handlers/           # Transaction, chart, news, wiki, and utility handlers
│   └── utils/              # Media generators, weather & wikipedia helpers
├── main.py                 # ASGI application server launcher
└── tests/                  # Automated pytest test suites
```

---

## 4. Application Lifecycle & Startup

The backend entry point is [backend/main.py](backend/main.py), which starts the Uvicorn ASGI server:

```python
def start():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app.app:app", host="0.0.0.0", port=port)
```

The FastAPI application setup resides in [backend/app/app.py](backend/app/app.py):

### Startup Flow:
1. **Instantiation**: `FastAPI` instance is initialized.
2. **Database Initialization**: `Base.metadata.create_all(bind=engine)` creates database tables automatically on startup.
3. **CORS Middleware**: CORS rules are injected dynamically using `CORS_ORIGINS` environment variables.
4. **Router Mounting**: API routers for users, income, expense, AI, vitya analytics, chat, presentation, notes, and tasks are registered.
5. **Static File Mounting**: `/uploads` directory is mounted for media asset serving.

---

## 5. Core Components Deep Dive

### 5.1 Database Session Management (`backend/api/database.py`)
Provides the `get_db()` dependency for FastAPI route functions:
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 5.2 Multi-Tenant Data Models (`backend/api/models/vitya.py`)
All core entities (`Income`, `Expense`, `Note`, `Task`, `Conversation`) implement foreign key relationships referencing `User.id` with cascade deletion (`ondelete="CASCADE"`):

```python
class Note(Base, TimestampMixin):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user = relationship("User", back_populates="notes")
```

### 5.3 Authentication & Dependency Injection (`backend/api/auth.py`)
Routes requiring authentication declare `current_user: User = Depends(token_required)`. This dependency extracts the `Authorization: Bearer <token>` header, decodes the JWT payload, validates expiration, and injects the authenticated `User` ORM instance.

---

## 6. Machine Learning Engine & Non-Blocking Execution

CPU-bound Scikit-Learn computations (such as Linear Regression model fitting in `/api/ai/predict/{category}`) are executed inside `async def` endpoints using `fastapi.concurrency.run_in_threadpool`:

```python
@router.get("/predict/{category}")
async def predict_expense(category: str, current_user=Depends(token_required), db: Session = Depends(get_db)):
    ...
    prediction = await run_in_threadpool(_fit_and_predict_linear_model, amounts)
    return {"category": category, "predicted_next_month_expense": round(prediction, 2)}
```

This prevents heavy ML calculations from blocking the asyncio event loop.

---

## 7. How to Add a New API Feature

Follow this standard 5-step implementation workflow:

1. **Define/Update Model**: Update `backend/api/models/vitya.py` with required fields and foreign keys.
2. **Define Pydantic Schemas**: Add request validation and response schemas in `backend/api/schemas/vitya.py`.
3. **Implement Endpoint Router**: Create route handlers using `Depends(get_db)` and `Depends(token_required)`.
4. **Register Router**: Mount the router in `backend/app/app.py`.
5. **Write Automated Tests**: Add test coverage under `tests/` using shared fixtures in `tests/conftest.py`.

---

## 8. Running Automated Tests

Execute the complete test suite using `pytest`:

```bash
python -m pytest
```

The test runner utilizes `tests/conftest.py` with an isolated SQLite in-memory database instance to execute unit and integration tests cleanly without affecting local databases.

---

## 🙏 Special Thanks & Acknowledgments

Heartfelt gratitude to everyone who contributed to making **Vitya AI** a reality:

- **Open Source Community**: Special thanks to the creators and maintainers of **FastAPI**, **SQLAlchemy**, **Pydantic**, and **Scikit-Learn** for providing world-class tools.
- **Google DeepMind & Gemini Team**: Thank you for empowering smart, context-aware artificial intelligence via the Google Gemini AI Platform.
- **Cloud & Infrastructure Partners**: Gratitude to cloud hosting providers for enabling reliable, seamless application deployment.
- **Our Beta Testers & Community**: Special thanks to our early adopters and users whose continuous feedback drives the evolution of Vitya AI into an empowered financial assistant.
