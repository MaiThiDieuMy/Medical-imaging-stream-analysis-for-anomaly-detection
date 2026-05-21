from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ml.labels import DEMO_LABELS


class AIModelBase(BaseModel):
    model_name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=20)
    model_path: str = Field(min_length=1)
    accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    f1_score: float | None = Field(default=None, ge=0.0, le=1.0)
    precision_score: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_score: float | None = Field(default=None, ge=0.0, le=1.0)


class AIModelCreate(AIModelBase):
    is_active: bool = False


class CandidateModelCreate(AIModelBase):
    pass


class AIModelResponse(AIModelBase):
    model_id: UUID
    is_active: bool
    created_at: datetime
    archived_at: datetime | None = None
    mlflow_run_id: str | None = None
    mlflow_model_uri: str | None = None
    mlflow_registered_model_name: str | None = None
    mlflow_model_version: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PromoteModelResponse(BaseModel):
    promoted: bool
    reason: str
    candidate_model: AIModelResponse
    previous_active_model: AIModelResponse | None = None
    active_model: AIModelResponse


class AnalysisResultReviewItem(BaseModel):
    label_name: str
    probability: float
    predicted_positive: bool

    model_config = ConfigDict(from_attributes=True)


class ConfirmedLabelItem(BaseModel):
    label_name: str
    confirmed_positive: bool

    model_config = ConfigDict(from_attributes=True)


class CaseReviewResponse(BaseModel):
    review_id: UUID
    case_id: UUID
    status: str
    reason: str
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    note: str | None = None
    analysis_results: list[AnalysisResultReviewItem] = Field(default_factory=list)
    confirmed_labels: list[ConfirmedLabelItem] = Field(default_factory=list)


class ReviewConfirmRequest(BaseModel):
    note: str | None = None
    reviewed_by: UUID | None = None


class LabelCorrection(BaseModel):
    label_name: str
    confirmed_positive: bool


class ReviewCorrectRequest(BaseModel):
    labels: list[LabelCorrection]
    note: str | None = None
    reviewed_by: UUID | None = None

    @model_validator(mode="after")
    def validate_demo_labels(self) -> "ReviewCorrectRequest":
        label_names = [item.label_name for item in self.labels]
        expected = set(DEMO_LABELS)
        if set(label_names) != expected or len(label_names) != len(expected):
            raise ValueError(
                "Corrected labels must include exactly: "
                f"{', '.join(DEMO_LABELS)}"
            )
        return self


class TrainingReadySample(BaseModel):
    review_id: UUID
    case_id: UUID
    status: str
    confirmed_labels: list[ConfirmedLabelItem]


class RetrainingSummaryResponse(BaseModel):
    min_confirmed_samples: int
    pending_reviews: int
    confirmed_reviews: int
    corrected_reviews: int
    training_ready_cases: int
    should_trigger_retraining: bool


class RetrainingCheckResponse(RetrainingSummaryResponse):
    message: str


class ManifestExportResponse(BaseModel):
    manifest_path: str
    samples_count: int
    message: str


class ClassificationMetricsResponse(BaseModel):
    accuracy: float
    precision_score: float
    recall_score: float
    f1_score: float


class MLflowLocalCheckpointRegisterRequest(AIModelBase):
    architecture: str = Field(default="mobilenet_v3_small", min_length=1)
    task_type: str = Field(default="multi_class", pattern="^multi_class$")


class MLflowRegisterResponse(BaseModel):
    ai_model: AIModelResponse
    run_id: str
    model_uri: str
    registered_model_name: str
    mlflow_model_version: str | None = None
    mlflow_tracking_uri: str
    mlflow_ui_url: str


class MLflowRunSummary(BaseModel):
    run_id: str
    status: str | None = None
    artifact_uri: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


class MLflowRunsResponse(BaseModel):
    mlflow_tracking_uri: str
    experiment_name: str
    experiment_id: str | None = None
    runs: list[MLflowRunSummary] = Field(default_factory=list)


class MLflowModelVersionSummary(BaseModel):
    name: str
    version: str
    run_id: str | None = None
    source: str | None = None
    status: str | None = None
    current_stage: str | None = None


class MLflowModelsResponse(BaseModel):
    mlflow_tracking_uri: str
    registered_model_name: str
    versions: list[MLflowModelVersionSummary] = Field(default_factory=list)
