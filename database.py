"""SQLAlchemy engine and session helpers (PostgreSQL in production, SQLite locally)."""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

_engine_kwargs: dict = {
    "echo": _settings.db_echo,
}
if _settings.is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update(
        {
            "pool_size": _settings.db_pool_size,
            "max_overflow": _settings.db_max_overflow,
            "pool_timeout": _settings.db_pool_timeout,
            "pool_recycle": _settings.db_pool_recycle,
            "pool_pre_ping": _settings.db_pool_pre_ping,
        }
    )

engine = create_engine(_settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_init_lock = threading.Lock()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(*, retries: int = 10, delay_seconds: float = 2.0) -> None:
    """Create tables, retrying briefly while PostgreSQL becomes ready."""
    from models import models  # noqa: F401

    with _init_lock:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                Base.metadata.create_all(bind=engine)
                return
            except OperationalError as exc:
                last_exc = exc
                message = str(exc).lower()
                # Concurrent create_all can race on SQLite ("table already exists").
                if "already exists" in message:
                    return
                logger.warning(
                    "init_db attempt %s/%s failed: %s", attempt, retries, exc
                )
                if attempt < retries:
                    time.sleep(delay_seconds)
        if last_exc is not None:
            raise last_exc


def reset_db() -> None:
    """Drop and recreate all tables (admin/reset)."""
    from models import models  # noqa: F401

    with _init_lock:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
