"""
Database connection and session factory for Finance Service.
Uses its own isolated database instance (Port 8002).
"""
from shared.database.base import create_service_db

engine, SessionLocal, Base, get_db = create_service_db(
    db_url_env_var="FINANCE_DATABASE_URL",
    default_sqlite_file="finance.db",
)
