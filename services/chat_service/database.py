"""
Database connection and session factory for Chat Service (Port 8003).
"""
from shared.database.base import create_service_db

engine, SessionLocal, Base, get_db = create_service_db(
    db_url_env_var="CHAT_DATABASE_URL",
    default_sqlite_file="chat.db",
)
