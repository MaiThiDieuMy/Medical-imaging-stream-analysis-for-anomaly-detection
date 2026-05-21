from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.auth import require_admin, require_doctor_or_admin
from app.core.database import get_db
from app.models.case_review import CaseReview
from app.models.user import User
from app.schemas.admin import (
    AIModelCreate,
    AIModelResponse,
    AnalysisResultReviewItem,
    CandidateModelCreate,
    CaseReviewResponse,
    ConfirmedLabelItem,
    ManifestExportResponse,
    MLflowLocalCheckpointRegisterRequest,
    MLflowModelsResponse,
    MLflowRegisterResponse,
    MLflowRunsResponse,
    PromoteModelResponse,
    RetrainingCheckResponse,
    RetrainingSummaryResponse,
    ReviewConfirmRequest,
    ReviewCorrectRequest,
    TrainingReadySample,
)
from app.schemas.users import UserCreate, UserResponse, UserUpdate
from app.services.mlops import MLOpsService
from app.services.model_admin import ModelAdminService, ModelAdminServiceError
from app.services.reviews import ReviewService, ReviewServiceError
from app.services.users import UserService, UserServiceError

router = APIRouter(prefix="/admin", tags=["admin"])


def _model_error_to_http(exc: ModelAdminServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _review_error_to_http(exc: ReviewServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _user_error_to_http(exc: UserServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _review_response(review: CaseReview) -> CaseReviewResponse:
    analysis_results = []
    if review.case is not None:
        analysis_results = [
            AnalysisResultReviewItem.model_validate(result, from_attributes=True)
            for result in sorted(
                review.case.analysis_results,
                key=lambda item: item.label_name,
            )
        ]

    confirmed_labels = [
        ConfirmedLabelItem.model_validate(label, from_attributes=True)
        for label in sorted(review.confirmed_labels, key=lambda item: item.label_name)
    ]

    return CaseReviewResponse(
        review_id=review.review_id,
        case_id=review.case_id,
        status=review.status,
        reason=review.reason,
        created_at=review.created_at,
        reviewed_at=review.reviewed_at,
        reviewed_by=review.reviewed_by_id,
        note=review.note,
        analysis_results=analysis_results,
        confirmed_labels=confirmed_labels,
    )


def _training_ready_sample(review: CaseReview) -> TrainingReadySample:
    response = _review_response(review)
    return TrainingReadySample(
        review_id=response.review_id,
        case_id=response.case_id,
        status=response.status,
        confirmed_labels=response.confirmed_labels,
    )


@router.get("/models", response_model=list[AIModelResponse])
def list_models(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[AIModelResponse]:
    return ModelAdminService(db).list_models()


@router.get("/models/active", response_model=AIModelResponse)
def get_active_model(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AIModelResponse:
    try:
        return ModelAdminService(db).get_active_model()
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc


@router.get("/models/{model_id}", response_model=AIModelResponse)
def get_model(
    model_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AIModelResponse:
    try:
        return ModelAdminService(db).get_model(model_id)
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc


@router.post("/models", response_model=AIModelResponse)
def create_model(
    payload: AIModelCreate,
    response: Response,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AIModelResponse:
    try:
        model = ModelAdminService(db).create_model(payload)
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc
    response.status_code = 201
    return model


@router.post("/models/{model_id}/activate", response_model=AIModelResponse)
def activate_model(
    model_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AIModelResponse:
    try:
        return ModelAdminService(db).activate_model(model_id)
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc


@router.post("/models/{model_id}/archive", response_model=AIModelResponse)
def archive_model(
    model_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AIModelResponse:
    try:
        return ModelAdminService(db).archive_model(model_id)
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[UserResponse]:
    return UserService(db).list_users()


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> UserResponse:
    try:
        return UserService(db).get_user(user_id)
    except UserServiceError as exc:
        raise _user_error_to_http(exc) from exc


@router.post("/users", response_model=UserResponse)
def create_user(
    payload: UserCreate,
    response: Response,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> UserResponse:
    try:
        user = UserService(db).create_user(payload)
    except UserServiceError as exc:
        raise _user_error_to_http(exc) from exc
    response.status_code = 201
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> UserResponse:
    try:
        return UserService(db).update_user(user_id, payload)
    except UserServiceError as exc:
        raise _user_error_to_http(exc) from exc


@router.get("/reviews/pending", response_model=list[CaseReviewResponse])
def list_pending_reviews(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_doctor_or_admin),
) -> list[CaseReviewResponse]:
    reviews = ReviewService(db).list_pending_reviews()
    return [_review_response(review) for review in reviews]


@router.get("/reviews/training-ready", response_model=list[TrainingReadySample])
def list_training_ready_reviews(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[TrainingReadySample]:
    reviews = ReviewService(db).list_training_ready()
    return [_training_ready_sample(review) for review in reviews]


@router.get("/reviews/{review_id}", response_model=CaseReviewResponse)
def get_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_doctor_or_admin),
) -> CaseReviewResponse:
    try:
        review = ReviewService(db).get_review(review_id)
    except ReviewServiceError as exc:
        raise _review_error_to_http(exc) from exc
    return _review_response(review)


@router.post("/reviews/{review_id}/confirm", response_model=CaseReviewResponse)
def confirm_review(
    review_id: UUID,
    payload: ReviewConfirmRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseReviewResponse:
    payload = payload or ReviewConfirmRequest()
    try:
        review = ReviewService(db).confirm_review(
            review_id,
            note=payload.note,
            reviewed_by=current_user.user_id,
        )
    except ReviewServiceError as exc:
        raise _review_error_to_http(exc) from exc
    return _review_response(review)


@router.post("/reviews/{review_id}/correct", response_model=CaseReviewResponse)
def correct_review(
    review_id: UUID,
    payload: ReviewCorrectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_doctor_or_admin),
) -> CaseReviewResponse:
    labels = {
        item.label_name: item.confirmed_positive
        for item in payload.labels
    }
    try:
        review = ReviewService(db).correct_review(
            review_id,
            labels=labels,
            note=payload.note,
            reviewed_by=current_user.user_id,
        )
    except ReviewServiceError as exc:
        raise _review_error_to_http(exc) from exc
    return _review_response(review)


@router.get("/mlops/retraining/summary", response_model=RetrainingSummaryResponse)
def get_retraining_summary(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> RetrainingSummaryResponse:
    return RetrainingSummaryResponse(**MLOpsService(db).retraining_summary())


@router.get("/mlops/retraining/samples", response_model=list[TrainingReadySample])
def get_retraining_samples(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[TrainingReadySample]:
    return [
        _training_ready_sample(review)
        for review in MLOpsService(db).training_ready_samples()
    ]


@router.post("/mlops/retraining/check", response_model=RetrainingCheckResponse)
def check_retraining(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> RetrainingCheckResponse:
    return RetrainingCheckResponse(**MLOpsService(db).retraining_check())


@router.post(
    "/mlops/retraining/export-manifest",
    response_model=ManifestExportResponse,
)
def export_retraining_manifest(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> ManifestExportResponse:
    return ManifestExportResponse(**MLOpsService(db).export_manifest())


@router.post(
    "/mlops/models/register-candidate",
    response_model=AIModelResponse,
)
def register_candidate_model(
    payload: CandidateModelCreate,
    response: Response,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> AIModelResponse:
    try:
        model = ModelAdminService(db).register_candidate(payload)
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc


@router.post(
    "/mlops/mlflow/register-local-checkpoint",
    response_model=MLflowRegisterResponse,
)
def register_local_checkpoint_to_mlflow(
    payload: MLflowLocalCheckpointRegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> MLflowRegisterResponse:
    try:
        result = ModelAdminService(db).register_local_checkpoint_with_mlflow(payload)
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc
    response.status_code = 201
    return result


@router.get("/mlops/mlflow/runs", response_model=MLflowRunsResponse)
def list_mlflow_runs(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> MLflowRunsResponse:
    try:
        return ModelAdminService(db).list_mlflow_runs()
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc


@router.get("/mlops/mlflow/models", response_model=MLflowModelsResponse)
def list_mlflow_models(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> MLflowModelsResponse:
    try:
        return ModelAdminService(db).list_mlflow_model_versions()
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc
    response.status_code = 201
    return model


@router.post(
    "/mlops/models/{model_id}/promote-if-better",
    response_model=PromoteModelResponse,
)
def promote_candidate_if_better(
    model_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> PromoteModelResponse:
    try:
        return ModelAdminService(db).promote_if_better(model_id)
    except ModelAdminServiceError as exc:
        raise _model_error_to_http(exc) from exc
