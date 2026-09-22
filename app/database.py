"""
Database engine & session management.

Uses SQLite for the prototype (file-based, zero external dependency) so the
service runs end-to-end with no infra setup. The engine is swappable for
Postgres/MySQL in production by changing DATABASE_URL only -- no code in
crud.py or models.py is DB-engine specific.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./urlshortener.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Imported here (not at module top) to avoid circular imports with models.py
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
