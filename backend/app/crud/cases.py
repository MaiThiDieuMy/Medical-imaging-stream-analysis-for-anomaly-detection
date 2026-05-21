from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.case_review import CaseReview
from app.models.patient import Patient
from app.models.xray_case import XRayCase


def _case_options():
    return (
        selectinload(XRayCase.patient),
        selectinload(XRayCase.image),
        selectinload(XRayCase.analysis_job).selectinload(AnalysisJob.model),
        selectinload(XRayCase.analysis_results).selectinload(AnalysisResult.model),
        selectinload(XRayCase.review).selectinload(CaseReview.confirmed_labels),
    )


def list_cases(
    db: Session,
    *,
    uploaded_by_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[XRayCase]:
    statement = (
        select(XRayCase)
        .join(Patient)
        .order_by(XRayCase.created_at.desc())
        .options(*_case_options())
    )
    if not include_archived:
        statement = statement.where(XRayCase.archived_at.is_(None))
    if uploaded_by_id is not None:
        statement = statement.where(XRayCase.uploaded_by_id == uploaded_by_id)
    return list(db.execute(statement).unique().scalars())


def get_case(db: Session, *, case_id: uuid.UUID) -> XRayCase | None:
    return db.execute(
        select(XRayCase)
        .where(XRayCase.case_id == case_id)
        .options(*_case_options())
    ).unique().scalar_one_or_none()
