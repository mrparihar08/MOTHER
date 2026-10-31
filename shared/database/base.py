"""
Database Factory for Microservices Isolation.
Allows each service to have its own isolated engine, sessionmaker, and declarative base.
"""
import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session


def create_service_db(db_url_env_var: str, default_sqlite_file: str):
    """
    Creates an independent database engine, SessionLocal, and declarative Base for a microservice.
    """
    database_url = os.getenv(db_url_env_var)
    if not database_url:
        os.makedirs("instance", exist_ok=True)
        database_url = f"sqlite:///./instance/{default_sqlite_file}"

    # SQLite connection args
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    ServiceSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    ServiceBase = declarative_base()

    def get_db() -> Generator[Session, None, None]:
        db = ServiceSessionLocal()
        try:
            yield db
        finally:
            db.close()

    return engine, ServiceSessionLocal, ServiceBase, get_db
