from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging

from backend.finance.analysis import analyse, savings
from backend.finance.routes import expense, income, vitya
from backend.api.database import engine
from backend.api.models.vitya import Base
from fastapi.responses import Response
from backend.api.routes import users, settings, subscriptions
from backend.api.WebApp import notes, tasks, calendar
from backend.chats import chat
from backend.presentation import presentation_api
from backend.chats.routes import rag_routes
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
        Base.metadata.create_all(bind=engine)
        logging.info("✅ Database connected & tables created")
    except Exception as e:
        logging.error(f"❌ DB connection failed: {e}")
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
    "https://security-vitya.onrender.com",
    "https://admin-vitya.onrender.com",
    "https://tourist-vitya.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:10000",
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
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.onrender\.com$",
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
# ---------------------------
# ROUTES
# ---------------------------
app.include_router(users.router, prefix="/api/users", tags=["Users & Authentication"])
app.include_router(income.router, prefix="/api/income", tags=["Income Management"])
app.include_router(expense.router, prefix="/api/expense", tags=["Expense Management"])
app.include_router(vitya.router, prefix="/api/vitya", tags=["Vitya AI"])
app.include_router(analyse.router, prefix="/api/analyse", tags=["Analyse & Insights"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat & Conversations"])
app.include_router(rag_routes.router, prefix="/api/rag", tags=["RAG Routes"])
app.include_router(presentation_api.router, prefix="/api/presentation", tags=["Presentation API Routes"])
app.include_router(notes.router, prefix="/api/notes", tags=["Notes Management"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks Management"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendar Management"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings Management"])
app.include_router(savings.router, prefix="/api/savings", tags=["Savings Goals Management"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Subscriptions Management"])
app.include_router(dora_router, prefix="/api/dora", tags=["DORA Health Intelligence Routes"])

# ---------------------------
# STATIC FILES (UPLOAD & ASSETS FIX)
# ---------------------------
UPLOAD_DIR = "uploads"
ASSET_DIR = "assets"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

if not os.path.exists(ASSET_DIR):
    os.makedirs(ASSET_DIR)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")
