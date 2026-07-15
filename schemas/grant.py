"""Pydantic schemas for CBSD Grant (batch format)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FrequencyRange(BaseModel):
    model_config = ConfigDict(extra="allow")

    lowFrequency: int | None = None
    highFrequency: int | None = None


class OperationParam(BaseModel):
    model_config = ConfigDict(extra="allow")

    maxEirp: float | None = None
    operationFrequencyRange: FrequencyRange | dict[str, Any] | None = None


class GrantRequestItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    operationParam: OperationParam | dict[str, Any] | None = None
    measuringCapabilities: Any | None = None


class GrantBatchRequest(BaseModel):
    grantRequest: list[dict[str, Any]] = Field(default_factory=list)


class GrantResponseItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    grantId: str | None = None
    grantExpireTime: str | None = None
    heartbeatInterval: int | None = None
    channelType: Literal["PAL", "GAA"] | None = None
    response: dict[str, Any]


class GrantBatchResponse(BaseModel):
    grantResponse: list[dict[str, Any]]
