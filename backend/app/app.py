from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.database import engine
from backend.api.models.vitya import Base
from backend.api.routes import users, income, expense, vitya, ai
from backend.chats import chat, presentation_api

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("vitya-api")

# -----------------------------------------------------------------------------
# CORS
# -----------------------------------------------------------------------------
DEFAULT_ORIGINS = [
    "https://vitya-expense.onrender.com",
    "https://vitya-chat.onrender.com",
    "http://localhost:3000",
    "http://192.168.1.17:3000",
]


def get_cors_origins() -> List[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        return origins or DEFAULT_ORIGINS
    return DEFAULT_ORIGINS


# -----------------------------------------------------------------------------
# App settings
# -----------------------------------------------------------------------------
APP_TITLE = os.getenv("APP_TITLE", "Vitya AI API")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true").lower() == "true"

# -----------------------------------------------------------------------------
# Lifespan
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database connected and tables created")
    except Exception:
        logger.exception("Database startup failed")
        raise

    yield

    logger.info("Application shutdown complete")


# -----------------------------------------------------------------------------
# App init
# -----------------------------------------------------------------------------
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "API is running", "status": "ok"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(income.router, prefix="/api/income", tags=["Income"])
app.include_router(expense.router, prefix="/api/expense", tags=["Expense"])
app.include_router(vitya.router, prefix="/api/vitya", tags=["Vitya"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(presentation_api.router, prefix="/api/presentation", tags=["Presentation"])