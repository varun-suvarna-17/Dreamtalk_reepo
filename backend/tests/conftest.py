"""
pytest configuration and fixtures for DreamTalk backend tests.

Uses a file-based SQLite test database (reset between tests) to avoid the
main.py module-level ``Base.metadata.create_all(bind=engine)`` call
creating tables on the real engine.  All LLM calls are mocked — no API
key is needed to run the suite.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# Test database — separate file so it doesn't pollute dreamtalk.db
# ---------------------------------------------------------------------------

_TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "_test_dreamtalk.db")
TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH}"

_test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override DB dependency at module import so it is active before TestClient starts.
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_db():
    """Drop and recreate all tables before each test for isolation."""
    Base.metadata.drop_all(bind=_test_engine)
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)


# ---------------------------------------------------------------------------
# TestClient fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """FastAPI TestClient using the test database."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
