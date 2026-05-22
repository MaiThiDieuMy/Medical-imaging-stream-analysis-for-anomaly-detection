from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.cases import get_case
from app.crud.reviews import (
    create_case_review,
    create_confirmed_labels,
    delete_confirmed_labels,
    get_review,
    get_review_by_case,
    list_case_results,
    list_reviews_by_status,
    list_training_ready_reviews,
)
from app.ml.labels import DEMO_LABELS
from app.ml.types import InferenceOutput
from app.models.case_review import CaseReview
from app.models.confirmed_label import ConfirmedLabel
from app.models.enums import ProcessingStatus

REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_CONFIRMED = "confirmed"
REVIEW_STATUS_CORRECTED = "corrected"
REVIEW_STATUS_REJECTED = "rejected"
TRAINING_READY_STATUSES = {REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED}
logger = logging.getLogger(__name__)


class ReviewServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def low_confidence_reason(
    outputs: list[InferenceOutput],
    *,
    low_confidence_threshold: float | None = None,
    decision_threshold: float | None = None,
    near_threshold_margin: float | None = None,
) -> str | None:
    if not outputs:
        return None

    confidence_threshold = (
        settings.low_confidence_threshold
        if low_confidence_threshold is None
        else low_confidence_threshold
    )
    positive_threshold = (
        settings.model_threshold if decision_threshold is None else decision_threshold
    )
    margin = (
        settings.review_near_threshold_margin
        if near_threshold_margin is None
        else near_threshold_margin
    )

    max_probability = max(output.probability for output in outputs)
    reasons: list[str] = []
    if max_probability < confidence_threshold:
        reasons.append(
            "max_probability "
            f"{max_probability:.4f} < low_confidence_threshold "
            f"{confidence_threshold:.4f}"
        )

    near_labels = [
        output.label_name
        for output in outputs
        if abs(output.probability - positive_threshold) <= margin
    ]
    if near_labels:
        reasons.append(
            "probabilities near decision threshold "
            f"{positive_threshold:.4f}: {', '.join(near_labels)}"
        )

    return "; ".join(reasons) if reasons else None


def ensure_pending_review_for_outputs(
    db: Session,
    *,
    case_id: uuid.UUID,
    outputs: list[InferenceOutput],
) -> CaseReview | None:
    reason = low_confidence_reason(outputs)
    if reason is None:
        return None

    existing_review = get_review_by_case(db, case_id=case_id)
    if existing_review is not None:
        return existing_review

    return create_case_review(
        db,
        case_id=case_id,
        status=REVIEW_STATUS_PENDING,
        reason=reason,
    )


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_pending_reviews(self) -> list[CaseReview]:
        return list_reviews_by_status(self.db, statuses={REVIEW_STATUS_PENDING})

    def get_review(self, review_id: uuid.UUID) -> CaseReview:
        review = get_review(self.db, review_id=review_id)
        if review is None:
            raise ReviewServiceError("CaseReview not found", status_code=404)
        return review

    def confirm_review(
        self,
        review_id: uuid.UUID,
        *,
        note: str | None = None,
        reviewed_by: uuid.UUID | None = None,
    ) -> CaseReview:
        review = self._get_pending_review(review_id)
        results = list_case_results(self.db, case_id=review.case_id)
        labels = {result.label_name: result.predicted_positive for result in results}
        self._validate_complete_label_set(labels)
        self._validate_single_positive_label(labels)
        return self._complete_review(
            review,
            labels=labels,
            status=REVIEW_STATUS_CONFIRMED,
            note=note,
            reviewed_by=reviewed_by,
        )

    def correct_review(
        self,
        review_id: uuid.UUID,
        *,
        labels: dict[str, bool],
        note: str | None = None,
        reviewed_by: uuid.UUID | None = None,
    ) -> CaseReview:
        review = self._get_pending_review(review_id)
        self._validate_complete_label_set(labels)
        self._validate_single_positive_label(labels)
        return self._complete_review(
            review,
            labels=labels,
            status=REVIEW_STATUS_CORRECTED,
            note=note,
            reviewed_by=reviewed_by,
        )

    def list_training_ready(self) -> list[CaseReview]:
        ready: list[CaseReview] = []
        for review in list_training_ready_reviews(self.db):
            if review.case is None or review.case.status != ProcessingStatus.COMPLETED:
                continue
            if review.case.image is None or not review.case.analysis_results:
                continue
            if not review.confirmed_labels:
                continue
            if (
                sum(
                    1
                    for label in review.confirmed_labels
                    if label.confirmed_positive
                )
                != 1
            ):
                continue
            ready.append(review)
        return ready

    def get_review_status_for_case(self, case_id: uuid.UUID) -> CaseReview | None:
        return get_review_by_case(self.db, case_id=case_id)

    def confirm_case_result(
        self,
        case_id: uuid.UUID,
        *,
        note: str | None = None,
        reviewed_by: uuid.UUID | None = None,
    ) -> CaseReview:
        review = self._get_or_create_review_for_completed_case(
            case_id,
            reason="Doctor/admin manual confirmation for completed case.",
        )
        self._ensure_review_can_receive_confirmed_labels(review)
        results = list_case_results(self.db, case_id=review.case_id)
        labels = {result.label_name: result.predicted_positive for result in results}
        self._validate_complete_label_set(labels)
        self._validate_single_positive_label(labels)
        return self._complete_review(
            review,
            labels=labels,
            status=REVIEW_STATUS_CONFIRMED,
            note=note,
            reviewed_by=reviewed_by,
        )

    def correct_case_labels(
        self,
        case_id: uuid.UUID,
        *,
        labels: dict[str, bool],
        note: str | None = None,
        reviewed_by: uuid.UUID | None = None,
    ) -> CaseReview:
        review = self._get_or_create_review_for_completed_case(
            case_id,
            reason="Doctor/admin manual label correction for completed case.",
        )
        self._ensure_review_can_receive_confirmed_labels(review)
        self._validate_complete_label_set(labels)
        self._validate_single_positive_label(labels)
        return self._complete_review(
            review,
            labels=labels,
            status=REVIEW_STATUS_CORRECTED,
            note=note,
            reviewed_by=reviewed_by,
        )

    def _get_pending_review(self, review_id: uuid.UUID) -> CaseReview:
        review = self.get_review(review_id)
        if review.status != REVIEW_STATUS_PENDING:
            raise ReviewServiceError(
                "Review must be pending before confirmation or correction",
                status_code=409,
            )
        if review.confirmed_labels:
            raise ReviewServiceError(
                "Review already has confirmed labels",
                status_code=409,
            )
        return review

    def _get_or_create_review_for_completed_case(
        self,
        case_id: uuid.UUID,
        *,
        reason: str,
    ) -> CaseReview:
        case = get_case(self.db, case_id=case_id)
        if case is None:
            raise ReviewServiceError("XRayCase not found", status_code=404)
        if case.status != ProcessingStatus.COMPLETED:
            raise ReviewServiceError(
                "Only completed cases can be confirmed or corrected for retraining",
                status_code=409,
            )
        if not case.analysis_results:
            raise ReviewServiceError(
                "Completed case has no analysis results to confirm",
                status_code=409,
            )

        review = get_review_by_case(self.db, case_id=case_id)
        if review is None:
            review = create_case_review(
                self.db,
                case_id=case_id,
                status=REVIEW_STATUS_PENDING,
                reason=reason,
            )
        return review

    @staticmethod
    def _ensure_review_can_receive_confirmed_labels(review: CaseReview) -> None:
        if review.status in TRAINING_READY_STATUSES or review.confirmed_labels:
            raise ReviewServiceError(
                "Case already has confirmed labels. Reopen/edit workflow is not implemented.",
                status_code=409,
            )

    def _complete_review(
        self,
        review: CaseReview,
        *,
        labels: dict[str, bool],
        status: str,
        note: str | None,
        reviewed_by: uuid.UUID | None,
    ) -> CaseReview:
        delete_confirmed_labels(self.db, review=review)
        create_confirmed_labels(self.db, review=review, labels=labels)
        review.status = status
        review.reviewed_at = datetime.now(timezone.utc)
        review.reviewed_by_id = reviewed_by
        review.note = note
        self.db.commit()
        logger.info(
            "Completed case review: review_id=%s case_id=%s status=%s reviewed_by=%s",
            review.review_id,
            review.case_id,
            status,
            reviewed_by,
        )
        return self.get_review(review.review_id)

    @staticmethod
    def _validate_complete_label_set(labels: dict[str, bool]) -> None:
        if set(labels) != set(DEMO_LABELS) or len(labels) != len(DEMO_LABELS):
            raise ReviewServiceError(
                "Labels must include exactly: " + ", ".join(DEMO_LABELS),
                status_code=422,
            )

    @staticmethod
    def _validate_single_positive_label(labels: dict[str, bool]) -> None:
        positive_count = sum(1 for selected in labels.values() if selected)
        if positive_count != 1:
            raise ReviewServiceError(
                "Exactly one label must be selected for multi-class retraining",
                status_code=422,
            )


def confirmed_label_items(review: CaseReview) -> list[ConfirmedLabel]:
    return sorted(review.confirmed_labels, key=lambda item: item.label_name)
