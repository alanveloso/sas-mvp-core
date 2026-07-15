"""Pydantic schemas for CBSD Spectrum Inquiry (batch format)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FrequencyRange(BaseModel):
    model_config = ConfigDict(extra="allow")

    lowFrequency: int | None = None
    highFrequency: int | None = None


class SpectrumInquiryRequestItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    inquiredSpectrum: list[dict[str, Any]] | None = None
    measReport: dict[str, Any] | None = None


class SpectrumInquiryBatchRequest(BaseModel):
    spectrumInquiryRequest: list[dict[str, Any]] = Field(default_factory=list)


class AvailableChannel(BaseModel):
    model_config = ConfigDict(extra="allow")

    frequencyRange: FrequencyRange
    channelType: Literal["PAL", "GAA"]
    ruleApplied: str = "FCC_PART_96"


class SpectrumInquiryResponseItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    cbsdId: str | None = None
    availableChannel: list[AvailableChannel] | None = None
    response: dict[str, Any]


class SpectrumInquiryBatchResponse(BaseModel):
    spectrumInquiryResponse: list[dict[str, Any]]
