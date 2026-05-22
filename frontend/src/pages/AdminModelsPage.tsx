import { FormEvent, useEffect, useState } from "react";
import {
  activateModel,
  archiveModel,
  getActiveModel,
  listMlflowModels,
  listModels,
  mlflowPayloadFromForm,
  modelPayloadFromForm,
  promoteIfBetter,
  registerCandidate,
  registerLocalCheckpointToMlflow,
} from "../api/client";
import { Message } from "../components/Message";
import { MetricGrid } from "../components/MetricGrid";
import { StatusBadge } from "../components/StatusBadge";
import type {
  AIModel,
  MLflowModelsResponse,
  MLflowRegisterResponse,
  PromoteModelResponse,
} from "../types/api";
import { compactId } from "../utils/format";

export function AdminModelsPage() {
  const [models, setModels] = useState<AIModel[]>([]);
  const [activeModel, setActiveModel] = useState<AIModel | null>(null);
  const [mlflowModels, setMlflowModels] = useState<MLflowModelsResponse | null>(null);
  const [promotion, setPromotion] = useState<PromoteModelResponse | null>(null);
  const [mlflowRegistration, setMlflowRegistration] =
    useState<MLflowRegisterResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refreshModels() {
    const [modelList, active, registry] = await Promise.all([
      listModels(),
      getActiveModel().catch(() => null),
      listMlflowModels().catch(() => null),
    ]);
    setModels(modelList);
    setActiveModel(active);
    setMlflowModels(registry);
  }

  useEffect(() => {
    refreshModels().catch((exc) =>
      setError(exc instanceof Error ? exc.message : "Không tải được danh sách mô hình."),
    );
  }, []);

  async function handleRegisterCandidate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setPromotion(null);
    setMlflowRegistration(null);
    try {
      setLoading(true);
      await registerCandidate(modelPayloadFromForm(event.currentTarget));
      event.currentTarget.reset();
      setMessage("Đã đăng ký candidate model trong cơ sở dữ liệu.");
      await refreshModels();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không đăng ký được model.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegisterMlflow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setPromotion(null);
    setMlflowRegistration(null);
    try {
      setLoading(true);
      const result = await registerLocalCheckpointToMlflow(
        mlflowPayloadFromForm(event.currentTarget),
      );
      event.currentTarget.reset();
      setMlflowRegistration(result);
      setMessage("Đã log checkpoint và đăng ký model version lên MLflow.");
      await refreshModels();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không đăng ký được model lên MLflow.");
    } finally {
      setLoading(false);
    }
  }

  async function handleActivate(modelId: string) {
    setError(null);
    setMessage(null);
    setPromotion(null);
    setMlflowRegistration(null);
    try {
      await activateModel(modelId);
      setMessage(
        "Đã kích hoạt mô hình. Thay đổi này chỉ áp dụng cho các inference mới.",
      );
      await refreshModels();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không kích hoạt được mô hình.");
    }
  }

  async function handlePromote(modelId: string) {
    setError(null);
    setMessage(null);
    setMlflowRegistration(null);
    try {
      const result = await promoteIfBetter(modelId);
      setPromotion(result);
      await refreshModels();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không promote được mô hình.");
    }
  }

  async function handleArchive(modelId: string) {
    if (
      !window.confirm(
        "Ẩn model này khỏi danh sách sử dụng? File weights và lịch sử inference vẫn được giữ.",
      )
    ) {
      return;
    }
    setError(null);
    setMessage(null);
    setPromotion(null);
    setMlflowRegistration(null);
    try {
      await archiveModel(modelId);
      setMessage("Đã ẩn model. Historical results vẫn giữ nguyên model version cũ.");
      await refreshModels();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không ẩn được model.");
    }
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Mô hình AI</h2>
          <p>
            Quản lý active model, candidate model và liên kết MLflow. Thay đổi
            active model chỉ ảnh hưởng các ca inference mới.
          </p>
        </div>
        <div className="actions">
          <a
            className="button-link"
            href="http://localhost:5000"
            rel="noreferrer"
            target="_blank"
          >
            Mở MLflow
          </a>
          <StatusBadge value={activeModel ? "active" : "none"} />
        </div>
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}
      {promotion && (
        <Message tone={promotion.promoted ? "success" : "warning"}>
          {promotion.promoted ? "Đã promote model." : "Chưa promote model."}{" "}
          {promotion.reason} Active model: {promotion.active_model.model_name}:
          {promotion.active_model.version}
        </Message>
      )}
      {mlflowRegistration && (
        <Message tone="success">
          MLflow run={mlflowRegistration.run_id}; model_uri=
          {mlflowRegistration.model_uri}; registered_model=
          {mlflowRegistration.registered_model_name}; version=
          {mlflowRegistration.mlflow_model_version ?? "-"}
        </Message>
      )}

      <div className="admin-grid">
        <div className="panel">
          <div className="section-heading">
            <div>
              <h3>Active model</h3>
              <p className="muted">Model đang dùng cho các ca inference mới.</p>
            </div>
            <StatusBadge value={activeModel ? "active" : "missing"} />
          </div>
          {activeModel ? (
            <>
              <dl className="detail-list">
                <div>
                  <dt>Name</dt>
                  <dd>{activeModel.model_name}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{activeModel.version}</dd>
                </div>
                <div>
                  <dt>Model ID</dt>
                  <dd title={activeModel.model_id}>{compactId(activeModel.model_id)}</dd>
                </div>
                <div>
                  <dt>MLflow run</dt>
                  <dd title={activeModel.mlflow_run_id ?? ""}>
                    {compactId(activeModel.mlflow_run_id)}
                  </dd>
                </div>
                <div>
                  <dt>Registry version</dt>
                  <dd>{activeModel.mlflow_model_version ?? "-"}</dd>
                </div>
              </dl>
              <MetricGrid
                metrics={{
                  accuracy: activeModel.accuracy,
                  f1_score: activeModel.f1_score,
                  precision_score: activeModel.precision_score,
                  recall_score: activeModel.recall_score,
                }}
              />
            </>
          ) : (
            <div className="empty-state compact">
              <strong>Chưa có active model</strong>
              <p>Seed demo model hoặc kích hoạt một candidate model trước khi phân tích ảnh.</p>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <h3>MLflow Registry</h3>
              <p className="muted">Nguồn theo dõi run và model version.</p>
            </div>
            <StatusBadge value={mlflowModels ? "connected" : "unavailable"} />
          </div>
          {mlflowModels ? (
            <dl className="detail-list">
              <div>
                <dt>Registered Model</dt>
                <dd>{mlflowModels.registered_model_name}</dd>
              </div>
              <div>
                <dt>Tracking URI</dt>
                <dd>{mlflowModels.mlflow_tracking_uri}</dd>
              </div>
              <div>
                <dt>Versions</dt>
                <dd>{mlflowModels.versions.length}</dd>
              </div>
            </dl>
          ) : (
            <div className="empty-state compact">
              <strong>Chưa tải được MLflow Registry</strong>
              <p>Kiểm tra MLflow service tại cổng 5000.</p>
            </div>
          )}
        </div>
      </div>

      <div className="split-layout">
        <form className="panel form-grid" onSubmit={handleRegisterMlflow}>
          <div className="form-section span-2">
            <span className="step-badge">1</span>
            <div>
              <h3>Đăng ký checkpoint lên MLflow</h3>
              <p className="muted">Log checkpoint, metric và tạo model version trong MLflow.</p>
            </div>
          </div>
          <label>
            Model name
            <input defaultValue="chest-xray-mobilenetv3-small" name="model_name" required />
          </label>
          <label>
            Version
            <input defaultValue="kaggle-best-v1" maxLength={20} name="version" required />
          </label>
          <label className="span-2">
            Model path
            <input
              defaultValue="/app/artifacts/models/best_model.pth"
              name="model_path"
              required
            />
          </label>
          <label>
            Architecture
            <input defaultValue="mobilenet_v3_small" name="architecture" required />
          </label>
          <label>
            Task type
            <input defaultValue="multi_class" disabled />
          </label>
          <MetricInputs />
          <button className="primary span-2" disabled={loading} type="submit">
            {loading ? "Đang đăng ký..." : "Đăng ký checkpoint lên MLflow"}
          </button>
        </form>

        <form className="panel form-grid" onSubmit={handleRegisterCandidate}>
          <div className="form-section span-2">
            <span className="step-badge">2</span>
            <div>
              <h3>Đăng ký candidate metadata</h3>
              <p className="muted">Tạo candidate model trong database khi đã có checkpoint sẵn.</p>
            </div>
          </div>
          <label>
            Model name
            <input name="model_name" required />
          </label>
          <label>
            Version
            <input maxLength={20} name="version" required />
          </label>
          <label className="span-2">
            Model path
            <input name="model_path" required />
          </label>
          <MetricInputs />
          <button className="primary span-2" disabled={loading} type="submit">
            {loading ? "Đang lưu..." : "Đăng ký candidate"}
          </button>
        </form>
      </div>

      <div className="panel">
        <div className="section-heading">
          <div>
            <h3>Model Registry trong app</h3>
            <p className="muted">
              Kích hoạt hoặc promote model chỉ ảnh hưởng các inference mới.
            </p>
          </div>
          <span className="count-pill">{models.length} models</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Version</th>
                <th>F1</th>
                <th>MLflow</th>
                <th>Status</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.model_id}>
                  <td>
                    <span>{model.model_name}</span>
                    <small title={model.model_id}>{compactId(model.model_id)}</small>
                    <small>{model.model_path}</small>
                  </td>
                  <td>{model.version}</td>
                  <td>{model.f1_score ?? "-"}</td>
                  <td>
                    {model.mlflow_run_id ? (
                      <>
                        <span title={model.mlflow_run_id}>
                          run {compactId(model.mlflow_run_id)}
                        </span>
                        <small>
                          {model.mlflow_registered_model_name ?? "-"} v
                          {model.mlflow_model_version ?? "-"}
                        </small>
                      </>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>
                    <StatusBadge
                      value={
                        model.archived_at
                          ? "archived"
                          : model.is_active
                            ? "active"
                            : "inactive"
                      }
                    />
                  </td>
                  <td className="actions">
                    <button
                      disabled={model.is_active || Boolean(model.archived_at)}
                      onClick={() => void handleActivate(model.model_id)}
                      type="button"
                    >
                      Kích hoạt
                    </button>
                    <button
                      disabled={model.is_active || Boolean(model.archived_at)}
                      onClick={() => void handlePromote(model.model_id)}
                      type="button"
                    >
                      Promote
                    </button>
                    <button
                      className="danger"
                      disabled={model.is_active || Boolean(model.archived_at)}
                      onClick={() => void handleArchive(model.model_id)}
                      type="button"
                    >
                      Ẩn model
                    </button>
                  </td>
                </tr>
              ))}
              {models.length === 0 && (
                <tr>
                  <td colSpan={6}>Chưa có model metadata.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function MetricInputs() {
  return (
    <>
      <label>
        Accuracy
        <input max="1" min="0" name="accuracy" step="0.0001" type="number" />
      </label>
      <label>
        F1 score
        <input max="1" min="0" name="f1_score" step="0.0001" type="number" />
      </label>
      <label>
        Precision
        <input
          max="1"
          min="0"
          name="precision_score"
          step="0.0001"
          type="number"
        />
      </label>
      <label>
        Recall
        <input max="1" min="0" name="recall_score" step="0.0001" type="number" />
      </label>
    </>
  );
}
