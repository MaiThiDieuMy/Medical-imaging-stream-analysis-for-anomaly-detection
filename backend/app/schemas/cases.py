from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import AnalysisResultItem


class PatientSummary(BaseModel):
    patient_id: UUID
    patient_code: str
    full_name: str
    gender: str
    birth_year: int | None = None
    department: str | None = None

    model_config = ConfigDict(from_attributes=True)


class XRayImageSummary(BaseModel):
    image_id: UUID
    file_name: str
    image_path: str
    image_hash: str
    file_format: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisJobSummary(BaseModel):
    job_id: UUID
    status: str
    model_id: UUID
    model_version: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CaseListItem(BaseModel):
    case_id: UUID
    status: str
    patient_code: str
    patient_name: str
    uploaded_by: UUID | None = None
    model_version: str | None = None
    review_status: str | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class CaseDetailResponse(BaseModel):
    case_id: UUID
    status: str
    note: str | None = None
    uploaded_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    patient: PatientSummary
    image: XRayImageSummary | None = None
    job: AnalysisJobSummary | None = None
    model_version: str | None = None
    review_status: str | None = None
    review_note: str | None = None
    results: list[AnalysisResultItem] = Field(default_factory=list)
