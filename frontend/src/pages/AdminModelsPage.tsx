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
      setMessage("Đã kích hoạt mô hình.");
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
    if (!window.confirm("Lưu trữ model này? File weights không bị xóa.")) {
      return;
    }
    setError(null);
    setMessage(null);
    setPromotion(null);
    setMlflowRegistration(null);
    try {
      await archiveModel(modelId);
      setMessage("Đã lưu trữ model.");
      await refreshModels();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không lưu trữ được model.");
    }
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Quản lý mô hình</h2>
          <p>Quản lý metadata, MLflow Tracking, Model Registry và active model.</p>
        </div>
        <div className="actions">
          <a
            className="button-link"
            href="http://localhost:5000"
            rel="noreferrer"
            target="_blank"
          >
            MLflow UI
          </a>
          <StatusBadge value={activeModel ? "active" : "none"} />
        </div>
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}
      {promotion && (
        <Message tone={promotion.promoted ? "success" : "warning"}>
          promoted={String(promotion.promoted)}; {promotion.reason}; active=
          {promotion.active_model.model_name}:{promotion.active_model.version}
        </Message>
      )}
      {mlflowRegistration && (
        <Message tone="success">
          MLflow run={mlflowRegistration.run_id}; model_uri=
          {mlflowRegistration.model_uri}; registered_model=
          {mlflowRegistration.registered_model_name};
          version={mlflowRegistration.mlflow_model_version ?? "-"}
        </Message>
      )}

      <div className="split-layout">
        <form className="panel form-grid" onSubmit={handleRegisterMlflow}>
          <h3 className="span-2">Đăng ký model lên MLflow</h3>
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
            {loading ? "Đang đăng ký..." : "Đăng ký model lên MLflow"}
          </button>
        </form>

        <div className="panel">
          <h3>Mô hình đang hoạt động</h3>
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
            <p className="muted">Chưa có active model.</p>
          )}
        </div>
      </div>

      <div className="split-layout">
        <form className="panel form-grid" onSubmit={handleRegisterCandidate}>
          <h3 className="span-2">Đăng ký candidate metadata</h3>
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

        <div className="panel">
          <h3>Model Registry</h3>
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
            <p className="muted">Chưa tải được thông tin MLflow Registry.</p>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>Models</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Version</th>
                <th>F1</th>
                <th>MLflow</th>
                <th>Status</th>
                <th>Action</th>
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
                      disabled={model.is_active || Boolean(model.archived_at)}
                      onClick={() => void handleArchive(model.model_id)}
                      type="button"
                    >
                      Lưu trữ
                    </button>
                  </td>
                </tr>
              ))}
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
