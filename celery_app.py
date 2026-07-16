"""Celery application wired to RabbitMQ (and optional result backend)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from celery import Celery

from config import get_settings

_settings = get_settings()

celery_app = Celery(
    "sas",
    broker=_settings.broker_url,
    include=["tasks"],
)

_conf: dict = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_acks_late": _settings.celery_task_acks_late,
    "worker_prefetch_multiplier": _settings.celery_worker_prefetch_multiplier,
    "task_default_queue": _settings.celery_task_default_queue,
    "task_track_started": True,
    "broker_connection_retry_on_startup": True,
}

if _settings.result_backend:
    _conf["result_backend"] = _settings.result_backend
else:
    # Status is persisted in the application DB (cpas_running flag).
    _conf["task_ignore_result"] = True

celery_app.conf.update(**_conf)
