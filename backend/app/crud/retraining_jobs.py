from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.retraining_job import RetrainingJob


def create_retraining_job(
    db: Session,
    *,
    status: str,
    trigger_type: str,
    base_model_id: uuid.UUID,
    training_samples_count: int,
    min_required_samples: int,
    triggered_by: uuid.UUID | None,
) -> RetrainingJob:
    job = RetrainingJob(
        status=status,
        trigger_type=trigger_type,
        base_model_id=base_model_id,
        training_samples_count=training_samples_count,
        min_required_samples=min_required_samples,
        triggered_by_id=triggered_by,
    )
    db.add(job)
    db.flush()
    return job


def get_retraining_job(
    db: Session,
    *,
    retraining_job_id: uuid.UUID,
) -> RetrainingJob | None:
    return db.execute(
        select(RetrainingJob).where(
            RetrainingJob.retraining_job_id == retraining_job_id,
        )
    ).scalar_one_or_none()


def list_retraining_jobs(db: Session) -> list[RetrainingJob]:
    return list(
        db.execute(
            select(RetrainingJob).order_by(RetrainingJob.created_at.desc())
        ).scalars()
    )


def get_active_retraining_job(db: Session) -> RetrainingJob | None:
    return db.execute(
        select(RetrainingJob)
        .where(RetrainingJob.status.in_({"queued", "running"}))
        .order_by(RetrainingJob.created_at.desc())
    ).scalar_one_or_none()


def get_latest_retraining_job(db: Session) -> RetrainingJob | None:
    return db.execute(
        select(RetrainingJob).order_by(RetrainingJob.created_at.desc())
    ).scalars().first()


def list_completed_retraining_jobs(db: Session) -> list[RetrainingJob]:
    return list(
        db.execute(
            select(RetrainingJob)
            .where(RetrainingJob.status == "completed")
            .order_by(RetrainingJob.finished_at.desc(), RetrainingJob.created_at.desc())
        ).scalars()
    )
