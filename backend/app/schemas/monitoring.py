from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MonitoringActiveModel(BaseModel):
    model_id: UUID
    model_name: str
    version: str
    accuracy: float | None = None
    f1_score: float | None = None
    precision_score: float | None = None
    recall_score: float | None = None
    created_at: datetime


class MonitoringSummaryResponse(BaseModel):
    backend_status: str
    database_reachable: bool
    redis_broker_status: str
    active_model: MonitoringActiveModel | None = None
    total_cases: int
    total_jobs_by_status: dict[str, int]
    reviews_by_status: dict[str, int]
    pending_reviews: int
    training_ready_cases: int
    metrics: dict[str, int]
