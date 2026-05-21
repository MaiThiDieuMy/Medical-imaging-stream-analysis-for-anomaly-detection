export type ProcessingStatus = "queued" | "processing" | "completed" | "failed";

export type UserRole = "user" | "admin";

export type UserPublic = {
  user_id: string;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
};

export type LoginCredentials = {
  username: string;
  password: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer" | string;
  user: UserPublic;
};

export type UserPayload = {
  username: string;
  password: string;
  full_name: string;
  role: UserRole;
};

export type UserUpdatePayload = {
  password?: string;
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
};

export type AnalysisResultItem = {
  label_name: string;
  probability: number;
  predicted_positive: boolean;
};

export type AnalyzeResponse = {
  status: ProcessingStatus | string;
  cache_hit: boolean;
  case_id: string | null;
  job_id: string | null;
  model_id: string;
  model_version: string;
  results: AnalysisResultItem[];
};

export type JobStatusResponse = {
  job_id: string;
  case_id: string;
  model_id: string;
  model_version: string;
  status: ProcessingStatus | string;
  worker_id: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type CaseStatusResponse = {
  case_id: string;
  status: ProcessingStatus | string;
  patient_id: string;
  job_id: string | null;
  job_status: ProcessingStatus | string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type CaseResultsResponse = {
  case_id: string;
  status: ProcessingStatus | string;
  model_id: string | null;
  model_version: string | null;
  results: AnalysisResultItem[];
};

export type PatientSummary = {
  patient_id: string;
  patient_code: string;
  full_name: string;
  gender: string;
  birth_year: number | null;
  department: string | null;
};

export type XRayImageSummary = {
  image_id: string;
  file_name: string;
  image_path: string;
  image_hash: string;
  file_format: string;
  uploaded_at: string;
};

export type AnalysisJobSummary = {
  job_id: string;
  status: string;
  model_id: string;
  model_version: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type CaseListItem = {
  case_id: string;
  status: string;
  patient_code: string;
  patient_name: string;
  uploaded_by: string | null;
  model_version: string | null;
  review_status: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type CaseDetailResponse = {
  case_id: string;
  status: string;
  note: string | null;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  patient: PatientSummary;
  image: XRayImageSummary | null;
  job: AnalysisJobSummary | null;
  model_version: string | null;
  review_status: string | null;
  review_note: string | null;
  results: AnalysisResultItem[];
};

export type AIModel = {
  model_id: string;
  model_name: string;
  version: string;
  model_path: string;
  accuracy: number | null;
  f1_score: number | null;
  precision_score: number | null;
  recall_score: number | null;
  is_active: boolean;
  created_at: string;
  archived_at: string | null;
  mlflow_run_id: string | null;
  mlflow_model_uri: string | null;
  mlflow_registered_model_name: string | null;
  mlflow_model_version: string | null;
};

export type ModelPayload = {
  model_name: string;
  version: string;
  model_path: string;
  accuracy: number | null;
  f1_score: number | null;
  precision_score: number | null;
  recall_score: number | null;
};

export type MLflowLocalCheckpointPayload = ModelPayload & {
  architecture: string;
  task_type: "multi_class";
};

export type MLflowRegisterResponse = {
  ai_model: AIModel;
  run_id: string;
  model_uri: string;
  registered_model_name: string;
  mlflow_model_version: string | null;
  mlflow_tracking_uri: string;
  mlflow_ui_url: string;
};

export type MLflowModelVersion = {
  name: string;
  version: string;
  run_id: string | null;
  source: string | null;
  status: string | null;
  current_stage: string | null;
};

export type MLflowModelsResponse = {
  mlflow_tracking_uri: string;
  registered_model_name: string;
  versions: MLflowModelVersion[];
};

export type PromoteModelResponse = {
  promoted: boolean;
  reason: string;
  candidate_model: AIModel;
  previous_active_model: AIModel | null;
  active_model: AIModel;
};

export type ReviewResultItem = {
  label_name: string;
  probability: number;
  predicted_positive: boolean;
};

export type ConfirmedLabelItem = {
  label_name: string;
  confirmed_positive: boolean;
};

export type CaseReview = {
  review_id: string;
  case_id: string;
  status: string;
  reason: string;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  note: string | null;
  analysis_results: ReviewResultItem[];
  confirmed_labels: ConfirmedLabelItem[];
};

export type LabelCorrection = {
  label_name: string;
  confirmed_positive: boolean;
};

export type TrainingReadySample = {
  review_id: string;
  case_id: string;
  status: string;
  confirmed_labels: ConfirmedLabelItem[];
};

export type RetrainingSummary = {
  min_confirmed_samples: number;
  pending_reviews: number;
  confirmed_reviews: number;
  corrected_reviews: number;
  training_ready_cases: number;
  should_trigger_retraining: boolean;
};

export type RetrainingCheckResponse = RetrainingSummary & {
  message: string;
};

export type ManifestExportResponse = {
  manifest_path: string;
  samples_count: number;
  message: string;
};

export type MonitoringActiveModel = {
  model_id: string;
  model_name: string;
  version: string;
  accuracy: number | null;
  f1_score: number | null;
  precision_score: number | null;
  recall_score: number | null;
  created_at: string;
};

export type MonitoringSummary = {
  backend_status: string;
  database_reachable: boolean;
  redis_broker_status: string;
  active_model: MonitoringActiveModel | null;
  total_cases: number;
  total_jobs_by_status: Record<string, number>;
  reviews_by_status: Record<string, number>;
  pending_reviews: number;
  training_ready_cases: number;
  metrics: Record<string, number>;
};

export type AnalyzeFormValues = {
  patient_code: string;
  full_name: string;
  gender: string;
  birth_year: string;
  department: string;
  note: string;
};
