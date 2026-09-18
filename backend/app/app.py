from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging

from backend.api.database import engine
from backend.api.models.vitya import Base
from fastapi.responses import Response
from backend.api.routes import users, income, expense, vitya, ai
from backend.api.WebApp import notes, tasks
from backend.chats import chat
from backend.chats.presentation import presentation_api
from backend.chats.routes import rag_routes

# ---------------------------
# LOGGING
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------
# LIFESPAN
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
origins = os.getenv("CORS_ORIGINS")

if origins:
    origins = [o.strip() for o in origins.split(",")]
else:
    origins = [
        "https://vitya-expense.onrender.com",
        "https://vitya-chat.onrender.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],     # FIXED (no issue now)
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
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(income.router, prefix="/api/income", tags=["Income"])
app.include_router(expense.router, prefix="/api/expense", tags=["Expense"])
app.include_router(vitya.router, prefix="/api/vitya", tags=["Vitya"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(rag_routes.router, prefix="/api/rag", tags=["RAG"])
app.include_router(presentation_api.router, prefix="/api/presentation", tags=["Presentation"])
app.include_router(notes.router, prefix="/api/notes", tags=["Notes"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])

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