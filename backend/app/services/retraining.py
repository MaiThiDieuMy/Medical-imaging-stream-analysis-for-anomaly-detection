from __future__ import annotations

from dataclasses import dataclass
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
    list_completed_retraining_jobs,
    list_retraining_jobs,
)
from app.crud.reviews import count_reviews_by_status, list_training_ready_reviews
from app.ml.evaluation_set import get_evaluation_set_status
from app.ml.finetune_dataset import build_finetune_dataset
from app.ml.retraining_dataset import class_index_for_label, normalize_retraining_label
from app.models.case_review import CaseReview
from app.models.enums import ProcessingStatus
from app.models.retraining_job import RetrainingJob
from app.services.reviews import REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED

RETRAINING_STATUS_QUEUED = "queued"
RETRAINING_STATUS_RUNNING = "running"
RETRAINING_STATUS_COMPLETED = "completed"
RETRAINING_STATUS_FAILED = "failed"
RETRAINING_STATUS_SKIPPED = "skipped"
RETRAINING_TRIGGER_MANUAL = "manual"
RETRAINING_TRIGGER_MANUAL_FORCE = "manual_force"
RETRAINING_TRIGGER_THRESHOLD = "threshold"

MAX_ERROR_MESSAGE_LENGTH = 4000


@dataclass(frozen=True)
class TrainingReadySampleInfo:
    review_id: uuid.UUID
    case_id: uuid.UUID
    image_path: str
    image_hash: str | None
    label_name: str
    label_index: int
    review_status: str
    reviewed_by: uuid.UUID | None
    created_at: datetime
    confirmed_labels: list[dict[str, object]]


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
        latest_completed_at = self._latest_completed_job_cutoff()
        all_training_ready_items = self.get_training_ready_sample_items()
        new_training_ready_items = self.get_training_ready_sample_items(
            reviewed_after=latest_completed_at,
        )
        new_training_ready = len(new_training_ready_items)
        finetune_summary = build_finetune_dataset(all_training_ready_items)
        min_samples = settings.retrain_min_confirmed_samples
        missing_samples = max(min_samples - new_training_ready, 0)
        running_job = get_active_retraining_job(self.db)
        latest_job = get_latest_retraining_job(self.db)
        evaluation_status = get_evaluation_set_status()
        return {
            "min_confirmed_samples": min_samples,
            "pending_reviews": pending,
            "confirmed_reviews": confirmed,
            "corrected_reviews": corrected,
            "training_ready_cases": new_training_ready,
            "training_seed_enabled": settings.retrain_include_training_seed,
            "training_seed_dir": settings.training_seed_dir,
            "training_seed_count": finetune_summary.seed_count,
            "total_finetune_samples": finetune_summary.total_train_count,
            "finetune_per_class_count": finetune_summary.per_class_count,
            "missing_confirmed_samples": missing_samples,
            "should_trigger_retraining": (
                new_training_ready >= min_samples
                and running_job is None
            ),
            "retrain_auto_start": settings.retrain_auto_start,
            "evaluation_set_available": evaluation_status.available,
            "evaluation_set_sample_count": evaluation_status.sample_count,
            "evaluation_set_dir": settings.evaluation_set_dir,
            "evaluation_warning": evaluation_status.warning,
            "running_job": running_job,
            "latest_job": latest_job,
        }

    def get_training_ready_samples(
        self,
        *,
        reviewed_after: datetime | None = None,
    ) -> list[CaseReview]:
        reviews = list_training_ready_reviews(self.db)
        ready: list[CaseReview] = []
        seen_cases: set[uuid.UUID] = set()
        for review in reviews:
            if review.case_id in seen_cases:
                continue
            if self._is_training_ready_review(review):
                if reviewed_after is not None:
                    reviewed_at = review.reviewed_at or review.created_at
                    if reviewed_at <= reviewed_after:
                        continue
                ready.append(review)
                seen_cases.add(review.case_id)
        return ready

    def get_training_ready_sample_items(
        self,
        *,
        reviewed_after: datetime | None = None,
    ) -> list[TrainingReadySampleInfo]:
        items: list[TrainingReadySampleInfo] = []
        for review in self.get_training_ready_samples(reviewed_after=reviewed_after):
            item = self._training_ready_sample_item(review)
            if item is not None:
                items.append(item)
        return items

    def should_trigger_retraining(self) -> bool:
        summary = self.get_retraining_summary()
        return bool(summary["should_trigger_retraining"])

    def create_retraining_job(
        self,
        *,
        force: bool = False,
        min_samples: int | None = None,
        triggered_by: uuid.UUID | None = None,
        trigger_type: str | None = None,
    ) -> RetrainingJob:
        latest_completed_at = None if force else self._latest_completed_job_cutoff()
        samples = self.get_training_ready_sample_items(
            reviewed_after=latest_completed_at,
        )
        finetune_summary = build_finetune_dataset(samples)
        required_samples = min_samples or settings.retrain_min_confirmed_samples
        if not samples and finetune_summary.total_train_count <= 0:
            raise RetrainingServiceError(
                "No confirmed/corrected cases are available for retraining.",
                status_code=400,
            )
        if len(samples) < required_samples and not force:
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
            trigger_type=(
                RETRAINING_TRIGGER_MANUAL_FORCE
                if force
                else trigger_type or RETRAINING_TRIGGER_MANUAL
            ),
            base_model_id=active_model.model_id,
            training_samples_count=len(samples),
            min_required_samples=required_samples,
            triggered_by=triggered_by,
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def maybe_auto_start_retraining(
        self,
        *,
        triggered_by: uuid.UUID | None = None,
    ) -> RetrainingJob | None:
        if not settings.retrain_auto_start:
            return None

        latest_completed_at = self._latest_completed_job_cutoff()
        samples = self.get_training_ready_sample_items(
            reviewed_after=latest_completed_at,
        )
        required_samples = settings.retrain_min_confirmed_samples
        if len(samples) < required_samples:
            return None

        if get_active_retraining_job(self.db) is not None:
            return None

        job = self.create_retraining_job(
            min_samples=required_samples,
            triggered_by=triggered_by,
            trigger_type=RETRAINING_TRIGGER_THRESHOLD,
        )
        from app.tasks.retraining import fine_tune_model

        fine_tune_model.delay(str(job.retraining_job_id))
        return job

    def list_jobs(self) -> list[RetrainingJob]:
        return list_retraining_jobs(self.db)

    def get_job(self, retraining_job_id: uuid.UUID) -> RetrainingJob:
        job = get_retraining_job(self.db, retraining_job_id=retraining_job_id)
        if job is None:
            raise RetrainingServiceError("RetrainingJob not found", status_code=404)
        return job

    def export_manifest_for_job(self, job: RetrainingJob | None = None) -> dict[str, object]:
        sample_items = self.get_training_ready_sample_items()
        finetune_summary = build_finetune_dataset(sample_items)
        samples = [sample.to_manifest() for sample in finetune_summary.samples]

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
            "seed_count": finetune_summary.seed_count,
            "confirmed_count": finetune_summary.confirmed_count,
            "total_train_count": finetune_summary.total_train_count,
            "per_class_count": finetune_summary.per_class_count,
            "class_order": ["Atelectasis", "Effusion", "Infiltration", "No_Finding"],
            "display_labels": {"No_Finding": "No Finding"},
            "samples": samples,
        }
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        if job is not None:
            job.manifest_path = str(manifest_path)
            job.training_samples_count = finetune_summary.confirmed_count
            self.db.commit()
            self.db.refresh(job)

        return {
            "manifest_path": str(manifest_path),
            "samples_count": len(samples),
            "seed_count": finetune_summary.seed_count,
            "confirmed_count": finetune_summary.confirmed_count,
            "total_train_count": finetune_summary.total_train_count,
            "per_class_count": finetune_summary.per_class_count,
            "message": (
                "Retraining manifest exported from local training seed and "
                "doctor/admin confirmed or corrected labels."
            ),
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
        if review.case.image is None or not review.case.image.image_path:
            return False
        if not review.case.analysis_results:
            return False
        if sum(1 for label in review.confirmed_labels if label.confirmed_positive) != 1:
            return False
        try:
            RetrainingService._positive_label_info(review)
        except ValueError:
            return False
        return True

    @staticmethod
    def _training_ready_sample_item(
        review: CaseReview,
    ) -> TrainingReadySampleInfo | None:
        if not RetrainingService._is_training_ready_review(review):
            return None
        if review.case is None or review.case.image is None:
            return None
        label_name, label_index = RetrainingService._positive_label_info(review)
        return TrainingReadySampleInfo(
            review_id=review.review_id,
            case_id=review.case_id,
            image_path=review.case.image.image_path,
            image_hash=review.case.image.image_hash,
            label_name=label_name,
            label_index=label_index,
            review_status=review.status,
            reviewed_by=review.reviewed_by_id,
            created_at=review.created_at,
            confirmed_labels=[
                {
                    "label_name": label.label_name,
                    "confirmed_positive": label.confirmed_positive,
                }
                for label in sorted(
                    review.confirmed_labels,
                    key=lambda item: item.label_name,
                )
            ],
        )

    @staticmethod
    def _positive_label_info(review: CaseReview) -> tuple[str, int]:
        positive_labels = [
            label.label_name
            for label in review.confirmed_labels
            if label.confirmed_positive
        ]
        if len(positive_labels) != 1:
            raise ValueError("Each training sample must have exactly one positive label")
        normalized = normalize_retraining_label(positive_labels[0])
        display_label = "No Finding" if normalized == "No_Finding" else normalized
        return display_label, class_index_for_label(normalized)

    @staticmethod
    def _manifest_sample(sample: TrainingReadySampleInfo) -> dict[str, object]:
        labels = {
            str(label["label_name"]): bool(label["confirmed_positive"])
            for label in sample.confirmed_labels
        }
        class_name = (
            "No_Finding" if sample.label_name == "No Finding" else sample.label_name
        )
        return {
            "review_id": str(sample.review_id),
            "case_id": str(sample.case_id),
            "review_status": sample.review_status,
            "reviewed_by": str(sample.reviewed_by) if sample.reviewed_by else None,
            "created_at": sample.created_at.isoformat(),
            "image_path": sample.image_path,
            "labels": labels,
            "label_name": sample.label_name,
            "label_index": sample.label_index,
            "class_name": class_name,
        }

    @staticmethod
    def _manifest_dir() -> Path:
        return Path(settings.retrain_manifest_dir or settings.retraining_manifest_dir)

    @staticmethod
    def _job_already_covers_sample_count(
        job: RetrainingJob | None,
        *,
        sample_count: int,
    ) -> bool:
        return (
            job is not None
            and job.status
            in {
                RETRAINING_STATUS_QUEUED,
                RETRAINING_STATUS_RUNNING,
                RETRAINING_STATUS_COMPLETED,
            }
            and job.training_samples_count >= sample_count
        )

    def _latest_completed_job_cutoff(
        self,
        *,
        before_job: RetrainingJob | None = None,
    ) -> datetime | None:
        for job in list_completed_retraining_jobs(self.db):
            completed_at = job.finished_at or job.created_at
            if before_job is not None and completed_at >= before_job.created_at:
                continue
            return completed_at
        return None
