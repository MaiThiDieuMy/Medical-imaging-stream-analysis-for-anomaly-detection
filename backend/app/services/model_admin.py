from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.ai_models import (
    activate_model,
    create_model,
    get_active_model,
    get_model,
    get_model_by_name_version,
    list_models,
)
from app.models.ai_model import AIModel
from app.mlops.mlflow_registry import (
    get_experiment_runs,
    get_registered_model_versions,
    log_local_checkpoint_model,
    register_model_version,
)
from app.core.config import settings
from app.monitoring.metrics import record_mlflow_registration
from app.schemas.admin import (
    AIModelCreate,
    CandidateModelCreate,
    MLflowLocalCheckpointRegisterRequest,
    MLflowModelVersionSummary,
    MLflowModelsResponse,
    MLflowRegisterResponse,
    MLflowRunsResponse,
    MLflowRunSummary,
    PromoteModelResponse,
)

logger = logging.getLogger(__name__)
PROMOTION_METRICS = {
    "accuracy",
    "precision_score",
    "recall_score",
    "f1_score",
}


@dataclass(frozen=True)
class PromotionDecision:
    recommended: bool
    reason: str
    metric_name: str
    candidate_metric: float | None
    active_metric: float | None


class ModelAdminServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ModelAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_models(self) -> list[AIModel]:
        return list_models(self.db)

    def get_active_model(self) -> AIModel:
        model = get_active_model(self.db)
        if model is None:
            raise ModelAdminServiceError("No active AI model found", status_code=404)
        return model

    def get_model(self, model_id: uuid.UUID) -> AIModel:
        model = get_model(self.db, model_id=model_id)
        if model is None:
            raise ModelAdminServiceError("AIModel not found", status_code=404)
        return model

    def create_model(self, payload: AIModelCreate) -> AIModel:
        self._ensure_unique_model_version(payload.model_name, payload.version)
        try:
            if payload.is_active:
                model = create_model(
                    self.db,
                    model_name=payload.model_name,
                    version=payload.version,
                    model_path=payload.model_path,
                    accuracy=payload.accuracy,
                    f1_score=payload.f1_score,
                    precision_score=payload.precision_score,
                    recall_score=payload.recall_score,
                    is_active=False,
                )
                activate_model(self.db, model=model)
            else:
                model = create_model(
                    self.db,
                    model_name=payload.model_name,
                    version=payload.version,
                    model_path=payload.model_path,
                    accuracy=payload.accuracy,
                    f1_score=payload.f1_score,
                    precision_score=payload.precision_score,
                    recall_score=payload.recall_score,
                    is_active=False,
                )
            self.db.commit()
            self.db.refresh(model)
            return model
        except IntegrityError as exc:
            self.db.rollback()
            raise ModelAdminServiceError(
                "AIModel model_name + version must be unique",
                status_code=409,
            ) from exc

    def activate_model(self, model_id: uuid.UUID) -> AIModel:
        model = self.get_model(model_id)
        if model.archived_at is not None:
            raise ModelAdminServiceError(
                "Archived AIModel cannot be activated",
                status_code=409,
            )
        activate_model(self.db, model=model)
        self.db.commit()
        self.db.refresh(model)
        logger.info(
            "Activated AI model: model_id=%s name=%s version=%s",
            model.model_id,
            model.model_name,
            model.version,
        )
        return model

    def register_candidate(self, payload: CandidateModelCreate) -> AIModel:
        return self.create_model(AIModelCreate(**payload.model_dump(), is_active=False))

    def register_local_checkpoint_with_mlflow(
        self,
        payload: MLflowLocalCheckpointRegisterRequest,
    ) -> MLflowRegisterResponse:
        self._ensure_unique_model_version(payload.model_name, payload.version)
        logger.info(
            "MLflow registration started: model_name=%s version=%s path=%s",
            payload.model_name,
            payload.version,
            payload.model_path,
        )
        try:
            logged = log_local_checkpoint_model(
                model_name=payload.model_name,
                version=payload.version,
                model_path=payload.model_path,
                architecture=payload.architecture,
                task_type=payload.task_type,
                accuracy=payload.accuracy,
                precision_score=payload.precision_score,
                recall_score=payload.recall_score,
                f1_score=payload.f1_score,
            )
            registered = register_model_version(
                model_uri=logged.model_uri,
                run_id=logged.run_id,
                registered_model_name=settings.mlflow_registered_model_name,
            )
            model = create_model(
                self.db,
                model_name=payload.model_name,
                version=payload.version,
                model_path=payload.model_path,
                accuracy=payload.accuracy,
                f1_score=payload.f1_score,
                precision_score=payload.precision_score,
                recall_score=payload.recall_score,
                is_active=False,
                mlflow_run_id=logged.run_id,
                mlflow_model_uri=logged.model_uri,
                mlflow_registered_model_name=registered.name,
                mlflow_model_version=registered.version,
            )
            self.db.commit()
            self.db.refresh(model)
            record_mlflow_registration(status="success")
            logger.info(
                "MLflow registration completed: ai_model_id=%s run_id=%s model_version=%s",
                model.model_id,
                logged.run_id,
                registered.version,
            )
        except (FileNotFoundError, ValueError) as exc:
            self.db.rollback()
            record_mlflow_registration(status="error")
            logger.warning(
                "MLflow registration rejected: model_name=%s version=%s reason=%s",
                payload.model_name,
                payload.version,
                exc,
            )
            raise ModelAdminServiceError(str(exc), status_code=404) from exc
        except IntegrityError as exc:
            self.db.rollback()
            record_mlflow_registration(status="error")
            logger.warning(
                "MLflow registration duplicate model metadata: model_name=%s version=%s",
                payload.model_name,
                payload.version,
            )
            raise ModelAdminServiceError(
                "AIModel model_name + version must be unique",
                status_code=409,
            ) from exc
        except Exception as exc:
            self.db.rollback()
            record_mlflow_registration(status="error")
            logger.exception(
                "MLflow registration failed: model_name=%s version=%s",
                payload.model_name,
                payload.version,
            )
            raise ModelAdminServiceError(
                f"MLflow registration failed: {exc}",
                status_code=502,
            ) from exc

        return MLflowRegisterResponse(
            ai_model=model,
            run_id=logged.run_id,
            model_uri=logged.model_uri,
            registered_model_name=registered.name,
            mlflow_model_version=registered.version,
            mlflow_tracking_uri=settings.mlflow_tracking_uri,
            mlflow_ui_url=settings.mlflow_ui_url,
        )

    def list_mlflow_runs(self) -> MLflowRunsResponse:
        try:
            experiment_id, runs = get_experiment_runs()
        except Exception as exc:
            raise ModelAdminServiceError(
                f"MLflow run listing failed: {exc}",
                status_code=502,
            ) from exc

        return MLflowRunsResponse(
            mlflow_tracking_uri=settings.mlflow_tracking_uri,
            experiment_name=settings.mlflow_experiment_name,
            experiment_id=experiment_id,
            runs=[
                MLflowRunSummary(
                    run_id=str(getattr(run.info, "run_id", "")),
                    status=getattr(run.info, "status", None),
                    artifact_uri=getattr(run.info, "artifact_uri", None),
                    params=dict(getattr(run.data, "params", {}) or {}),
                    metrics={
                        key: float(value)
                        for key, value in (getattr(run.data, "metrics", {}) or {}).items()
                    },
                )
                for run in runs
            ],
        )

    def list_mlflow_model_versions(self) -> MLflowModelsResponse:
        try:
            versions = get_registered_model_versions()
        except Exception as exc:
            raise ModelAdminServiceError(
                f"MLflow model listing failed: {exc}",
                status_code=502,
            ) from exc

        return MLflowModelsResponse(
            mlflow_tracking_uri=settings.mlflow_tracking_uri,
            registered_model_name=settings.mlflow_registered_model_name,
            versions=[
                MLflowModelVersionSummary(
                    name=version.name,
                    version=version.version or "",
                    run_id=version.run_id,
                    source=version.source,
                    status=version.status,
                    current_stage=version.current_stage,
                )
                for version in versions
            ],
        )

    def promote_if_better(self, model_id: uuid.UUID) -> PromoteModelResponse:
        candidate = self.get_model(model_id)
        if candidate.archived_at is not None:
            raise ModelAdminServiceError(
                "Archived AIModel cannot be promoted",
                status_code=409,
            )
        active = get_active_model(self.db)

        if candidate.is_active:
            metric_name = self._promotion_metric_name()
            candidate_metric = self._metric_value(candidate, metric_name)
            active_metric = self._metric_value(active, metric_name)
            return PromoteModelResponse(
                promoted=False,
                reason="Model ứng viên đã là model hoạt động.",
                promotion_metric=metric_name,
                candidate_metric=candidate_metric,
                active_metric=active_metric,
                promotion_recommended=False,
                candidate_model=candidate,
                previous_active_model=active,
                active_model=candidate,
            )

        decision = self._promotion_decision(candidate, active)
        if decision.recommended:
            previous_active = active
            activate_model(self.db, model=candidate)
            self.db.commit()
            self.db.refresh(candidate)
            logger.info(
                "Promoted candidate model: model_id=%s version=%s reason=%s",
                candidate.model_id,
                candidate.version,
                decision.reason,
            )
            return PromoteModelResponse(
                promoted=True,
                reason=decision.reason,
                promotion_metric=decision.metric_name,
                candidate_metric=decision.candidate_metric,
                active_metric=decision.active_metric,
                promotion_recommended=True,
                candidate_model=candidate,
                previous_active_model=previous_active,
                active_model=candidate,
            )

        if active is None:
            raise ModelAdminServiceError(
                "No active model exists and candidate could not be promoted",
                status_code=409,
            )

        logger.info(
            "Candidate model not promoted: model_id=%s version=%s reason=%s",
            candidate.model_id,
            candidate.version,
            decision.reason,
        )
        return PromoteModelResponse(
            promoted=False,
            reason=decision.reason,
            promotion_metric=decision.metric_name,
            candidate_metric=decision.candidate_metric,
            active_metric=decision.active_metric,
            promotion_recommended=False,
            candidate_model=candidate,
            previous_active_model=active,
            active_model=active,
        )

    def archive_model(self, model_id: uuid.UUID) -> AIModel:
        model = self.get_model(model_id)
        if model.is_active:
            raise ModelAdminServiceError(
                "Active AIModel cannot be archived. Activate another model first.",
                status_code=409,
            )
        if model.archived_at is None:
            model.archived_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(model)
            logger.info(
                "Archived AI model: model_id=%s name=%s version=%s",
                model.model_id,
                model.model_name,
                model.version,
            )
        return model

    def _ensure_unique_model_version(self, model_name: str, version: str) -> None:
        existing = get_model_by_name_version(
            self.db,
            model_name=model_name,
            version=version,
        )
        if existing is not None:
            raise ModelAdminServiceError(
                "AIModel model_name + version must be unique",
                status_code=409,
            )

    def _promotion_decision(
        self,
        candidate: AIModel,
        active: AIModel | None,
    ) -> PromotionDecision:
        metric_name = self._promotion_metric_name()
        candidate_metric = self._metric_value(candidate, metric_name)
        active_metric = self._metric_value(active, metric_name)

        if active is None:
            return PromotionDecision(
                recommended=True,
                reason="Chưa có model hoạt động; admin có thể chọn model ứng viên.",
                metric_name=metric_name,
                candidate_metric=candidate_metric,
                active_metric=None,
            )
        if active_metric is None:
            return PromotionDecision(
                recommended=False,
                reason=(
                    f"Model đang hoạt động chưa có {metric_name}; cần admin xem lại."
                ),
                metric_name=metric_name,
                candidate_metric=candidate_metric,
                active_metric=None,
            )
        if candidate_metric is None:
            return PromotionDecision(
                recommended=False,
                reason=f"Model ứng viên chưa có {metric_name}.",
                metric_name=metric_name,
                candidate_metric=None,
                active_metric=active_metric,
            )

        threshold = active_metric + settings.model_promotion_min_delta
        if candidate_metric >= threshold:
            return PromotionDecision(
                recommended=True,
                reason=(
                    f"Model ứng viên có {metric_name} lớn hơn hoặc bằng "
                    f"model đang hoạt động cộng ngưỡng delta tối thiểu."
                ),
                metric_name=metric_name,
                candidate_metric=candidate_metric,
                active_metric=active_metric,
            )
        return PromotionDecision(
            recommended=False,
            reason=(
                f"Model ứng viên có {metric_name} thấp hơn model đang hoạt động "
                f"cộng ngưỡng delta tối thiểu."
            ),
            metric_name=metric_name,
            candidate_metric=candidate_metric,
            active_metric=active_metric,
        )

    @staticmethod
    def _promotion_metric_name() -> str:
        metric_name = settings.model_promotion_metric
        if metric_name not in PROMOTION_METRICS:
            raise ModelAdminServiceError(
                "MODEL_PROMOTION_METRIC must be one of: "
                + ", ".join(sorted(PROMOTION_METRICS)),
                status_code=500,
            )
        return metric_name

    @staticmethod
    def _metric_value(model: AIModel | None, metric_name: str) -> float | None:
        if model is None:
            return None
        value = getattr(model, metric_name, None)
        return float(value) if value is not None else None
