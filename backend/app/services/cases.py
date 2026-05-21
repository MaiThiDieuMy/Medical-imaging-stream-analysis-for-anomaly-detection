from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import uuid

from sqlalchemy.orm import Session

from app.crud.cases import get_case, list_cases
from app.models.enums import UserRole
from app.models.xray_case import XRayCase
from app.models.xray_image import XRayImage
from app.models.user import User
from app.schemas.analysis import AnalysisResultItem
from app.schemas.cases import (
    AnalysisJobSummary,
    CaseDetailResponse,
    CaseListItem,
    PatientSummary,
    XRayImageSummary,
)
from app.services.storage import get_image_storage


class CaseServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CaseService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_accessible_cases(self, user: User) -> list[CaseListItem]:
        uploaded_by_id = None if user.role == UserRole.ADMIN else user.user_id
        return [
            self._case_list_item(case)
            for case in list_cases(self.db, uploaded_by_id=uploaded_by_id)
        ]

    def list_my_cases(self, user: User) -> list[CaseListItem]:
        return [
            self._case_list_item(case)
            for case in list_cases(self.db, uploaded_by_id=user.user_id)
        ]

    def get_case_detail(self, case_id: uuid.UUID, user: User) -> CaseDetailResponse:
        case = self._get_accessible_case(case_id, user)
        return self._case_detail(case)

    def archive_case(self, case_id: uuid.UUID, user: User) -> CaseDetailResponse:
        if user.role != UserRole.ADMIN:
            raise CaseServiceError("Admin role required", status_code=403)
        case = get_case(self.db, case_id=case_id)
        if case is None:
            raise CaseServiceError("XRayCase not found", status_code=404)
        if case.archived_at is None:
            case.archived_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(case)
        return self._case_detail(case)

    def get_case_image(self, case_id: uuid.UUID, user: User) -> tuple[bytes, str]:
        case = self._get_accessible_case(case_id, user)
        if case.image is None:
            raise CaseServiceError("XRayImage not found", status_code=404)
        content = get_image_storage().get_image_bytes(case.image.image_path)
        return content, self._media_type(case.image)

    def get_case_report_html(self, case_id: uuid.UUID, user: User) -> str:
        detail = self.get_case_detail(case_id, user)
        rows = "\n".join(
            "<tr>"
            f"<td>{escape(result.label_name)}</td>"
            f"<td>{result.probability * 100:.1f}%</td>"
            f"<td>{'Positive' if result.predicted_positive else 'Negative'}</td>"
            "</tr>"
            for result in detail.results
        )
        return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>X-Ray AI Report {detail.case_id}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #18202a; margin: 32px; }}
    h1, h2 {{ margin-bottom: 8px; }}
    dl {{ display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; }}
    dt {{ font-weight: bold; color: #475569; }}
    dd {{ margin: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid #dbe4ee; padding: 8px; text-align: left; }}
    th {{ background: #f4f7fb; }}
    .muted {{ color: #64748b; }}
  </style>
</head>
<body>
  <h1>X-Ray AI Analysis Report</h1>
  <p class="muted">Demo report. Not clinically meaningful.</p>
  <h2>Patient</h2>
  <dl>
    <dt>Patient code</dt><dd>{escape(detail.patient.patient_code)}</dd>
    <dt>Full name</dt><dd>{escape(detail.patient.full_name)}</dd>
    <dt>Gender</dt><dd>{escape(detail.patient.gender)}</dd>
    <dt>Birth year</dt><dd>{detail.patient.birth_year or '-'}</dd>
    <dt>Department</dt><dd>{escape(detail.patient.department or '-')}</dd>
  </dl>
  <h2>Case</h2>
  <dl>
    <dt>Case ID</dt><dd>{detail.case_id}</dd>
    <dt>Status</dt><dd>{escape(detail.status)}</dd>
    <dt>Model version</dt><dd>{escape(detail.model_version or '-')}</dd>
    <dt>Review status</dt><dd>{escape(detail.review_status or '-')}</dd>
    <dt>Note</dt><dd>{escape(detail.note or '-')}</dd>
  </dl>
  <h2>AI Results</h2>
  <table>
    <thead><tr><th>Label</th><th>Probability</th><th>Prediction</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""

    def ensure_access(self, case_id: uuid.UUID, user: User) -> None:
        self._get_accessible_case(case_id, user)

    def _get_accessible_case(self, case_id: uuid.UUID, user: User) -> XRayCase:
        case = get_case(self.db, case_id=case_id)
        if case is None:
            raise CaseServiceError("XRayCase not found", status_code=404)
        if user.role != UserRole.ADMIN and case.uploaded_by_id != user.user_id:
            raise CaseServiceError("XRayCase not found", status_code=404)
        return case

    def _case_list_item(self, case: XRayCase) -> CaseListItem:
        return CaseListItem(
            case_id=case.case_id,
            status=case.status.value,
            patient_code=case.patient.patient_code,
            patient_name=case.patient.full_name,
            uploaded_by=case.uploaded_by_id,
            model_version=(
                case.analysis_job.model.version if case.analysis_job is not None else None
            ),
            review_status=case.review.status if case.review is not None else None,
            created_at=case.created_at,
            updated_at=case.updated_at,
            archived_at=case.archived_at,
        )

    def _case_detail(self, case: XRayCase) -> CaseDetailResponse:
        job = None
        model_version = None
        if case.analysis_job is not None:
            model_version = case.analysis_job.model.version
            job = AnalysisJobSummary(
                job_id=case.analysis_job.job_id,
                status=case.analysis_job.status.value,
                model_id=case.analysis_job.model_id,
                model_version=model_version,
                error_message=case.analysis_job.error_message,
                created_at=case.analysis_job.created_at,
                started_at=case.analysis_job.started_at,
                finished_at=case.analysis_job.finished_at,
            )
        return CaseDetailResponse(
            case_id=case.case_id,
            status=case.status.value,
            note=case.note,
            uploaded_by=case.uploaded_by_id,
            created_at=case.created_at,
            updated_at=case.updated_at,
            archived_at=case.archived_at,
            patient=PatientSummary.model_validate(case.patient, from_attributes=True),
            image=(
                XRayImageSummary.model_validate(case.image, from_attributes=True)
                if case.image is not None
                else None
            ),
            job=job,
            model_version=model_version,
            review_status=case.review.status if case.review is not None else None,
            review_note=case.review.note if case.review is not None else None,
            results=[
                AnalysisResultItem.model_validate(result, from_attributes=True)
                for result in sorted(case.analysis_results, key=lambda item: item.label_name)
            ],
        )

    @staticmethod
    def _media_type(image: XRayImage) -> str:
        return "image/png" if image.file_format.lower() == "png" else "image/jpeg"
