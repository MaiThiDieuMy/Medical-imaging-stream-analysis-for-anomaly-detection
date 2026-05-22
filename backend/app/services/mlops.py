from __future__ import annotations

from sqlalchemy.orm import Session

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

    def retraining_check(self) -> dict[str, object]:
        summary = self.retraining_summary()
        should_trigger = bool(summary["should_trigger_retraining"])
        message = (
            "Retraining threshold reached; manual training can be started."
            if should_trigger
            else "Retraining threshold not reached; keep collecting confirmed labels."
        )
        return {**summary, "message": message}

    def export_manifest(self) -> dict[str, object]:
        return self.retraining.export_manifest_for_job()
