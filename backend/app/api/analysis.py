from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.auth import require_doctor_or_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.analysis import (
    AnalyzeResponse,
    CaseResultsResponse,
    CaseStatusResponse,
    JobStatusResponse,
    PatientAnalyzeRequest,
)
from app.schemas.cases import (
    CaseConfirmResultRequest,
    CaseCorrectLabelsRequest,
    CaseDetailResponse,
    CaseListItem,
    CaseReviewStatusResponse,
    ConfirmedLabelSummary,
    PatientSummary,
    PatientUpdate,
)
from app.services.analyze import (
    AnalyzeService,
    AnalyzeServiceError,
    UploadedImageData,
)
from app.services.cases import CaseService, CaseServiceError
from app.services.patients import PatientService, PatientServiceError
from app.services.reviews import ReviewService, ReviewServiceError

router = APIRouter(tags=["analysis"])


def _service_error_to_http(exc: AnalyzeServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _case_error_to_http(exc: CaseServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _review_error_to_http(exc: ReviewServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _patient_error_to_http(exc: PatientServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _case_review_status_response(
    case_id: UUID,
    review,
) -> CaseReviewStatusResponse:
    if review is None:
        return CaseReviewStatusResponse(case_id=case_id, status="no_review")
    return CaseReviewStatusResponse(
        review_id=review.review_id,
        case_id=review.case_id,
        status=review.status,
        reason=review.reason,
        reviewed_by=review.reviewed_by_id,
        reviewed_at=review.reviewed_at,
        note=review.note,
        confirmed_labels=[
            ConfirmedLabelSummary.model_validate(label, from_attributes=True)
            for label in sorted(review.confirmed_labels, key=lambda item: item.label_name)
        ],
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_xray(
    response: Response,
    full_name: Annotated[str, Form(min_length=1, max_length=100)],
    gender: Annotated[str, Form(min_length=1, max_length=10)],
    image: Annotated[UploadFile, File()],
    patient_code: Annotated[str | None, Form(min_length=1, max_length=20)] = None,
    birth_year: Annotated[int | None, Form(ge=1900, le=2100)] = None,
    department: Annotated[str | None, Form(max_length=100)] = None,
    note: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> AnalyzeResponse:
    patient_data = PatientAnalyzeRequest(
        patient_code=patient_code,
        full_name=full_name,
        gender=gender,
        birth_year=birth_year,
        department=department,
        note=note,
    )
    image_bytes = await image.read(settings.max_upload_size_bytes + 1)
    uploaded_image = UploadedImageData(
        filename=image.filename or "",
        content_type=image.content_type,
        content=image_bytes,
    )

    try:
        result = AnalyzeService(db).analyze_upload(
            patient_data,
            uploaded_image,
            uploaded_by_id=current_user.user_id,
        )
    except AnalyzeServiceError as exc:
        raise _service_error_to_http(exc) from exc

    response.status_code = 200 if result.cache_hit else 202
    return result


@router.patch("/patients/{patient_id}", response_model=PatientSummary)
def update_patient(
    patient_id: UUID,
    payload: PatientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> PatientSummary:
    try:
        patient = PatientService(db).update_patient(patient_id, payload, current_user)
    except PatientServiceError as exc:
        raise _patient_error_to_http(exc) from exc
    return PatientSummary.model_validate(patient, from_attributes=True)


@router.get("/cases/{case_id}/review-status", response_model=CaseReviewStatusResponse)
def get_case_review_status(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseReviewStatusResponse:
    try:
        CaseService(db).ensure_access(case_id, current_user)
        review = ReviewService(db).get_review_status_for_case(case_id)
        return _case_review_status_response(case_id, review)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc


@router.post("/cases/{case_id}/confirm-result", response_model=CaseReviewStatusResponse)
def confirm_case_result(
    case_id: UUID,
    payload: CaseConfirmResultRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseReviewStatusResponse:
    payload = payload or CaseConfirmResultRequest()
    try:
        CaseService(db).ensure_access(case_id, current_user)
        review = ReviewService(db).confirm_case_result(
            case_id,
            note=payload.note,
            reviewed_by=current_user.user_id,
        )
        return _case_review_status_response(case_id, review)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc
    except ReviewServiceError as exc:
        raise _review_error_to_http(exc) from exc


@router.post("/cases/{case_id}/correct-labels", response_model=CaseReviewStatusResponse)
def correct_case_labels(
    case_id: UUID,
    payload: CaseCorrectLabelsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseReviewStatusResponse:
    try:
        CaseService(db).ensure_access(case_id, current_user)
        review = ReviewService(db).correct_case_labels(
            case_id,
            labels=payload.label_map(),
            note=payload.note,
            reviewed_by=current_user.user_id,
        )
        return _case_review_status_response(case_id, review)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc
    except ReviewServiceError as exc:
        raise _review_error_to_http(exc) from exc


@router.get("/cases", response_model=list[CaseListItem])
def list_cases(
    archive_filter: str = Query("active", pattern="^(active|archived|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> list[CaseListItem]:
    return CaseService(db).list_accessible_cases(
        current_user,
        archive_filter=archive_filter,
    )


@router.get("/cases/my", response_model=list[CaseListItem])
def list_my_cases(
    archive_filter: str = Query("active", pattern="^(active|archived|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> list[CaseListItem]:
    return CaseService(db).list_my_cases(
        current_user,
        archive_filter=archive_filter,
    )


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
def get_case_detail(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseDetailResponse:
    try:
        return CaseService(db).get_case_detail(case_id, current_user)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc


@router.post("/cases/{case_id}/archive", response_model=CaseDetailResponse)
def archive_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseDetailResponse:
    try:
        return CaseService(db).archive_case(case_id, current_user)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc


@router.patch("/cases/{case_id}/restore", response_model=CaseDetailResponse)
def restore_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseDetailResponse:
    try:
        return CaseService(db).restore_case(case_id, current_user)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc


@router.get("/cases/{case_id}/image")
def get_case_image(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> Response:
    try:
        content, media_type = CaseService(db).get_case_image(case_id, current_user)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc
    return Response(content=content, media_type=media_type)


@router.get("/cases/{case_id}/report", response_class=HTMLResponse)
def get_case_report(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> HTMLResponse:
    try:
        html = CaseService(db).get_case_report_html(case_id, current_user)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc
    return HTMLResponse(content=html)


@router.get("/cases/{case_id}/status", response_model=CaseStatusResponse)
def get_case_status(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseStatusResponse:
    try:
        CaseService(db).ensure_access(case_id, current_user)
        return AnalyzeService(db).get_case_status(case_id)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc
    except AnalyzeServiceError as exc:
        raise _service_error_to_http(exc) from exc


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> JobStatusResponse:
    try:
        status = AnalyzeService(db).get_job_status(job_id)
        CaseService(db).ensure_access(status.case_id, current_user)
        return status
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc
    except AnalyzeServiceError as exc:
        raise _service_error_to_http(exc) from exc


@router.get("/cases/{case_id}/results", response_model=CaseResultsResponse)
def get_case_results(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseResultsResponse:
    try:
        CaseService(db).ensure_access(case_id, current_user)
        return AnalyzeService(db).get_case_results(case_id)
    except CaseServiceError as exc:
        raise _case_error_to_http(exc) from exc
    except AnalyzeServiceError as exc:
        raise _service_error_to_http(exc) from exc
