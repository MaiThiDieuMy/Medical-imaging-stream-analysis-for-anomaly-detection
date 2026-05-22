from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.ai_models import get_active_model
from app.crud.retraining_jobs import (
    create_retraining_job as crud_create_retraining_job,
    get_active_retraining_job,
    get_latest_retraining_job,
    get_retraining_job,
    list_retraining_jobs,
)
from app.crud.reviews import count_reviews_by_status, list_training_ready_reviews
from app.models.case_review import CaseReview
from app.models.enums import ProcessingStatus
from app.models.retraining_job import RetrainingJob
from app.services.reviews import REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED

RETRAINING_STATUS_QUEUED = "queued"
RETRAINING_STATUS_RUNNING = "running"
RETRAINING_STATUS_COMPLETED = "completed"
RETRAINING_STATUS_FAILED = "failed"
RETRAINING_STATUS_SKIPPED = "skipped"

MAX_ERROR_MESSAGE_LENGTH = 4000


class RetrainingServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RetrainingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_retraining_summary(self) -> dict[str, object]:
        pending = count_reviews_by_status(self.db, status="pending")
        confirmed = count_reviews_by_status(self.db, status=REVIEW_STATUS_CONFIRMED)
        corrected = count_reviews_by_status(self.db, status=REVIEW_STATUS_CORRECTED)
        training_ready = len(self.get_training_ready_samples())
        min_samples = settings.retrain_min_confirmed_samples
        running_job = get_active_retraining_job(self.db)
        latest_job = get_latest_retraining_job(self.db)
        return {
            "min_confirmed_samples": min_samples,
            "pending_reviews": pending,
            "confirmed_reviews": confirmed,
            "corrected_reviews": corrected,
            "training_ready_cases": training_ready,
            "should_trigger_retraining": (
                training_ready >= min_samples and running_job is None
            ),
            "running_job": running_job,
            "latest_job": latest_job,
        }

    def get_training_ready_samples(self) -> list[CaseReview]:
        reviews = list_training_ready_reviews(self.db)
        ready: list[CaseReview] = []
        seen_cases: set[uuid.UUID] = set()
        for review in reviews:
            if review.case_id in seen_cases:
                continue
            if self._is_training_ready_review(review):
                ready.append(review)
                seen_cases.add(review.case_id)
        return ready

    def should_trigger_retraining(self) -> bool:
        summary = self.get_retraining_summary()
        return bool(summary["should_trigger_retraining"])

    def create_retraining_job(
        self,
        *,
        triggered_by: uuid.UUID | None = None,
    ) -> RetrainingJob:
        samples = self.get_training_ready_samples()
        min_samples = settings.retrain_min_confirmed_samples
        if len(samples) < min_samples:
            raise RetrainingServiceError(
                "Not enough confirmed/corrected cases for retraining.",
                status_code=400,
            )

        existing_job = get_active_retraining_job(self.db)
        if existing_job is not None:
            raise RetrainingServiceError(
                "A retraining job is already queued or running.",
                status_code=409,
            )

        active_model = get_active_model(self.db)
        if active_model is None:
            raise RetrainingServiceError("No active AI model found", status_code=404)

        job = crud_create_retraining_job(
            self.db,
            status=RETRAINING_STATUS_QUEUED,
            base_model_id=active_model.model_id,
            training_samples_count=len(samples),
            min_required_samples=min_samples,
            triggered_by=triggered_by,
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def list_jobs(self) -> list[RetrainingJob]:
        return list_retraining_jobs(self.db)

    def get_job(self, retraining_job_id: uuid.UUID) -> RetrainingJob:
        job = get_retraining_job(self.db, retraining_job_id=retraining_job_id)
        if job is None:
            raise RetrainingServiceError("RetrainingJob not found", status_code=404)
        return job

    def export_manifest_for_job(self, job: RetrainingJob | None = None) -> dict[str, object]:
        reviews = self.get_training_ready_samples()
        samples = [self._manifest_sample(review) for review in reviews]

        output_dir = self._manifest_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = (
            f"training_manifest_{job.retraining_job_id}_{timestamp}"
            if job is not None
            else f"training_manifest_{timestamp}"
        )
        manifest_path = output_dir / f"{stem}.json"
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "retraining_job_id": (
                str(job.retraining_job_id) if job is not None else None
            ),
            "samples_count": len(samples),
            "class_order": ["Atelectasis", "Effusion", "Infiltration", "No_Finding"],
            "display_labels": {"No_Finding": "No Finding"},
            "samples": samples,
        }
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        if job is not None:
            job.manifest_path = str(manifest_path)
            job.training_samples_count = len(samples)
            self.db.commit()
            self.db.refresh(job)

        return {
            "manifest_path": str(manifest_path),
            "samples_count": len(samples),
            "message": "Retraining manifest exported from confirmed/corrected labels only.",
        }

    def mark_job_running(self, job: RetrainingJob) -> RetrainingJob:
        job.status = RETRAINING_STATUS_RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.error_message = None
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_job_completed(
        self,
        job: RetrainingJob,
        *,
        candidate_model_id: uuid.UUID,
        output_model_path: str,
        mlflow_run_id: str | None,
        mlflow_model_uri: str | None,
        metrics: dict[str, float],
        warning: str | None = None,
    ) -> RetrainingJob:
        job.status = RETRAINING_STATUS_COMPLETED
        job.candidate_model_id = candidate_model_id
        job.output_model_path = output_model_path
        job.mlflow_run_id = mlflow_run_id
        job.mlflow_model_uri = mlflow_model_uri
        job.accuracy = metrics.get("accuracy")
        job.precision_score = metrics.get("precision_score")
        job.recall_score = metrics.get("recall_score")
        job.f1_score = metrics.get("f1_score")
        job.error_message = warning
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_job_failed(self, job: RetrainingJob, error: Exception) -> RetrainingJob:
        job.status = RETRAINING_STATUS_FAILED
        job.error_message = str(error)[:MAX_ERROR_MESSAGE_LENGTH]
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    @staticmethod
    def _is_training_ready_review(review: CaseReview) -> bool:
        if review.status not in {REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED}:
            return False
        if not review.confirmed_labels:
            return False
        if review.case is None or review.case.status != ProcessingStatus.COMPLETED:
            return False
        if review.case.image is None:
            return False
        if not review.case.analysis_results:
            return False
        return sum(1 for label in review.confirmed_labels if label.confirmed_positive) == 1

    @staticmethod
    def _manifest_sample(review: CaseReview) -> dict[str, object]:
        labels = {
            label.label_name: label.confirmed_positive
            for label in sorted(review.confirmed_labels, key=lambda item: item.label_name)
        }
        positive_label = next(
            label_name
            for label_name, confirmed_positive in labels.items()
            if confirmed_positive
        )
        return {
            "review_id": str(review.review_id),
            "case_id": str(review.case_id),
            "review_status": review.status,
            "reviewed_by": (
                str(review.reviewed_by_id) if review.reviewed_by_id is not None else None
            ),
            "reviewed_at": (
                review.reviewed_at.isoformat() if review.reviewed_at is not None else None
            ),
            "image_path": (
                review.case.image.image_path
                if review.case is not None and review.case.image is not None
                else None
            ),
            "labels": labels,
            "class_name": "No_Finding" if positive_label == "No Finding" else positive_label,
        }

    @staticmethod
    def _manifest_dir() -> Path:
        return Path(settings.retrain_manifest_dir or settings.retraining_manifest_dir)
