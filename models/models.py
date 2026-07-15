"""SQLAlchemy models for the SAS MVP."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class FccIdRecord(Base):
    __tablename__ = "fcc_ids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fcc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    fcc_max_eirp: Mapped[float] = mapped_column(Float, default=47.0)


class UserIdRecord(Base):
    __tablename__ = "user_ids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)


class BlacklistedFccId(Base):
    __tablename__ = "blacklisted_fcc_ids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fcc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class ConditionalRegistration(Base):
    __tablename__ = "conditional_registrations"
    __table_args__ = (
        UniqueConstraint("fcc_id", "cbsd_serial_number", name="uq_cond_fcc_serial"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fcc_id: Mapped[str] = mapped_column(String(64), index=True)
    cbsd_serial_number: Mapped[str] = mapped_column(String(128), index=True)
    data_json: Mapped[str] = mapped_column(Text)


class CpiUser(Base):
    __tablename__ = "cpi_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cpi_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    cpi_name: Mapped[str] = mapped_column(String(256), default="")
    cpi_public_key: Mapped[str] = mapped_column(Text, default="")


class Cbsd(Base):
    __tablename__ = "cbsds"
    __table_args__ = (
        UniqueConstraint("fcc_id", "cbsd_serial_number", name="uq_cbsd_fcc_serial"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cbsd_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    fcc_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(256))
    cbsd_serial_number: Mapped[str] = mapped_column(String(128))
    cbsd_category: Mapped[str | None] = mapped_column(String(8), nullable=True)
    registration_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Grant(Base):
    __tablename__ = "grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grant_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    cbsd_id: Mapped[str] = mapped_column(String(256), index=True)
    channel_type: Mapped[str] = mapped_column(String(16), default="GAA")
    grant_expire_time: Mapped[datetime] = mapped_column(DateTime)
    heartbeat_interval: Mapped[int] = mapped_column(Integer, default=60)
    transmit_expire_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terminated: Mapped[bool] = mapped_column(Boolean, default=False)
    grant_json: Mapped[str] = mapped_column(Text, default="{}")
