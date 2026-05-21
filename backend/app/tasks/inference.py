from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

from celery import Task
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import SessionLocal
from app.ml.inference import run_inference
from app.ml.model_loader import load_model
from app.models.ai_model import AIModel
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.enums import ProcessingStatus
from app.services.reviews import ensure_pending_review_for_outputs
from app.models.xray_case import XRayCase
from app.services.storage import get_image_storage
from app.tasks.celery_app import celery_app

MAX_ERROR_MESSAGE_LENGTH = 4000
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id)
    except ValueError as exc:
        raise ValueError(f"Invalid job_id: {job_id}") from exc


def _load_job(db: Session, job_id: uuid.UUID) -> AnalysisJob | None:
    statement = (
        select(AnalysisJob)
        .where(AnalysisJob.job_id == job_id)
        .options(
            selectinload(AnalysisJob.case).selectinload(XRayCase.image),
            selectinload(AnalysisJob.model),
        )
    )
    return db.execute(statement).scalar_one_or_none()


def _set_failed_status(db: Session, job_id: uuid.UUID, error: Exception) -> None:
    failed_job = _load_job(db, job_id)
    if failed_job is None:
        return

    failed_job.status = ProcessingStatus.FAILED
    failed_job.error_message = str(error)[:MAX_ERROR_MESSAGE_LENGTH]
    failed_job.finished_at = _utc_now()
    if failed_job.case is not None:
        failed_job.case.status = ProcessingStatus.FAILED
    db.commit()


def _upsert_analysis_result(
    db: Session,
    *,
    case_id: uuid.UUID,
    model_id: uuid.UUID,
    label_name: str,
    probability: float,
    predicted_positive: bool,
) -> None:
    statement = select(AnalysisResult).where(
        AnalysisResult.case_id == case_id,
        AnalysisResult.model_id == model_id,
        AnalysisResult.label_name == label_name,
    )
    existing_result = db.execute(statement).scalar_one_or_none()

    if existing_result is None:
        db.add(
            AnalysisResult(
                case_id=case_id,
                model_id=model_id,
                label_name=label_name,
                probability=probability,
                predicted_positive=predicted_positive,
            )
        )
        return

    existing_result.probability = probability
    existing_result.predicted_positive = predicted_positive


def _load_model_for_job(ai_model: AIModel):
    model_path = settings.model_weights_path or ai_model.model_path
    return load_model(
        model_source=settings.model_source,
        model_path=model_path,
        architecture=settings.model_architecture,
        device=settings.model_device,
        allow_demo_model=settings.allow_demo_model,
    )


@celery_app.task(name="app.tasks.inference.perform_inference", bind=True)
def perform_inference(self: Task, job_id: str) -> dict[str, str | int | bool | None]:
    parsed_job_id = _parse_job_id(job_id)
    db = SessionLocal()

    try:
        job = _load_job(db, parsed_job_id)
        if job is None:
            raise ValueError(f"AnalysisJob not found: {job_id}")
        if job.case is None:
            raise ValueError(f"AnalysisJob has no XRayCase: {job_id}")
        if job.case.image is None:
            raise ValueError(f"XRayCase has no XRayImage: {job.case_id}")
        if job.model is None:
            raise ValueError(f"AnalysisJob has no AIModel: {job_id}")

        logger.info(
            "Worker processing job: job_id=%s case_id=%s model_id=%s",
            job.job_id,
            job.case_id,
            job.model_id,
        )
        now = _utc_now()
        job.status = ProcessingStatus.PROCESSING
        job.started_at = now
        job.finished_at = None
        job.error_message = None
        job.worker_id = self.request.hostname or self.request.id
        job.case.status = ProcessingStatus.PROCESSING
        db.commit()

        image_input = get_image_storage().get_image_input(job.case.image.image_path)
        loaded_model = _load_model_for_job(job.model)
        outputs = run_inference(
            image_input,
            loaded_model=loaded_model,
            threshold=settings.model_threshold,
        )

        for output in outputs:
            _upsert_analysis_result(
                db,
                case_id=job.case_id,
                model_id=job.model_id,
                label_name=output.label_name,
                probability=output.probability,
                predicted_positive=output.predicted_positive,
            )

        job.status = ProcessingStatus.COMPLETED
        job.finished_at = _utc_now()
        job.case.status = ProcessingStatus.COMPLETED
        db.commit()

        review_required = False
        review_id: str | None = None
        try:
            review = ensure_pending_review_for_outputs(
                db,
                case_id=job.case_id,
                outputs=outputs,
            )
            if review is not None:
                db.commit()
                review_required = True
                review_id = str(review.review_id)
        except Exception:
            db.rollback()
            logger.exception("Failed to create low-confidence review for job %s", job_id)

        logger.info(
            "Worker completed job: job_id=%s case_id=%s results_count=%s review_required=%s",
            job.job_id,
            job.case_id,
            len(outputs),
            review_required,
        )
        return {
            "job_id": str(job.job_id),
            "case_id": str(job.case_id),
            "status": ProcessingStatus.COMPLETED.value,
            "results_count": len(outputs),
            "review_required": review_required,
            "review_id": review_id,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Worker failed job: job_id=%s", job_id)
        _set_failed_status(db, parsed_job_id, exc)
        raise
    finally:
        db.close()
