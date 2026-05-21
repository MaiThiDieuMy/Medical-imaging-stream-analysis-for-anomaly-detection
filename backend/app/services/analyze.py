from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import logging
import uuid

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.ai_models import get_active_model
from app.crud.analysis import (
    create_queued_analysis,
    get_cached_case_with_results,
    get_case_with_job,
    get_case_with_results,
    get_job_with_model,
    get_or_update_patient,
)
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.enums import ProcessingStatus
from app.monitoring.metrics import record_analyze_result
from app.schemas.analysis import (
    AnalysisResultItem,
    AnalyzeResponse,
    CaseResultsResponse,
    CaseStatusResponse,
    JobStatusResponse,
    PatientAnalyzeRequest,
)
from app.services.storage import ImageStorage, get_image_storage
from app.tasks.inference import perform_inference

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadedImageData:
    filename: str
    content_type: str | None
    content: bytes


class AnalyzeServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def enqueue_inference_task(job_id: str) -> object:
    return perform_inference.delay(job_id)


class AnalyzeService:
    def __init__(
        self,
        db: Session,
        *,
        storage: ImageStorage | None = None,
        enqueue: Callable[[str], object] = enqueue_inference_task,
    ) -> None:
        self.db = db
        self.storage = storage or get_image_storage()
        self.enqueue = enqueue

    def analyze_upload(
        self,
        patient_data: PatientAnalyzeRequest,
        image: UploadedImageData,
        *,
        uploaded_by_id: uuid.UUID | None = None,
    ) -> AnalyzeResponse:
        logger.info(
            "Analyze request started: filename=%s uploaded_by=%s",
            image.filename,
            uploaded_by_id,
        )
        file_format = self._validate_uploaded_image(image)
        image_hash = sha256(image.content).hexdigest()

        active_model = get_active_model(self.db)
        if active_model is None:
            raise AnalyzeServiceError(
                "No active AI model is configured. Seed a demo model first.",
                status_code=503,
            )

        cached = get_cached_case_with_results(
            self.db,
            image_hash=image_hash,
            model_id=active_model.model_id,
        )
        if cached is not None:
            cached_case, cached_results = cached
            logger.info(
                "Analyze cache hit: image_hash=%s model_id=%s case_id=%s",
                image_hash[:12],
                active_model.model_id,
                cached_case.case_id,
            )
            record_analyze_result(cache_hit=True)
            return AnalyzeResponse(
                status=ProcessingStatus.COMPLETED.value,
                cache_hit=True,
                case_id=cached_case.case_id,
                job_id=(
                    cached_case.analysis_job.job_id
                    if cached_case.analysis_job is not None
                    else None
                ),
                model_id=active_model.model_id,
                model_version=active_model.version,
                results=self._result_items(cached_results),
            )

        patient = get_or_update_patient(
            self.db,
            patient_code=patient_data.patient_code.strip(),
            full_name=patient_data.full_name.strip(),
            gender=patient_data.gender.strip(),
            birth_year=patient_data.birth_year,
            department=(
                patient_data.department.strip()
                if patient_data.department is not None
                else None
            ),
        )
        image_path = self.storage.save_image_bytes(
            image.content,
            image_hash=image_hash,
            file_format=file_format,
        )
        case, _, job = create_queued_analysis(
            self.db,
            patient=patient,
            model=active_model,
            image_path=image_path,
            image_hash=image_hash,
            file_name=image.filename,
            file_format=file_format,
            note=patient_data.note,
            uploaded_by_id=uploaded_by_id,
        )
        self.db.commit()
        self.db.refresh(case)
        self.db.refresh(job)

        try:
            self.enqueue(str(job.job_id))
            logger.info(
                "Analyze cache miss queued: image_hash=%s case_id=%s job_id=%s model_id=%s",
                image_hash[:12],
                case.case_id,
                job.job_id,
                active_model.model_id,
            )
            record_analyze_result(cache_hit=False)
        except Exception as exc:
            logger.exception(
                "Failed to enqueue inference job: case_id=%s job_id=%s",
                case.case_id,
                job.job_id,
            )
            job.status = ProcessingStatus.FAILED
            job.error_message = str(exc)
            case.status = ProcessingStatus.FAILED
            self.db.commit()
            raise AnalyzeServiceError(
                f"Failed to enqueue inference job: {exc}",
                status_code=503,
            ) from exc

        return AnalyzeResponse(
            status=ProcessingStatus.QUEUED.value,
            cache_hit=False,
            case_id=case.case_id,
            job_id=job.job_id,
            model_id=active_model.model_id,
            model_version=active_model.version,
            results=[],
        )

    def get_case_status(self, case_id: uuid.UUID) -> CaseStatusResponse:
        case = get_case_with_job(self.db, case_id=case_id)
        if case is None:
            raise AnalyzeServiceError("XRayCase not found", status_code=404)

        job = case.analysis_job
        return CaseStatusResponse(
            case_id=case.case_id,
            status=case.status.value,
            patient_id=case.patient_id,
            job_id=job.job_id if job is not None else None,
            job_status=job.status.value if job is not None else None,
            error_message=job.error_message if job is not None else None,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )

    def get_job_status(self, job_id: uuid.UUID) -> JobStatusResponse:
        job = get_job_with_model(self.db, job_id=job_id)
        if job is None:
            raise AnalyzeServiceError("AnalysisJob not found", status_code=404)

        return self._job_status_response(job)

    def get_case_results(self, case_id: uuid.UUID) -> CaseResultsResponse:
        case = get_case_with_results(self.db, case_id=case_id)
        if case is None:
            raise AnalyzeServiceError("XRayCase not found", status_code=404)

        model_id = None
        model_version = None
        if case.analysis_job is not None:
            model_id = case.analysis_job.model_id
            model_version = case.analysis_job.model.version
            results = [
                result
                for result in case.analysis_results
                if result.model_id == case.analysis_job.model_id
            ]
        else:
            results = list(case.analysis_results)
            if results:
                model_id = results[0].model_id
                model_version = results[0].model.version

        return CaseResultsResponse(
            case_id=case.case_id,
            status=case.status.value,
            model_id=model_id,
            model_version=model_version,
            results=self._result_items(results),
        )

    def _validate_uploaded_image(self, image: UploadedImageData) -> str:
        if not image.filename:
            raise AnalyzeServiceError("Image filename is required")
        if not image.content:
            raise AnalyzeServiceError("Uploaded image is empty")
        if len(image.content) > settings.max_upload_size_bytes:
            raise AnalyzeServiceError(
                "Uploaded image exceeds the configured size limit",
                status_code=413,
            )

        extension = self._extract_extension(image.filename)
        allowed_extensions = self._csv_values(settings.allowed_image_extensions)
        if extension not in allowed_extensions:
            raise AnalyzeServiceError(
                f"Unsupported image extension '{extension}'",
            )

        content_type = (image.content_type or "").lower()
        allowed_content_types = self._csv_values(settings.allowed_image_content_types)
        if content_type not in allowed_content_types:
            raise AnalyzeServiceError(
                f"Unsupported image content type '{content_type or 'unknown'}'",
            )

        self._verify_image_content(image.content)
        return "jpg" if extension == ".jpeg" else extension.lstrip(".")

    @staticmethod
    def _extract_extension(filename: str) -> str:
        if "." not in filename:
            raise AnalyzeServiceError("Image filename must include an extension")
        return f".{filename.rsplit('.', 1)[1].lower()}"

    @staticmethod
    def _csv_values(value: str) -> set[str]:
        return {item.strip().lower() for item in value.split(",") if item.strip()}

    @staticmethod
    def _verify_image_content(content: bytes) -> None:
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except (SyntaxError, UnidentifiedImageError, OSError) as exc:
            raise AnalyzeServiceError("Uploaded file is not a readable image") from exc

    @staticmethod
    def _result_items(
        results: list[AnalysisResult],
    ) -> list[AnalysisResultItem]:
        return [
            AnalysisResultItem.model_validate(result, from_attributes=True)
            for result in sorted(results, key=lambda item: item.label_name)
        ]

    @staticmethod
    def _job_status_response(job: AnalysisJob) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=job.job_id,
            case_id=job.case_id,
            model_id=job.model_id,
            model_version=job.model.version,
            status=job.status.value,
            worker_id=job.worker_id,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
