from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.monitoring import MonitoringSummaryResponse
from app.services.monitoring import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
metrics_router = APIRouter(tags=["monitoring"])


@router.get("/summary", response_model=MonitoringSummaryResponse)
def get_monitoring_summary(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> MonitoringSummaryResponse:
    return MonitoringSummaryResponse(**MonitoringService(db).summary())


@metrics_router.get("/metrics")
def get_prometheus_metrics(db: Session = Depends(get_db)) -> Response:
    return Response(
        content=MonitoringService(db).prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
