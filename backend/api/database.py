from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# ---------------------------
# DATABASE URL
# ---------------------------
DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL / SUPABASE_DATABASE_URL is not set in environment variables")

# Fix old postgres scheme (for Heroku / older configs)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ---------------------------
# ENGINE CONFIG
# ---------------------------
engine_kwargs = {
    "pool_pre_ping": True,
    "echo": False,
}

# SQLite needs special handling
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        **engine_kwargs,
    )

# ---------------------------
# SESSION
# ---------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
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
        db.rollback()
        raise
    finally:
        db.close()