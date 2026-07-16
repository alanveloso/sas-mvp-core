"""SQLite database setup for the SAS MVP."""

from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = Path(__file__).resolve().parent / "sas_mvp.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_init_lock = threading.Lock()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from models import models  # noqa: F401

    # RSA + ECDSA uvicorn processes share this module; serialize schema creation.
    with _init_lock:
        try:
            Base.metadata.create_all(bind=engine)
        except OperationalError as exc:
            # Concurrent create_all can race on SQLite ("table already exists").
            if "already exists" not in str(exc).lower():
                raise


def reset_db() -> None:
    """Drop and recreate all tables (admin/reset)."""
    from models import models  # noqa: F401

    with _init_lock:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
