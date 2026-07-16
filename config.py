"""Centralized application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent
_DEFAULT_CERTS = _ROOT / "certs"


class Settings(BaseSettings):
    """Single source of truth for connections, mTLS paths and runtime knobs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Persistence
    database_url: str = Field(
        default=f"sqlite:///{_ROOT / 'sas_mvp.db'}",
        description="SQLAlchemy database URL (PostgreSQL in production).",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    # Message broker / Celery
    rabbitmq_url: str = "amqp://sas:sas@localhost:5672//"
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    celery_task_acks_late: bool = True
    celery_worker_prefetch_multiplier: int = 1
    celery_task_default_queue: str = "sas"

    # Spectrum / runtime profile
    sas_profile: str = "cbrs_winnforum"
    sas_admin_id: str = "sas_admin_id"
    fad_public_base: str = "https://localhost:9000"
    sas_sas_version: str = "v1.3"
    http_timeout_seconds: float = 30.0
    max_batch_size: int = 100

    # API listeners
    api_host: str = "0.0.0.0"
    rsa_port: int = 9000
    ecc_port: int = 9001

    # mTLS / certificates
    certs_dir: Path = _DEFAULT_CERTS
    ssl_certfile: Optional[Path] = None
    ssl_keyfile: Optional[Path] = None
    ssl_ecc_certfile: Optional[Path] = None
    ssl_ecc_keyfile: Optional[Path] = None
    ssl_ca_certs: Optional[Path] = None
    ssl_crl_dir: Optional[Path] = None
    client_certfile: Optional[Path] = None
    client_keyfile: Optional[Path] = None

    # External federal / marketplace DB basic auth
    db_sync_username: str = "username"
    db_sync_password: str = "password"

    @field_validator(
        "certs_dir",
        "ssl_certfile",
        "ssl_keyfile",
        "ssl_ecc_certfile",
        "ssl_ecc_keyfile",
        "ssl_ca_certs",
        "ssl_crl_dir",
        "client_certfile",
        "client_keyfile",
        mode="before",
    )
    @classmethod
    def _coerce_path(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, Path):
            return value
        return Path(str(value))

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.rabbitmq_url

    @property
    def result_backend(self) -> Optional[str]:
        """Optional Celery result backend; None disables result persistence."""
        return self.celery_result_backend

    @property
    def resolved_ssl_certfile(self) -> Path:
        return self.ssl_certfile or (self.certs_dir / "server.cert")

    @property
    def resolved_ssl_keyfile(self) -> Path:
        return self.ssl_keyfile or (self.certs_dir / "server.key")

    @property
    def resolved_ssl_ecc_certfile(self) -> Path:
        return self.ssl_ecc_certfile or (self.certs_dir / "server-ecc.cert")

    @property
    def resolved_ssl_ecc_keyfile(self) -> Path:
        return self.ssl_ecc_keyfile or (self.certs_dir / "server-ecc.key")

    @property
    def resolved_ssl_ca_certs(self) -> Path:
        return self.ssl_ca_certs or (self.certs_dir / "ca.cert")

    @property
    def resolved_ssl_crl_dir(self) -> Path:
        return self.ssl_crl_dir or (self.certs_dir / "crl")

    @property
    def resolved_client_certfile(self) -> Path:
        return self.client_certfile or self.resolved_ssl_certfile

    @property
    def resolved_client_keyfile(self) -> Path:
        return self.client_keyfile or self.resolved_ssl_keyfile

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def db_sync_basic_auth(self) -> tuple[str, str]:
        return (self.db_sync_username, self.db_sync_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
