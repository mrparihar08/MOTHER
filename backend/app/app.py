from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.finance.analysis import analyse, savings
from backend.finance.routes import expense, income, vitya, scan_ledger_routes
from backend.api.database import engine
from backend.api.models.vitya import Base
from fastapi.responses import Response
from backend.api.routes import users, settings, subscriptions, automations, voice_notes_routes, notifications, storage_routes
from backend.api.WebApp import notes, tasks, calendar
from backend.chats import chat
from backend.chats import VoiceAssistant as voice_assistant
from backend.presentation import presentation_api
from backend.chats.routes import rag_routes, research_routes
from backend.dora import router as dora_router

# ---------------------------
# LOGGING
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------
# LIFESPAN & TABLE CREATION
# ---------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from alembic.config import Config
        from alembic import command
        alembic_ini_path = os.path.join(ROOT_DIR, "alembic.ini")
        if os.path.exists(alembic_ini_path):
            cfg = Config(alembic_ini_path)
            command.upgrade(cfg, "head")
            logging.info("✅ Database schema migrated to latest version via Alembic")
        else:
            Base.metadata.create_all(bind=engine)
            logging.info("✅ Database connected & tables created")
    except Exception as e:
        logging.warning(f"⚠️ Alembic migration note: {e}. Ensuring tables via metadata.create_all")
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as err:
            logging.error(f"❌ DB connection failed: {err}")
            # Ensure user_conv_index column exists on SQLite/PostgreSQL
        try:
            with engine.connect() as conn:
                from sqlalchemy import text
                for col_sql in [
                    "ALTER TABLE conversations ADD COLUMN user_conv_index INTEGER",
                    "ALTER TABLE conversations ADD COLUMN conversation_summary TEXT",
                    "ALTER TABLE chat_messages ADD COLUMN user_id INTEGER",
                    "ALTER TABLE chat_messages ADD COLUMN input_mode VARCHAR(20) DEFAULT 'chat'",
                    "ALTER TABLE chat_messages ADD COLUMN message_status VARCHAR(20) DEFAULT 'completed'",
                    "ALTER TABLE chat_messages ADD COLUMN meta_info TEXT",
                ]:
                    try:
                        conn.execute(text(col_sql))
                        conn.commit()
                    except Exception:
                        pass
                logging.info("Ensured unified conversation & voice message schema columns")
        except Exception as mig_err:
            logging.debug(f"Schema columns verify: {mig_err}")
    yield

# ---------------------------
# APP INIT
# ---------------------------
app = FastAPI(
    title="Vitya AI API",
    version="1.0.0",
    docs_url="/docs",   # disable later if needed
    redoc_url=None,
    lifespan=lifespan,
)

# ---------------------------
# CORS CONFIG (VERY IMPORTANT FIX)
# ---------------------------
origins_env = os.getenv("CORS_ORIGINS", "").strip()
default_origins = [
    "https://vitya-expense.onrender.com",
    "https://vitya-chat.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:10000",
    "http://127.0.0.1:10000",
    "capacitor://localhost",
]

if origins_env and origins_env != "*":
    origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    for o in default_origins:
        if o not in origins:
            origins.append(o)
else:
    origins = default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^(https?|capacitor)://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$|^https://.*\.onrender\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# ROOT + HEALTH
# ---------------------------
@app.get("/")
def root():
    return {"message": "API is running 🚀"}

@app.get("/health")
def health():
    return {"status": "ok"}
@app.head("/health")
def health_head():
    return Response(status_code=200)

@app.get("/google874c7225877a9829.html")
def google_verification():
    return Response(content="google-site-verification: google874c7225877a9829.html", media_type="text/html")
# ---------------------------
# ROUTES: SHARED PLATFORM CORE
# ---------------------------
app.include_router(users.router, prefix="/api/users", tags=["Shared Core - Users & Authentication"])
app.include_router(users.router, prefix="/api/auth", tags=["Shared Core - Users & Authentication (Alias)"])
app.include_router(settings.router, prefix="/api/settings", tags=["Shared Core - Settings & Preferences"])
app.include_router(chat.router, prefix="/api/chat", tags=["Shared Core - Chat & Agent Dispatcher"])
app.include_router(voice_assistant.router, prefix="/api/voice-assistant", tags=["Shared Core - Real-Time AI Voice Assistant"])
app.include_router(rag_routes.router, prefix="/api/rag", tags=["Shared Core - RAG Documents"])
app.include_router(research_routes.router, prefix="/api/research", tags=["Research Lab - Deep Document Intelligence"])
app.include_router(notes.router, prefix="/api/notes", tags=["Shared Core - Notes Management"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Shared Core - Tasks Management"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["Shared Core - Calendar Management"])
app.include_router(automations.router, prefix="/api/automations", tags=["Shared Core - Neural Automations & Routines"])
app.include_router(voice_notes_routes.router, prefix="/api/voice-notes", tags=["Voice Meeting & Audio Brain - Whisper Intelligence"])
app.include_router(notifications.router, prefix="/api/v1", tags=["Shared Core - Notifications & Web Push"])
app.include_router(notifications.router, prefix="/api", tags=["Shared Core - Notifications & Web Push (Alias)"])
app.include_router(storage_routes.router, prefix="/api/storage", tags=["Shared Core - Object Storage & Presigned URLs"])

# ---------------------------
# ROUTES: MODULE 1 — PRESENTATION STUDIO
# ---------------------------
app.include_router(presentation_api.router, prefix="/api/presentation", tags=["Presentation Studio - Deck Generation"])

# ---------------------------
# ROUTES: MODULE 2 — DORA DR.
# ---------------------------
app.include_router(dora_router, prefix="/api/dora", tags=["Dora Dr. - Clinical Health Intelligence"])

# ---------------------------
# ROUTES: MODULE 3 — VIDYA ADVISOR (Finance, Expense, Income)
# ---------------------------
app.include_router(income.router, prefix="/api/income", tags=["Vidya- Income Management"])
app.include_router(expense.router, prefix="/api/expense", tags=["Vidya- Expense Management"])
app.include_router(vitya.router, prefix="/api/vitya", tags=["Vidya- Telemetry & Analytics"])
app.include_router(analyse.router, prefix="/api/analyse", tags=["Vidya- Analysis & Predictive AI"])
# Backward-compatible alias: Frontend client directly queries /api/ai for health score, predictions, and budget caps
app.include_router(analyse.router, prefix="/api/ai", tags=["Vidya- AI Financial Intelligence (Alias)"])
app.include_router(savings.router, prefix="/api/savings", tags=["Vidya- Savings Goals"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Vidya- Subscriptions"])
app.include_router(scan_ledger_routes.router, prefix="/api/scan-ledger", tags=["Vidya- AI Vision & Receipt Ledger"])

# Chat export backward-compatibility alias (without /api prefix)
app.add_api_route("/chat/export", chat.export_chat_endpoint, methods=["POST"], tags=["Shared Core - Chat & Agent Dispatcher (Alias)"])

# ---------------------------
# STATIC FILES (UPLOAD, ASSETS & OUTPUTS FIX)
# ---------------------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UPLOAD_DIR = os.path.join(ROOT_DIR, "uploads")
ASSET_DIR = os.path.join(ROOT_DIR, "assets")
OUTPUT_DIR = os.path.join(ROOT_DIR, "outputs")

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

if not os.path.exists(ASSET_DIR):
    os.makedirs(ASSET_DIR)

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

