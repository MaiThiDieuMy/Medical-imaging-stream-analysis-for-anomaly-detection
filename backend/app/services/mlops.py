from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.retraining import RetrainingService, TrainingReadySampleInfo


class MLOpsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.retraining = RetrainingService(db)

    def retraining_summary(self) -> dict[str, object]:
        return self.retraining.get_retraining_summary()

    def training_ready_samples(self) -> list[TrainingReadySampleInfo]:
        return self.retraining.get_training_ready_sample_items()

    def retraining_check(self) -> dict[str, object]:
        summary = self.retraining_summary()
        should_trigger = bool(summary["should_trigger_retraining"])
        missing = int(summary.get("missing_confirmed_samples", 0))
        if should_trigger:
            message = "Đã đủ ngưỡng retraining; có thể bắt đầu fine-tune."
        elif missing > 0:
            message = (
                "Chưa đủ ngưỡng retraining; "
                f"cần thêm {missing} ca đã xác nhận/gán nhãn lại."
            )
        else:
            message = (
                "Đã đủ ngưỡng retraining, nhưng đã có job bao phủ batch "
                "training-ready hiện tại."
            )
        return {**summary, "message": message}

    def export_manifest(self) -> dict[str, object]:
        return self.retraining.export_manifest_for_job()
