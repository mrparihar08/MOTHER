import os
import logging
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# -----------------------------
# DATABASE URL
# -----------------------------
DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL") or "sqlite:///./instance/app.db"

# Fix old postgres:// format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

# -----------------------------
# ENGINE CREATION WITH FALLBACK
# -----------------------------
engine = None

if DATABASE_URL.startswith("sqlite"):
    if "sqlite:///" in DATABASE_URL:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        if db_path and not db_path.startswith(":memory:"):
            Path(db_path).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=10,
            echo=False
        )
    except Exception as exc:
        logger.error("Failed to initialize PostgreSQL engine with URL (%s): %s. Falling back to SQLite.", DATABASE_URL[:20], exc)
        db_path = "./instance/app.db"
        Path(db_path).resolve().parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )

# -----------------------------
# SESSION
# -----------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# -----------------------------
# BASE
# -----------------------------
Base = declarative_base()

# -----------------------------
# DATABASE DEPENDENCY
# -----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()