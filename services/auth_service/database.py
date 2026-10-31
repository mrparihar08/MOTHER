"""
Database Connection & Session Factory for Auth Service.
Isolated from other services.
"""
from shared.database.base import create_service_db

engine, SessionLocal, Base, get_db = create_service_db(
    db_url_env_var="AUTH_DATABASE_URL",
    default_sqlite_file="auth.db",
)
