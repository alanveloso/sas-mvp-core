"""Pydantic schemas for CBSD Registration (batch format)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResponseObject(BaseModel):
    responseCode: int
    responseMessage: str | None = None
    responseData: Any | None = None


class RegistrationRequestItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    userId: str | None = None
    fccId: str | None = None
    cbsdSerialNumber: str | None = None
    cbsdCategory: str | None = None
    callSign: str | None = None
    measCapability: list[Any] | None = None
    airInterface: dict[str, Any] | None = None
    installationParam: dict[str, Any] | None = None
    cpiSignatureData: dict[str, Any] | None = None
    groupingParam: list[Any] | None = None
    cbsdInfo: dict[str, Any] | None = None


class RegistrationBatchRequest(BaseModel):
    registrationRequest: list[dict[str, Any]] = Field(default_factory=list)


class RegistrationResponseItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    response: ResponseObject
    measReportConfig: list[str] | None = None


class RegistrationBatchResponse(BaseModel):
    registrationResponse: list[dict[str, Any]]
