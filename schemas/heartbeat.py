"""Pydantic schemas for CBSD Heartbeat (batch format)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from services.error_handlers import MAXIMUM_BATCH_SIZE


class HeartbeatRequestItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    grantId: str | None = None
    operationState: Literal["GRANTED", "AUTHORIZED"] | str | None = None
    grantRenew: bool | None = None
    measReport: dict[str, Any] | None = None


class HeartbeatBatchRequest(BaseModel):
    heartbeatRequest: list[dict[str, Any]] = Field(
        ..., max_length=MAXIMUM_BATCH_SIZE
    )


class HeartbeatResponseItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    grantId: str | None = None
    transmitExpireTime: str
    grantExpireTime: str | None = None
    heartbeatInterval: int | None = None
    measReportConfig: list[str] | None = None
    response: dict[str, Any]


class HeartbeatBatchResponse(BaseModel):
    heartbeatResponse: list[dict[str, Any]]
