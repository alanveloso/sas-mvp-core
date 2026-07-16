"""Pydantic schemas for CBSD Deregistration (batch format)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.error_handlers import MAXIMUM_BATCH_SIZE


class DeregistrationRequestItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None


class DeregistrationBatchRequest(BaseModel):
    deregistrationRequest: list[dict[str, Any]] = Field(
        ..., max_length=MAXIMUM_BATCH_SIZE
    )


class DeregistrationResponseItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    response: dict[str, Any]


class DeregistrationBatchResponse(BaseModel):
    deregistrationResponse: list[dict[str, Any]]
