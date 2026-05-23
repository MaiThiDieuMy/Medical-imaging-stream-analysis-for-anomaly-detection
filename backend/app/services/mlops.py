from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.dataset_manifest import DatasetManifest
from app.models.case_review import CaseReview
from app.services.retraining import RetrainingService


class MLOpsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.retraining = RetrainingService(db)

    def retraining_summary(self) -> dict[str, object]:
        return self.retraining.get_retraining_summary()

    def training_ready_samples(self) -> list[CaseReview]:
        return self.retraining.get_training_ready_samples()

    def dataset_summary(self) -> dict[str, object]:
        return self.retraining.dataset_summary()

    def dataset_manifests(self) -> list[DatasetManifest]:
        return self.retraining.list_manifests()

    def get_dataset_manifest(self, manifest_id) -> DatasetManifest:
        return self.retraining.get_manifest(manifest_id)

    def create_dataset_manifest(self, *, created_by) -> DatasetManifest:
        return self.retraining.create_dataset_manifest_snapshot(created_by=created_by)

    def retraining_check(self) -> dict[str, object]:
        summary = self.retraining_summary()
        should_trigger = bool(summary["should_trigger_retraining"])
        message = (
            "Retraining threshold reached; manual training can be started."
            if should_trigger
            else "Retraining threshold not reached; keep collecting confirmed labels."
        )
        return {**summary, "message": message}

    def export_manifest(self, *, created_by=None) -> dict[str, object]:
        return self.retraining.export_manifest_for_job(created_by=created_by)
