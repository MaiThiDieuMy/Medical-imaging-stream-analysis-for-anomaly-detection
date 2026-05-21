from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.reviews import count_reviews_by_status, list_training_ready_reviews
from app.models.case_review import CaseReview
from app.services.reviews import REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED


class MLOpsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def retraining_summary(self) -> dict[str, int | bool]:
        pending = count_reviews_by_status(self.db, status="pending")
        confirmed = count_reviews_by_status(self.db, status=REVIEW_STATUS_CONFIRMED)
        corrected = count_reviews_by_status(self.db, status=REVIEW_STATUS_CORRECTED)
        training_ready = confirmed + corrected
        min_samples = settings.retrain_min_confirmed_samples
        return {
            "min_confirmed_samples": min_samples,
            "pending_reviews": pending,
            "confirmed_reviews": confirmed,
            "corrected_reviews": corrected,
            "training_ready_cases": training_ready,
            "should_trigger_retraining": training_ready >= min_samples,
        }

    def training_ready_samples(self) -> list[CaseReview]:
        return list_training_ready_reviews(self.db)

    def retraining_check(self) -> dict[str, int | bool | str]:
        summary = self.retraining_summary()
        should_trigger = bool(summary["should_trigger_retraining"])
        message = (
            "Retraining threshold reached; manual training can be started."
            if should_trigger
            else "Retraining threshold not reached; keep collecting confirmed labels."
        )
        return {**summary, "message": message}

    def export_manifest(self) -> dict[str, int | str]:
        reviews = self.training_ready_samples()
        samples = []
        for review in reviews:
            if not review.confirmed_labels:
                continue
            labels = {
                label.label_name: label.confirmed_positive
                for label in sorted(review.confirmed_labels, key=lambda item: item.label_name)
            }
            samples.append(
                {
                    "review_id": str(review.review_id),
                    "case_id": str(review.case_id),
                    "review_status": review.status,
                    "image_path": (
                        review.case.image.image_path
                        if review.case is not None and review.case.image is not None
                        else None
                    ),
                    "labels": labels,
                }
            )

        output_dir = Path(settings.retraining_manifest_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        manifest_path = output_dir / f"training_manifest_{timestamp}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "samples_count": len(samples),
                    "samples": samples,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "manifest_path": str(manifest_path),
            "samples_count": len(samples),
            "message": "Retraining manifest exported from confirmed/corrected labels only.",
        }
