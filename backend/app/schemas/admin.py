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
    promotion_metric: str
    candidate_metric: float | None = None
    active_metric: float | None = None
    promotion_recommended: bool
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
        if sum(1 for item in self.labels if item.confirmed_positive) != 1:
            raise ValueError("Exactly one label must be selected for multi-class data")
        return self


class TrainingReadySample(BaseModel):
    review_id: UUID
    case_id: UUID
    image_path: str
    label_name: str
    label_index: int
    review_status: str
    reviewed_by: UUID | None = None
    created_at: datetime
    confirmed_labels: list[ConfirmedLabelItem]


class RetrainingJobResponse(BaseModel):
    retraining_job_id: UUID
    status: str
    trigger_type: str
    base_model_id: UUID
    candidate_model_id: UUID | None = None
    manifest_path: str | None = None
    output_model_path: str | None = None
    mlflow_run_id: str | None = None
    mlflow_model_uri: str | None = None
    training_samples_count: int
    min_required_samples: int
    accuracy: float | None = None
    precision_score: float | None = None
    recall_score: float | None = None
    f1_score: float | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    triggered_by_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class RetrainingStartRequest(BaseModel):
    force: bool = False
    epochs: int | None = Field(default=None, ge=1, le=100)
    min_samples: int | None = Field(default=None, ge=1, le=100000)


class RetrainingSummaryResponse(BaseModel):
    min_confirmed_samples: int
    pending_reviews: int
    confirmed_reviews: int
    corrected_reviews: int
    training_ready_cases: int
    training_seed_enabled: bool
    training_seed_dir: str
    training_seed_count: int
    total_finetune_samples: int
    finetune_per_class_count: dict[str, int]
    missing_confirmed_samples: int
    should_trigger_retraining: bool
    retrain_auto_start: bool
    evaluation_set_available: bool
    evaluation_set_sample_count: int
    evaluation_set_dir: str
    evaluation_warning: str | None = None
    running_job: RetrainingJobResponse | None = None
    latest_job: RetrainingJobResponse | None = None


class RetrainingCheckResponse(RetrainingSummaryResponse):
    message: str


class ManifestExportResponse(BaseModel):
    manifest_path: str
    samples_count: int
    seed_count: int = 0
    confirmed_count: int = 0
    total_train_count: int = 0
    per_class_count: dict[str, int] = Field(default_factory=dict)
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
