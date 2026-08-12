# Vitya AI — Intelligent Financial & Productivity Assistant

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python)](https://www.python.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg?style=flat&logo=sqlalchemy)](https://www.sqlalchemy.org/)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-ML-F7931E.svg?style=flat&logo=scikit-learn)](https://scikit-learn.org/)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-AI-4285F4.svg?style=flat&logo=googlecloud)](https://ai.google.dev/)
[![Pytest](https://img.shields.io/badge/Pytest-Passed-success.svg?style=flat&logo=pytest)](https://docs.pytest.org/)

**Vitya AI** is an enterprise-ready, multi-tenant personal finance management and productivity backend. Built on **FastAPI**, **SQLAlchemy**, **Scikit-learn**, and **Google Gemini AI**, Vitya AI enables users to track income and expenses, receive ML-driven financial forecasts, manage private notes and tasks with strict multi-tenant isolation, and interact with a multi-layered conversational AI assistant.

---

## 🚀 Key Features

### 🔐 1. Authentication & Security
- **Multi-Tenant User Isolation**: All financial data, notes, and tasks are strictly scoped to the authenticated user via foreign key relationships and JWT bearer tokens.
- **JWT Token Authentication**: Secure token generation (48-hour access tokens, 15-minute password reset tokens).
- **Password Security**: Hashing using `bcrypt` via `Passlib`.
- **Dynamic Configuration**: Support for environment-driven `FRONTEND_URL` for password reset link generation.

### 💰 2. Personal Finance Tracking
- **Income Management**: Record, retrieve, update, and remove income entries.
- **Expense Management**: Track expenses by amount, category, description, and date.
- **CSV Data Exports**: Dedicated endpoints `/api/vitya/csv/expenses` and `/api/vitya/csv/incomes` for offline report generation.
- **Financial Analytics**: Real-time spending distributions, monthly trend calculations, and recent transaction summaries.

### 🧠 3. ML-Driven Financial Insights
- **Expense Prediction**: Non-blocking Scikit-learn `LinearRegression` engine forecasting upcoming monthly category expenses (`/api/ai/predict/{category}`).
- **Overspending Detection**: Automatic detection of transaction spikes exceeding 1.5x historical category averages.
- **Smart Savings & Budget Planning**: Income-tiered savings allocation (10% to 30%) with proportional category budgeting.
- **Waste & Anomaly Analysis**: Multi-variance analysis flagging unusual expense spikes (>2x category average).

### 🤖 4. Conversational AI Assistant
- **Multi-Stage Intent Router**: Automatic parsing of natural language transactions (e.g., *"Spent 250 on groceries"*).
- **Specialized Utility Handlers**: Dynamic generation of QR codes, barcodes, financial summaries, and weather reports.
- **Gemini AI Integration**: Seamless fallback to Google Gemini (`gemini-flash-latest`) for unhandled natural language queries.

### 📝 5. User Notes & Tasks
- **Private Notes**: Secure creation, editing, listing, and deletion of personal notes.
- **Task Management**: Simple task tracking with full multi-tenant security guarantees.

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/) | Asynchronous REST API framework |
| **Database ORM** | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) | Relational database mapping & session management |
| **Data Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Request parsing and schema enforcement |
| **Authentication** | [PyJWT](https://pyjwt.readthedocs.io/) / [Passlib](https://passlib.readthedocs.io/) | Bearer tokens & password hashing |
| **Machine Learning** | [Scikit-Learn](https://scikit-learn.org/) & [NumPy](https://numpy.org/) | Non-blocking linear regression & anomaly detection |
| **AI LLM** | [Google Gemini AI](https://ai.google.dev/) | Generative AI assistant fallback |
| **Testing** | [Pytest](https://docs.pytest.org/) | Unit and integration test suite |
| **Database** | PostgreSQL / Supabase / SQLite | Dynamic database support |

---

## 📂 Project Architecture

```text
backend/
├── app/
│   └── app.py              # Central FastAPI app initialization, middleware, routes
├── api/
│   ├── auth.py             # JWT token creation & authentication dependencies
│   ├── database.py         # SQLAlchemy engine, session maker, DB session dependency
│   ├── models/
│   │   └── vitya.py        # SQLAlchemy ORM models (User, Income, Expense, Note, Task)
│   ├── routes/
│   │   ├── users.py        # Auth, profile & password recovery endpoints
│   │   ├── income.py       # User income CRUD
│   │   ├── expense.py      # User expense CRUD
│   │   ├── ai.py           # Non-blocking ML prediction & budget engine
│   │   └── vitya.py        # CSV exports, trend graphs & financial overview
│   ├── schemas/
│   │   └── vitya.py        # Pydantic data schemas
│   └── WebApp/
│       ├── notes.py        # Authenticated Notes CRUD
│       └── tasks.py        # Authenticated Tasks CRUD
├── chats/
│   ├── chat.py             # Main /api/chat router
│   ├── chatbot.py          # Intent cascade router
│   ├── gemini_service.py   # Google Gemini API integration
│   ├── handlers/           # Transaction, chart, utility, info handlers
│   └── utils/              # Media generation & API helpers
└── main.py                 # Application launcher (Uvicorn runner)
```

---

## 🛠️ Local Installation & Development

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/mrparihar08/MOTHER.git
cd MOTHER
python -m venv venv
```

Activate the environment:
- **Windows**: `venv\Scripts\activate`
- **Linux/macOS**: `source venv/bin/activate`

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory:
```env
SECRET_KEY=your_super_secret_jwt_key
DATABASE_URL=sqlite:///./instance/test.db
FRONTEND_URL=http://localhost:3000
GEMINI_API_KEY=your_google_gemini_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
```

### 4. Run the Server
```bash
python backend/main.py
```
The server will start at `http://localhost:10000`. Swagger API documentation is accessible at `http://localhost:10000/docs`.

---

## 🧪 Testing

Run the automated test suite with `pytest`:
```bash
python -m pytest
```

The test suite validates:
- Multi-tenant data isolation across Notes & Tasks
- Independent CSV export routes (`/csv/expenses`, `/csv/incomes`)
- Dynamic `FRONTEND_URL` resolution in password reset links
- Asynchronous non-blocking execution of Scikit-learn predictions

---

## ☁️ Deployment

The repository includes a ready-to-use `render.yaml` for one-click deployment on **Render**:
- **Backend API Service**: Web service running `python backend/main.py`
- **PostgreSQL Database**: Managed relational database instance

---

## 🙏 Special Thanks & Acknowledgments

Heartfelt gratitude to everyone who contributed to making **Vitya AI** a reality:

- **Open Source Community**: Special thanks to the creators and maintainers of **FastAPI**, **SQLAlchemy**, **Pydantic**, and **Scikit-Learn** for providing world-class tools.
- **Google DeepMind & Gemini Team**: Thank you for empowering smart, context-aware artificial intelligence via the Google Gemini AI Platform.
- **Cloud & Infrastructure Partners**: Gratitude to cloud hosting providers for enabling reliable, seamless application deployment.
- **Our Beta Testers & Community**: Special thanks to our early adopters and users whose continuous feedback drives the evolution of Vitya AI into an empowered financial assistant.
