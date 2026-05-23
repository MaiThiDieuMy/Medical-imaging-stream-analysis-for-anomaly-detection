from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.ai_models import get_active_model
from app.crud.dataset_manifests import (
    create_dataset_manifest,
    get_dataset_manifest,
    get_latest_dataset_manifest,
    list_dataset_manifests,
)
from app.crud.retraining_jobs import (
    create_retraining_job as crud_create_retraining_job,
    get_active_retraining_job,
    get_active_retraining_job_for_manifest,
    get_latest_retraining_job,
    get_retraining_job,
    list_retraining_jobs,
)
from app.crud.reviews import count_reviews_by_status, list_training_ready_reviews
from app.models.case_review import CaseReview
from app.models.dataset_manifest import DatasetManifest
from app.models.enums import ProcessingStatus
from app.models.retraining_job import RetrainingJob
from app.services.reviews import REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED

RETRAINING_STATUS_QUEUED = "queued"
RETRAINING_STATUS_RUNNING = "running"
RETRAINING_STATUS_EVALUATING = "evaluating"
RETRAINING_STATUS_REGISTERING = "registering"
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
        samples = self.get_training_ready_samples()
        training_ready = len(samples)
        new_samples = self.get_new_training_ready_samples()
        new_training_ready = len(new_samples)
        min_samples = settings.retrain_min_confirmed_samples
        running_job = get_active_retraining_job(self.db)
        latest_job = get_latest_retraining_job(self.db)
        latest_manifest = get_latest_dataset_manifest(self.db)
        return {
            "min_confirmed_samples": min_samples,
            "pending_reviews": pending,
            "confirmed_reviews": confirmed,
            "corrected_reviews": corrected,
            "training_ready_cases": training_ready,
            "new_training_ready_cases": new_training_ready,
            "used_training_ready_cases": training_ready - new_training_ready,
            "auto_start_retraining_job": settings.auto_start_retraining_job,
            "label_distribution": self._label_distribution(samples),
            "new_label_distribution": self._label_distribution(new_samples),
            "should_trigger_retraining": (
                new_training_ready >= min_samples and running_job is None
            ),
            "running_job": running_job,
            "latest_job": latest_job,
            "latest_manifest": latest_manifest,
        }

    def dataset_summary(self) -> dict[str, object]:
        samples = self.get_training_ready_samples()
        new_samples = self.get_new_training_ready_samples()
        manifests = list_dataset_manifests(self.db)
        latest_manifest = manifests[0] if manifests else None
        return {
            "training_ready_cases": len(samples),
            "new_training_ready_cases": len(new_samples),
            "used_training_ready_cases": len(samples) - len(new_samples),
            "label_distribution": self._label_distribution(samples),
            "new_label_distribution": self._label_distribution(new_samples),
            "manifest_count": len(manifests),
            "latest_manifest": latest_manifest,
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

    def get_new_training_ready_samples(self) -> list[CaseReview]:
        used_image_keys = self._used_image_keys_from_locked_manifests()
        return [
            review
            for review in self.get_training_ready_samples()
            if self._review_image_key(review) not in used_image_keys
        ]

    def should_trigger_retraining(self) -> bool:
        summary = self.get_retraining_summary()
        return bool(summary["should_trigger_retraining"])

    def auto_start_retraining_if_ready(
        self,
        *,
        triggered_by: uuid.UUID | None,
    ) -> RetrainingJob | None:
        if not settings.auto_start_retraining_job:
            return None
        if not self.should_trigger_retraining():
            return None

        job = self.create_retraining_job(triggered_by=triggered_by)
        from app.tasks.retraining import fine_tune_model

        fine_tune_model.delay(str(job.retraining_job_id))
        return job

    def create_retraining_job(
        self,
        *,
        triggered_by: uuid.UUID | None = None,
        manifest_id: uuid.UUID | None = None,
    ) -> RetrainingJob:
        active_model = get_active_model(self.db)
        if active_model is None:
            raise RetrainingServiceError("No active AI model found", status_code=404)

        existing_job = get_active_retraining_job(self.db)
        if existing_job is not None:
            raise RetrainingServiceError(
                "A retraining job is already queued or running.",
                status_code=409,
            )

        manifest = (
            self.get_manifest(manifest_id)
            if manifest_id is not None
            else self.create_dataset_manifest_snapshot(created_by=triggered_by)
        )
        min_samples = settings.retrain_min_confirmed_samples
        if manifest.samples_count < min_samples:
            raise RetrainingServiceError(
                "Not enough confirmed/corrected cases for retraining.",
                status_code=400,
            )
        new_samples_count = (
            self._new_samples_count_for_manifest(manifest)
            if manifest_id is not None
            else len(self.get_new_training_ready_samples())
        )
        if new_samples_count < min_samples:
            raise RetrainingServiceError(
                "Not enough new confirmed/corrected cases since the last retraining.",
                status_code=400,
            )
        if manifest.is_locked:
            raise RetrainingServiceError(
                "Dataset manifest has already been used for retraining.",
                status_code=409,
            )

        existing_for_manifest = get_active_retraining_job_for_manifest(
            self.db,
            dataset_manifest_id=manifest.manifest_id,
        )
        if existing_for_manifest is not None:
            raise RetrainingServiceError(
                "A retraining job is already active for this dataset manifest.",
                status_code=409,
            )

        job = crud_create_retraining_job(
            self.db,
            status=RETRAINING_STATUS_QUEUED,
            base_model_id=active_model.model_id,
            dataset_manifest_id=manifest.manifest_id,
            manifest_path=manifest.manifest_path,
            training_samples_count=manifest.samples_count,
            min_required_samples=min_samples,
            triggered_by=triggered_by,
        )
        manifest.is_locked = True
        manifest.used_by_retraining_job_id = job.retraining_job_id
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

    def list_manifests(self) -> list[DatasetManifest]:
        return list_dataset_manifests(self.db)

    def get_manifest(self, manifest_id: uuid.UUID) -> DatasetManifest:
        manifest = get_dataset_manifest(self.db, manifest_id=manifest_id)
        if manifest is None:
            raise RetrainingServiceError("DatasetManifest not found", status_code=404)
        return manifest

    def create_dataset_manifest_snapshot(
        self,
        *,
        created_by: uuid.UUID | None = None,
        require_min_samples: bool = True,
    ) -> DatasetManifest:
        reviews = self.get_training_ready_samples()
        samples = [self._manifest_sample(review) for review in reviews]
        if require_min_samples and len(samples) < settings.retrain_min_confirmed_samples:
            raise RetrainingServiceError(
                "Not enough confirmed/corrected cases to create a dataset manifest.",
                status_code=400,
            )
        label_distribution = self._label_distribution_from_samples(samples)

        output_dir = self._manifest_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        version = f"dataset-chest-xray-demo-v{timestamp}-{uuid.uuid4().hex[:8]}"
        stem = f"training_manifest_{timestamp}"
        manifest_path = output_dir / f"{stem}.json"
        base_query_hash = self._base_query_hash(samples)
        payload = {
            "manifest_id": None,
            "manifest_name": "dataset-chest-xray-demo",
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": str(created_by) if created_by is not None else None,
            "samples_count": len(samples),
            "label_distribution": label_distribution,
            "source_review_statuses": [
                REVIEW_STATUS_CONFIRMED,
                REVIEW_STATUS_CORRECTED,
            ],
            "base_query_hash": base_query_hash,
            "selection_strategy": "hybrid_cumulative_training_new_image_trigger",
            "class_order": ["Atelectasis", "Effusion", "Infiltration", "No_Finding"],
            "display_labels": {"No_Finding": "No Finding"},
            "samples": samples,
        }
        manifest = create_dataset_manifest(
            self.db,
            manifest_name="dataset-chest-xray-demo",
            version=version,
            manifest_path=str(manifest_path),
            samples_count=len(samples),
            label_distribution=label_distribution,
            source_review_statuses=[
                REVIEW_STATUS_CONFIRMED,
                REVIEW_STATUS_CORRECTED,
            ],
            base_query_hash=base_query_hash,
            created_by=created_by,
            metadata_json={
                "class_order": payload["class_order"],
                "selection_strategy": payload["selection_strategy"],
                "sample_image_keys": [
                    self._sample_image_key(sample) for sample in samples
                ],
            },
        )
        payload["manifest_id"] = str(manifest.manifest_id)
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return manifest

    def export_manifest_for_job(
        self,
        job: RetrainingJob | None = None,
        *,
        created_by: uuid.UUID | None = None,
    ) -> dict[str, object]:
        manifest = (
            job.dataset_manifest
            if job is not None and job.dataset_manifest is not None
            else self.create_dataset_manifest_snapshot(
                created_by=created_by,
                require_min_samples=job is not None,
            )
        )

        return {
            "manifest_id": manifest.manifest_id,
            "manifest_path": manifest.manifest_path,
            "samples_count": manifest.samples_count,
            "message": (
                "Versioned retraining manifest exported from "
                "confirmed/corrected labels only."
            ),
        }

    def mark_job_running(self, job: RetrainingJob) -> RetrainingJob:
        job.status = RETRAINING_STATUS_RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.error_message = None
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_job_evaluating(self, job: RetrainingJob) -> RetrainingJob:
        job.status = RETRAINING_STATUS_EVALUATING
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_job_registering(self, job: RetrainingJob) -> RetrainingJob:
        job.status = RETRAINING_STATUS_REGISTERING
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
        if review.case.archived_at is not None:
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
        case = review.case
        image = case.image if case is not None else None
        job = case.analysis_job if case is not None else None
        sorted_results = sorted(
            case.analysis_results if case is not None else [],
            key=lambda item: item.label_name,
        )
        source_model = sorted_results[0].model if sorted_results else None
        return {
            "review_id": str(review.review_id),
            "case_id": str(review.case_id),
            "image_id": str(image.image_id) if image is not None else None,
            "review_status": review.status,
            "reviewed_by": (
                str(review.reviewed_by_id) if review.reviewed_by_id is not None else None
            ),
            "reviewed_at": (
                review.reviewed_at.isoformat() if review.reviewed_at is not None else None
            ),
            "image_path": image.image_path if image is not None else None,
            "image_hash": image.image_hash if image is not None else None,
            "analysis_job_id": str(job.job_id) if job is not None else None,
            "source_model_id": (
                str(source_model.model_id) if source_model is not None else None
            ),
            "source_model_version": (
                source_model.version if source_model is not None else None
            ),
            "ai_predictions": [
                {
                    "label_name": result.label_name,
                    "probability": result.probability,
                    "predicted_positive": result.predicted_positive,
                }
                for result in sorted_results
            ],
            "doctor_labels": labels,
            "labels": labels,
            "class_name": "No_Finding" if positive_label == "No Finding" else positive_label,
        }

    @staticmethod
    def _manifest_dir() -> Path:
        configured = Path(settings.retrain_manifest_dir or settings.retraining_manifest_dir)
        if configured.parts[:2] in {
            ("\\", "app"),
            ("/", "app"),
        }:
            app_relative = Path(*configured.parts[2:])
            if not Path(configured.parts[0], configured.parts[1]).exists():
                return app_relative
        return configured

    def _used_image_keys_from_locked_manifests(self) -> set[str]:
        used_image_keys: set[str] = set()
        for manifest in list_dataset_manifests(self.db):
            if not manifest.is_locked:
                continue
            metadata_image_keys = self._metadata_image_keys(manifest)
            if metadata_image_keys:
                used_image_keys.update(metadata_image_keys)
                continue
            manifest_path = Path(manifest.manifest_path)
            if not manifest_path.exists():
                manifest_path = self._manifest_path_for_runtime(manifest.manifest_path)
            if not manifest_path.exists():
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for sample in payload.get("samples", []):
                if not isinstance(sample, dict):
                    continue
                used_image_keys.add(self._sample_image_key(sample))
        return {key for key in used_image_keys if key}

    def _new_samples_count_for_manifest(self, manifest: DatasetManifest) -> int:
        used_image_keys = self._used_image_keys_from_locked_manifests()
        manifest_image_keys = self._manifest_image_keys(manifest)
        if not manifest_image_keys:
            return len(self.get_new_training_ready_samples())
        return sum(1 for key in manifest_image_keys if key not in used_image_keys)

    def _manifest_image_keys(self, manifest: DatasetManifest) -> list[str]:
        metadata_image_keys = self._metadata_image_keys(manifest)
        if metadata_image_keys:
            return metadata_image_keys

        manifest_path = Path(manifest.manifest_path)
        if not manifest_path.exists():
            manifest_path = self._manifest_path_for_runtime(manifest.manifest_path)
        if not manifest_path.exists():
            return []
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [
            self._sample_image_key(sample)
            for sample in payload.get("samples", [])
            if isinstance(sample, dict)
        ]

    @staticmethod
    def _metadata_image_keys(manifest: DatasetManifest) -> list[str]:
        metadata = manifest.metadata_json or {}
        image_keys = metadata.get("sample_image_keys")
        if not isinstance(image_keys, list):
            return []
        return [str(key) for key in image_keys if key]

    @staticmethod
    def _review_image_key(review: CaseReview) -> str:
        case = review.case
        image = case.image if case is not None else None
        if image is None:
            return f"case:{review.case_id}"
        return RetrainingService._sample_image_key(
            {
                "image_id": str(image.image_id),
                "image_hash": image.image_hash,
                "case_id": str(review.case_id),
            }
        )

    @staticmethod
    def _sample_image_key(sample: dict[str, object]) -> str:
        image_id = sample.get("image_id")
        if image_id:
            return f"image_id:{image_id}"
        image_hash = sample.get("image_hash")
        if image_hash:
            return f"image_hash:{image_hash}"
        case_id = sample.get("case_id")
        if case_id:
            return f"case:{case_id}"
        return ""

    @staticmethod
    def _manifest_path_for_runtime(path: str) -> Path:
        configured = Path(path)
        if configured.parts[:2] in {
            ("\\", "app"),
            ("/", "app"),
        }:
            return Path(*configured.parts[2:])
        return configured

    @staticmethod
    def _label_distribution(reviews: list[CaseReview]) -> dict[str, int]:
        samples = [RetrainingService._manifest_sample(review) for review in reviews]
        return RetrainingService._label_distribution_from_samples(samples)

    @staticmethod
    def _label_distribution_from_samples(
        samples: list[dict[str, object]],
    ) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for sample in samples:
            class_name = str(sample.get("class_name") or "")
            if class_name:
                counter[class_name] += 1
        return dict(counter)

    @staticmethod
    def _base_query_hash(samples: list[dict[str, object]]) -> str:
        case_ids = sorted(str(sample["case_id"]) for sample in samples)
        payload = json.dumps(
            {
                "case_ids": case_ids,
                "review_statuses": [
                    REVIEW_STATUS_CONFIRMED,
                    REVIEW_STATUS_CORRECTED,
                ],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
