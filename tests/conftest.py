import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, get_db


@pytest.fixture()
def client():
    """
    Fresh in-memory SQLite DB per test, wired in via FastAPI's dependency
    override -- avoids any module-reload trickery and keeps tests isolated
    and fast.

    StaticPool is required for SQLite ":memory:": without it, each new
    connection checkout gets its own separate empty in-memory database,
    so the tables created up front would be invisible to the session used
    inside request handlers.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
