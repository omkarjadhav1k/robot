"""Database engine configuration and session management."""

import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger("business_ai_robot.database")
settings = get_settings()

db_url = settings.DATABASE_URL

connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine_kwargs = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
}
if not db_url.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 300,
        "pool_timeout": 10,
    })

engine = create_engine(db_url, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
