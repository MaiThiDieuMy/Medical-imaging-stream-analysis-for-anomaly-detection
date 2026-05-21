from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PatientAnalyzeRequest(BaseModel):
    patient_code: str = Field(min_length=1, max_length=20)
    full_name: str = Field(min_length=1, max_length=100)
    gender: str = Field(min_length=1, max_length=10)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    department: str | None = Field(default=None, max_length=100)
    note: str | None = None


class AnalysisResultItem(BaseModel):
    label_name: str
    probability: float
    predicted_positive: bool

    model_config = ConfigDict(from_attributes=True)


class AnalyzeResponse(BaseModel):
    status: str
    cache_hit: bool
    case_id: UUID | None
    job_id: UUID | None
    model_id: UUID
    model_version: str
    results: list[AnalysisResultItem] = Field(default_factory=list)


class CaseStatusResponse(BaseModel):
    case_id: UUID
    status: str
    patient_id: UUID
    job_id: UUID | None = None
    job_status: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class JobStatusResponse(BaseModel):
    job_id: UUID
    case_id: UUID
    model_id: UUID
    model_version: str
    status: str
    worker_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CaseResultsResponse(BaseModel):
    case_id: UUID
    status: str
    model_id: UUID | None = None
    model_version: str | None = None
    results: list[AnalysisResultItem] = Field(default_factory=list)
