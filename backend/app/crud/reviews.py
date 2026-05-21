from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis_result import AnalysisResult
from app.models.case_review import CaseReview
from app.models.confirmed_label import ConfirmedLabel
from app.models.xray_case import XRayCase


def get_review(db: Session, *, review_id: uuid.UUID) -> CaseReview | None:
    return db.execute(
        select(CaseReview)
        .where(CaseReview.review_id == review_id)
        .options(
            selectinload(CaseReview.confirmed_labels),
            selectinload(CaseReview.case).selectinload(XRayCase.analysis_results),
        )
    ).scalar_one_or_none()


def get_review_by_case(db: Session, *, case_id: uuid.UUID) -> CaseReview | None:
    return db.execute(
        select(CaseReview).where(CaseReview.case_id == case_id)
    ).scalar_one_or_none()


def list_reviews_by_status(db: Session, *, statuses: set[str]) -> list[CaseReview]:
    return list(
        db.execute(
            select(CaseReview)
            .where(CaseReview.status.in_(statuses))
            .order_by(CaseReview.created_at.desc())
            .options(
                selectinload(CaseReview.confirmed_labels),
                selectinload(CaseReview.case).selectinload(XRayCase.analysis_results),
                selectinload(CaseReview.case).selectinload(XRayCase.image),
            )
        ).scalars()
    )


def create_case_review(
    db: Session,
    *,
    case_id: uuid.UUID,
    status: str,
    reason: str,
) -> CaseReview:
    review = CaseReview(case_id=case_id, status=status, reason=reason)
    db.add(review)
    db.flush()
    return review


def delete_confirmed_labels(db: Session, *, review: CaseReview) -> None:
    for label in list(review.confirmed_labels):
        db.delete(label)
    db.flush()


def create_confirmed_labels(
    db: Session,
    *,
    review: CaseReview,
    labels: dict[str, bool],
) -> list[ConfirmedLabel]:
    created: list[ConfirmedLabel] = []
    for label_name, confirmed_positive in labels.items():
        label = ConfirmedLabel(
            review_id=review.review_id,
            case_id=review.case_id,
            label_name=label_name,
            confirmed_positive=confirmed_positive,
        )
        db.add(label)
        created.append(label)
    db.flush()
    return created


def list_training_ready_reviews(db: Session) -> list[CaseReview]:
    return list_reviews_by_status(db, statuses={"confirmed", "corrected"})


def count_reviews_by_status(db: Session, *, status: str) -> int:
    return (
        db.scalar(
            select(func.count(CaseReview.review_id)).where(CaseReview.status == status)
        )
        or 0
    )


def list_case_results(
    db: Session,
    *,
    case_id: uuid.UUID,
) -> list[AnalysisResult]:
    return list(
        db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.case_id == case_id)
            .order_by(AnalysisResult.label_name)
        ).scalars()
    )
