import type {
  AIModel,
  AnalyzeFormValues,
  AnalyzeResponse,
  CaseDetailResponse,
  CaseListItem,
  CaseResultsResponse,
  CaseReview,
  CaseStatusResponse,
  JobStatusResponse,
  LabelCorrection,
  LoginCredentials,
  LoginResponse,
  MLflowLocalCheckpointPayload,
  MLflowModelsResponse,
  MLflowRegisterResponse,
  MonitoringSummary,
  ModelPayload,
  ManifestExportResponse,
  PromoteModelResponse,
  RetrainingCheckResponse,
  RetrainingSummary,
  TrainingReadySample,
  UserPayload,
  UserPublic,
  UserUpdatePayload,
} from "../types/api";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const API_PREFIX = "/api/v1";
const TOKEN_STORAGE_KEY = "xray_ai_access_token";

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  let body: BodyInit | undefined;
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...options,
    headers,
    body,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return (await response.json()) as T;
}

async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const { body: _body, ...fetchOptions } = options;
  const headers = new Headers(options.headers);
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...fetchOptions,
    headers,
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.blob();
}

async function requestText(path: string, options: RequestOptions = {}): Promise<string> {
  const { body: _body, ...fetchOptions } = options;
  const headers = new Headers(options.headers);
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...fetchOptions,
    headers,
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.text();
}

export function getAccessToken(): string | null {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setAccessToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearAccessToken(): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) => {
          if (typeof item === "object" && item !== null && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return String(item);
        })
        .join("; ");
    }
    return `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

function numberOrNull(value: string): number | null {
  if (value.trim() === "") {
    return null;
  }
  return Number(value);
}

export async function login(
  credentials: LoginCredentials,
): Promise<LoginResponse> {
  const response = await requestJson<LoginResponse>("/auth/login", {
    method: "POST",
    body: credentials,
  });
  setAccessToken(response.access_token);
  return response;
}

export function getMe(): Promise<UserPublic> {
  return requestJson<UserPublic>("/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await requestJson<{ status: string }>("/auth/logout", { method: "POST" });
  } finally {
    clearAccessToken();
  }
}

export function analyzeImage(
  values: AnalyzeFormValues,
  image: File,
): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("patient_code", values.patient_code);
  formData.append("full_name", values.full_name);
  formData.append("gender", values.gender);
  if (values.birth_year.trim()) {
    formData.append("birth_year", values.birth_year);
  }
  if (values.department.trim()) {
    formData.append("department", values.department);
  }
  if (values.note.trim()) {
    formData.append("note", values.note);
  }
  formData.append("image", image);

  return requestJson<AnalyzeResponse>("/analyze", {
    method: "POST",
    body: formData,
  });
}

export function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return requestJson<JobStatusResponse>(`/jobs/${jobId}/status`);
}

export function getCaseStatus(caseId: string): Promise<CaseStatusResponse> {
  return requestJson<CaseStatusResponse>(`/cases/${caseId}/status`);
}

export function getCaseResults(caseId: string): Promise<CaseResultsResponse> {
  return requestJson<CaseResultsResponse>(`/cases/${caseId}/results`);
}

export function listCases(): Promise<CaseListItem[]> {
  return requestJson<CaseListItem[]>("/cases");
}

export function listMyCases(): Promise<CaseListItem[]> {
  return requestJson<CaseListItem[]>("/cases/my");
}

export function getCaseDetail(caseId: string): Promise<CaseDetailResponse> {
  return requestJson<CaseDetailResponse>(`/cases/${caseId}`);
}

export function getCaseImage(caseId: string): Promise<Blob> {
  return requestBlob(`/cases/${caseId}/image`);
}

export function getCaseReportHtml(caseId: string): Promise<string> {
  return requestText(`/cases/${caseId}/report`);
}

export function archiveCase(caseId: string): Promise<CaseDetailResponse> {
  return requestJson<CaseDetailResponse>(`/cases/${caseId}/archive`, {
    method: "POST",
  });
}

export function listModels(): Promise<AIModel[]> {
  return requestJson<AIModel[]>("/admin/models");
}

export function getActiveModel(): Promise<AIModel> {
  return requestJson<AIModel>("/admin/models/active");
}

export function getModel(modelId: string): Promise<AIModel> {
  return requestJson<AIModel>(`/admin/models/${modelId}`);
}

export function createModel(payload: ModelPayload): Promise<AIModel> {
  return requestJson<AIModel>("/admin/models", {
    method: "POST",
    body: { ...payload, is_active: false },
  });
}

export function activateModel(modelId: string): Promise<AIModel> {
  return requestJson<AIModel>(`/admin/models/${modelId}/activate`, {
    method: "POST",
  });
}

export function archiveModel(modelId: string): Promise<AIModel> {
  return requestJson<AIModel>(`/admin/models/${modelId}/archive`, {
    method: "POST",
  });
}

export function registerCandidate(payload: ModelPayload): Promise<AIModel> {
  return requestJson<AIModel>("/admin/mlops/models/register-candidate", {
    method: "POST",
    body: payload,
  });
}

export function promoteIfBetter(modelId: string): Promise<PromoteModelResponse> {
  return requestJson<PromoteModelResponse>(
    `/admin/mlops/models/${modelId}/promote-if-better`,
    { method: "POST" },
  );
}

export function registerLocalCheckpointToMlflow(
  payload: MLflowLocalCheckpointPayload,
): Promise<MLflowRegisterResponse> {
  return requestJson<MLflowRegisterResponse>(
    "/admin/mlops/mlflow/register-local-checkpoint",
    {
      method: "POST",
      body: payload,
    },
  );
}

export function listMlflowModels(): Promise<MLflowModelsResponse> {
  return requestJson<MLflowModelsResponse>("/admin/mlops/mlflow/models");
}

export function listPendingReviews(): Promise<CaseReview[]> {
  return requestJson<CaseReview[]>("/admin/reviews/pending");
}

export function getReview(reviewId: string): Promise<CaseReview> {
  return requestJson<CaseReview>(`/admin/reviews/${reviewId}`);
}

export function confirmReview(reviewId: string): Promise<CaseReview> {
  return requestJson<CaseReview>(`/admin/reviews/${reviewId}/confirm`, {
    method: "POST",
    body: {},
  });
}

export function correctReview(
  reviewId: string,
  labels: LabelCorrection[],
): Promise<CaseReview> {
  return requestJson<CaseReview>(`/admin/reviews/${reviewId}/correct`, {
    method: "POST",
    body: { labels },
  });
}

export function getRetrainingSummary(): Promise<RetrainingSummary> {
  return requestJson<RetrainingSummary>("/admin/mlops/retraining/summary");
}

export function getRetrainingSamples(): Promise<TrainingReadySample[]> {
  return requestJson<TrainingReadySample[]>("/admin/mlops/retraining/samples");
}

export function checkRetraining(): Promise<RetrainingCheckResponse> {
  return requestJson<RetrainingCheckResponse>("/admin/mlops/retraining/check", {
    method: "POST",
  });
}

export function exportRetrainingManifest(): Promise<ManifestExportResponse> {
  return requestJson<ManifestExportResponse>(
    "/admin/mlops/retraining/export-manifest",
    { method: "POST" },
  );
}

export function getMonitoringSummary(): Promise<MonitoringSummary> {
  return requestJson<MonitoringSummary>("/monitoring/summary");
}

export function listUsers(): Promise<UserPublic[]> {
  return requestJson<UserPublic[]>("/admin/users");
}

export function getUser(userId: string): Promise<UserPublic> {
  return requestJson<UserPublic>(`/admin/users/${userId}`);
}

export function createUser(payload: UserPayload): Promise<UserPublic> {
  return requestJson<UserPublic>("/admin/users", {
    method: "POST",
    body: payload,
  });
}

export function updateUser(
  userId: string,
  payload: UserUpdatePayload,
): Promise<UserPublic> {
  return requestJson<UserPublic>(`/admin/users/${userId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function modelPayloadFromForm(form: HTMLFormElement): ModelPayload {
  const formData = new FormData(form);
  return {
    model_name: String(formData.get("model_name") ?? ""),
    version: String(formData.get("version") ?? ""),
    model_path: String(formData.get("model_path") ?? ""),
    accuracy: numberOrNull(String(formData.get("accuracy") ?? "")),
    f1_score: numberOrNull(String(formData.get("f1_score") ?? "")),
    precision_score: numberOrNull(String(formData.get("precision_score") ?? "")),
    recall_score: numberOrNull(String(formData.get("recall_score") ?? "")),
  };
}

export function mlflowPayloadFromForm(
  form: HTMLFormElement,
): MLflowLocalCheckpointPayload {
  const base = modelPayloadFromForm(form);
  const formData = new FormData(form);
  return {
    ...base,
    architecture: String(formData.get("architecture") ?? "mobilenet_v3_small"),
    task_type: "multi_class",
  };
}
