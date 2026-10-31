"""
Database connection and session factory for Presentation Studio Service (Port 8005).
"""
from shared.database.base import create_service_db

engine, SessionLocal, Base, get_db = create_service_db(
    db_url_env_var="PRESENTATION_DATABASE_URL",
    default_sqlite_file="presentation.db",
)
