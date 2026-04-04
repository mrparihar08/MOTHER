from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# ---------------------------
# DATABASE URL
# ---------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL is not set in environment variables")

# Fix old postgres scheme (for Heroku / older configs)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ---------------------------
# ENGINE CONFIG
# ---------------------------
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,        # ✅ avoids stale connections
    pool_size=5,               # ✅ base pool size
    max_overflow=10,           # ✅ extra connections
    pool_timeout=30,           # ✅ wait time
    pool_recycle=1800,         # ✅ reset connections (important for cloud DBs)
    echo=False                 # ❌ disable SQL logs in prod
)

# Special handling for SQLite (only for dev/testing)
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

# ---------------------------
# SESSION
# ---------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ---------------------------
# BASE MODEL
# ---------------------------
Base = declarative_base()

# ---------------------------
# DEPENDENCY (FastAPI)
# ---------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()   # ✅ rollback on error
        raise
    finally:
        db.close()