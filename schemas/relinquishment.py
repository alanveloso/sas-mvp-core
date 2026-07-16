"""Pydantic schemas for CBSD Relinquishment (batch format)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.error_handlers import MAXIMUM_BATCH_SIZE


class RelinquishmentRequestItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    grantId: str | None = None


class RelinquishmentBatchRequest(BaseModel):
    relinquishmentRequest: list[dict[str, Any]] = Field(
        ..., max_length=MAXIMUM_BATCH_SIZE
    )


class RelinquishmentResponseItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    grantId: str | None = None
    response: dict[str, Any]


class RelinquishmentBatchResponse(BaseModel):
    relinquishmentResponse: list[dict[str, Any]]
