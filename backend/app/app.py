from fastapi import FastAPI, HTTPException

from fastapi.middleware.cors import CORSMiddleware
import os
import logging

from backend.api.database import engine
from backend.api.models.vitya import Base

from backend.api.routes import users, income, expense, vitya, ai
from backend.chats import chat

# ---------------------------
# LOGGING
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------
# APP INIT
# ---------------------------
app = FastAPI(
    title="Vitya AI API",
    version="1.0.0",
    docs_url="/docs",         # disable in prod if needed
    redoc_url=None
)

# ---------------------------
# STARTUP EVENT (DB INIT)
# ---------------------------
@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        logging.info("✅ Database connected & tables created")
    except Exception as e:
        logging.error(f"❌ DB connection failed: {e}")
        raise

# ---------------------------
# CORS CONFIG
# ---------------------------
DEFAULT_ORIGINS = [
    "https://vitya-expense.onrender.com",
    "https://vitya-chat.onrender.com",
    "http://localhost:3000",
    "http://192.168.1.17:3000"
    
]

cors_origins = os.getenv("CORS_ORIGINS")

if cors_origins:
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
else:
    origins = DEFAULT_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # safer than "*"
    allow_headers=["*"],
)
@app.get("/")
def root():
    return {"message": "API is running"}

# ---------------------------
# HEALTH CHECK (IMPORTANT)
# ---------------------------
@app.get("/health")
def health_check():
    return {"status": "ok"}

# ---------------------------
# ROUTERS
# ---------------------------
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(income.router, prefix="/api/income", tags=["Income"])
app.include_router(expense.router, prefix="/api/expense", tags=["Expense"])
app.include_router(vitya.router, prefix="/api/vitya", tags=["Vitya"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])