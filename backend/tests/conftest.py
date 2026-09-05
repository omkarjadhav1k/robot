"""Pytest fixtures for backend tests with isolated database session and client overrides."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.session import get_db
from app.main import app as fastapi_app
from app.models.business import Business


@pytest.fixture(scope="session")
def engine():
    """Create a persistent shared in-memory SQLite engine for the test session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(engine) -> Session:
    """Create an isolated test session with a seeded Business tenant."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    # Ensure a default business exists for tenant foreign keys
    biz = session.query(Business).first()
    if not biz:
        biz = Business(name="Test Retail Store", owner_name="Store Owner", business_type="Retail")
        session.add(biz)
        session.commit()
        session.refresh(biz)

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def default_business(db_session: Session) -> Business:
    """Fixture returning the active default business tenant."""
    return db_session.query(Business).first()


@pytest.fixture
def client(engine) -> TestClient:
    """Synchronous test client with FastAPI get_db dependency overridden to SQLite engine."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Ensure default business exists
    setup_session = SessionLocal()
    biz = setup_session.query(Business).first()
    if not biz:
        biz = Business(name="Test Retail Store", owner_name="Store Owner", business_type="Retail")
        setup_session.add(biz)
        setup_session.commit()
    setup_session.close()

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
