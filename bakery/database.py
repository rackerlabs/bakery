#!/usr/bin/env python3
"""Database session management for Bakery."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Generator, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bakery.config import settings

T = TypeVar("T")

RECORD_CHANGED_MYSQL_ERRNO = 1020

# Create database engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.environment == "development",
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""

    pass


def is_record_changed_error(exc: BaseException) -> bool:
    """Return True when MariaDB reports a concurrent row update (errno 1020)."""
    if not isinstance(exc, OperationalError):
        return False
    orig = getattr(exc, "orig", None)
    if orig is not None:
        args = getattr(orig, "args", ())
        if args and args[0] == RECORD_CHANGED_MYSQL_ERRNO:
            return True
    return "Record has changed since last read" in str(exc)


async def commit_with_record_changed_retry_async(
    db: Session,
    persist_fn: Callable[[], T],
    *,
    max_attempts: int = 5,
    backoff_base_sec: float = 0.05,
) -> T:
    """Retry a commit when a stale ticket row races with another sync request."""
    for attempt in range(max_attempts):
        try:
            return persist_fn()
        except OperationalError as exc:
            if not is_record_changed_error(exc) or attempt >= max_attempts - 1:
                raise
            db.rollback()
            if backoff_base_sec > 0:
                await asyncio.sleep(backoff_base_sec * (2**attempt))
    raise RuntimeError("commit_with_record_changed_retry_async exhausted retries")


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session.

    Yields:
        Session: Database session

    Example:
        @app.get("/endpoint")
        async def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
