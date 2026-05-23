import { useEffect, useState } from "react";
import {
  checkRetraining,
  confirmReview,
  correctReview,
  createDatasetManifest,
  exportRetrainingManifest,
  getRetrainingSummary,
  listDatasetManifests,
  listPendingReviews,
  listRetrainingJobs,
  triggerRetraining,
} from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import type {
  CaseReview,
  DatasetManifest,
  LabelCorrection,
  RetrainingJob,
  RetrainingSummary,
} from "../types/api";
import { compactId } from "../utils/format";

const demoLabels = ["No Finding", "Effusion", "Infiltration", "Atelectasis"];

type CorrectionState = Record<string, Record<string, boolean>>;

type ReviewMlopsPageProps = {
  isAdmin: boolean;
};

export function ReviewMlopsPage({ isAdmin }: ReviewMlopsPageProps) {
  const [reviews, setReviews] = useState<CaseReview[]>([]);
  const [summary, setSummary] = useState<RetrainingSummary | null>(null);
  const [jobs, setJobs] = useState<RetrainingJob[]>([]);
  const [manifests, setManifests] = useState<DatasetManifest[]>([]);
  const [corrections, setCorrections] = useState<CorrectionState>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const latestUnlockedManifest =
    summary?.latest_manifest &&
    !summary.latest_manifest.is_locked &&
    summary.latest_manifest.samples_count >= summary.min_confirmed_samples
      ? summary.latest_manifest
      : null;

  async function refreshData() {
    const pending = await listPendingReviews();
    const retrainingSummary = isAdmin ? await getRetrainingSummary() : null;
    const retrainingJobs = isAdmin ? await listRetrainingJobs() : [];
    const datasetManifests = isAdmin ? await listDatasetManifests() : [];
    setReviews(pending);
    setSummary(retrainingSummary);
    setJobs(retrainingJobs);
    setManifests(datasetManifests);
    setCorrections((current) => {
      const next = { ...current };
      for (const review of pending) {
        if (!next[review.review_id]) {
          const predictedLabel =
            review.analysis_results.find((result) => result.predicted_positive)
              ?.label_name ?? demoLabels[0];
          next[review.review_id] = Object.fromEntries(
            demoLabels.map((label) => [label, label === predictedLabel]),
          );
        }
      }
      return next;
    });
  }

  useEffect(() => {
    refreshData().catch((exc) =>
      setError(
        exc instanceof Error
          ? exc.message
          : "Không tải được danh sách cần duyệt.",
      ),
    );
  }, [isAdmin]);

  async function handleConfirm(reviewId: string) {
    setError(null);
    setMessage(null);
    try {
      await confirmReview(reviewId);
      setMessage("Đã xác nhận nhãn AI. Ca này được tính là training-ready.");
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không xác nhận được review.");
    }
  }

  async function handleCorrect(reviewId: string) {
    setError(null);
    setMessage(null);
    try {
      const labels: LabelCorrection[] = demoLabels.map((label) => ({
        label_name: label,
        confirmed_positive: Boolean(corrections[reviewId]?.[label]),
      }));
      await correctReview(reviewId, labels);
      setMessage("Đã lưu nhãn bác sĩ chọn. Ca này được tính là training-ready.");
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không lưu được nhãn đã chọn.");
    }
  }

  async function handleRetrainingCheck() {
    setError(null);
    setMessage(null);
    if (!isAdmin) {
      setMessage("Chỉ Quản trị viên được kiểm tra retraining.");
      return;
    }
    try {
      const result = await checkRetraining();
      setMessage(result.message);
      setSummary(result);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không kiểm tra được retraining.");
    }
  }

  async function handleCreateManifest() {
    setError(null);
    setMessage(null);
    if (!isAdmin) {
      setMessage("Chỉ Quản trị viên được tạo dataset manifest.");
      return;
    }
    try {
      const manifest = await createDatasetManifest();
      setMessage(
        `Đã tạo manifest ${compactId(manifest.manifest_id)} với ${manifest.samples_count} mẫu.`,
      );
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tạo được manifest.");
    }
  }

  async function handleExportManifest() {
    setError(null);
    setMessage(null);
    if (!isAdmin) {
      setMessage("Chỉ Quản trị viên được export retraining manifest.");
      return;
    }
    try {
      const result = await exportRetrainingManifest();
      setMessage(
        `${result.message} Samples=${result.samples_count}; path=${result.manifest_path}`,
      );
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không export được manifest.");
    }
  }

  async function handleTriggerRetraining() {
    setError(null);
    setMessage(null);
    if (!isAdmin) {
      setMessage("Chỉ Quản trị viên được bắt đầu retraining.");
      return;
    }
    try {
      const job = await triggerRetraining(latestUnlockedManifest?.manifest_id);
      setMessage(`Đã tạo retraining job ${compactId(job.retraining_job_id)}.`);
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không bắt đầu được retraining.");
    }
  }

  function selectCorrection(reviewId: string, label: string) {
    setCorrections((current) => ({
      ...current,
      [reviewId]: Object.fromEntries(
        demoLabels.map((candidate) => [candidate, candidate === label]),
      ),
    }));
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Duyệt ca cần xác nhận</h2>
          <p>
            Xác nhận hoặc sửa nhãn để tạo dữ liệu huấn luyện đáng tin cậy cho
            vòng đời MLOps.
          </p>
        </div>
        <StatusBadge value={summary?.should_trigger_retraining ?? false} />
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="panel mlops-readiness-panel">
        <div className="section-heading">
          <div>
            <h3>Retraining readiness</h3>
            <p className="muted">
              Chỉ case đã được doctor/admin confirmed hoặc corrected mới được
              dùng để tạo dataset manifest.
            </p>
          </div>
          <StatusBadge
            value={summary?.should_trigger_retraining ? "ready" : "collecting"}
          />
        </div>

        {!isAdmin ? (
          <p className="muted">
            Bác sĩ/KTV chỉ cần duyệt nhãn. Phần retraining dành cho Quản trị viên.
          </p>
        ) : summary ? (
          <>
            <div className="mlops-kpi-row">
              <ReadinessKpi
                label="Mẫu mới"
                value={`${summary.new_training_ready_cases}/${summary.min_confirmed_samples}`}
                tone={summary.should_trigger_retraining ? "success" : "neutral"}
              />
              <ReadinessKpi
                label="Tổng đã xác nhận"
                value={summary.training_ready_cases}
              />
              <ReadinessKpi
                label="Đã dùng train"
                value={summary.used_training_ready_cases}
              />
              <ReadinessKpi label="Chờ duyệt" value={summary.pending_reviews} />
              <ReadinessKpi label="Confirmed" value={summary.confirmed_reviews} />
              <ReadinessKpi label="Corrected" value={summary.corrected_reviews} />
              <ReadinessKpi
                label="Manifest mới nhất"
                value={
                  summary.latest_manifest
                    ? compactId(summary.latest_manifest.manifest_id)
                    : "-"
                }
                title={summary.latest_manifest?.manifest_id}
              />
              <ReadinessKpi
                label="Job mới nhất"
                value={
                  summary.latest_job
                    ? compactId(summary.latest_job.retraining_job_id)
                    : "-"
                }
                title={summary.latest_job?.retraining_job_id}
              />
            </div>

            <div className="mlops-workflow-grid">
              <div className="mlops-step-list">
                <WorkflowStep
                  number="1"
                  title="Duyệt nhãn"
                  state={
                    summary.training_ready_cases >= summary.min_confirmed_samples
                      ? "done"
                      : "active"
                  }
                />
                <WorkflowStep
                  number="2"
                  title="Tạo manifest"
                  state={summary.latest_manifest ? "done" : "pending"}
                />
                <WorkflowStep
                  number="3"
                  title="Fine-tune async"
                  state={summary.running_job ? "active" : "pending"}
                />
                <WorkflowStep
                  number="4"
                  title="Review candidate"
                  state={summary.latest_job?.candidate_model_id ? "done" : "pending"}
                />
              </div>

              <div className="label-distribution-card">
                <h4>Phân bố nhãn mới chưa retrain</h4>
                <div className="label-bars">
                  {Object.entries(summary.new_label_distribution).length === 0 ? (
                    <p className="muted">Chưa có mẫu mới chưa retrain.</p>
                  ) : (
                    Object.entries(summary.new_label_distribution).map(([label, count]) => (
                      <div className="label-bar-row" key={label}>
                        <span>{label}</span>
                        <div>
                          <strong>{count}</strong>
                          <i
                            style={{
                              width: `${Math.max(
                                10,
                                (count /
                                  Math.max(1, summary.new_training_ready_cases)) *
                                  100,
                              )}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="mlops-actions-grid">
              <ActionButton
                disabled={!isAdmin}
                label="Kiểm tra điều kiện"
                onClick={() => void handleRetrainingCheck()}
                title="Refresh số mẫu training-ready, phân bố nhãn, job và manifest mới nhất."
              />
              <ActionButton
                disabled={!isAdmin || !summary.should_trigger_retraining}
                label="Tạo manifest"
                onClick={() => void handleCreateManifest()}
                title="Tạo snapshot dataset versioned từ các case confirmed/corrected hiện tại."
              />
              <ActionButton
                disabled={!isAdmin}
                label="Xuất manifest"
                onClick={() => void handleExportManifest()}
                title="Export manifest JSON từ dữ liệu confirmed/corrected. Dùng để xem hoặc debug lineage."
              />
              <ActionButton
                primary
                disabled={!isAdmin || !summary.should_trigger_retraining}
                label={
                  summary.auto_start_retraining_job
                    ? "Auto retraining bật"
                    : "Bắt đầu retraining"
                }
                onClick={() => void handleTriggerRetraining()}
                title="Tạo retraining job, lock manifest, enqueue Celery fine-tune và log kết quả vào MLflow."
              />
            </div>
          </>
        ) : (
          <p className="muted">Chưa có summary.</p>
        )}
      </div>

      {isAdmin && jobs.length > 0 && (
        <div className="panel">
          <h3>Retraining jobs gần đây</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Status</th>
                  <th>Samples</th>
                  <th>Manifest</th>
                  <th>Candidate</th>
                  <th>F1</th>
                </tr>
              </thead>
              <tbody>
                {jobs.slice(0, 5).map((job) => (
                  <tr key={job.retraining_job_id}>
                    <td title={job.retraining_job_id}>
                      {compactId(job.retraining_job_id)}
                    </td>
                    <td>
                      <StatusBadge value={job.status} />
                    </td>
                    <td>
                      {job.training_samples_count}/{job.min_required_samples}
                    </td>
                    <td title={job.dataset_manifest_id ?? ""}>
                      {compactId(job.dataset_manifest_id)}
                    </td>
                    <td title={job.candidate_model_id ?? ""}>
                      {compactId(job.candidate_model_id)}
                    </td>
                    <td>{job.f1_score ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {isAdmin && manifests.length > 0 && (
        <div className="panel">
          <h3>Dataset manifests</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Manifest</th>
                  <th>Version</th>
                  <th>Samples</th>
                  <th>Locked</th>
                </tr>
              </thead>
              <tbody>
                {manifests.slice(0, 5).map((manifest) => (
                  <tr key={manifest.manifest_id}>
                    <td title={manifest.manifest_id}>
                      {compactId(manifest.manifest_id)}
                    </td>
                    <td>{manifest.version}</td>
                    <td>{manifest.samples_count}</td>
                    <td>{manifest.is_locked ? "Có" : "Chưa"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="review-list">
        {reviews.length === 0 ? (
          <div className="panel empty-state">
            <strong>Không có ca cần duyệt</strong>
            <p>
              Tất cả case hiện tại đã được xử lý hoặc chưa có case nào cần bác sĩ
              xác nhận.
            </p>
          </div>
        ) : (
          reviews.map((review) => (
            <article className="panel review-card" key={review.review_id}>
              <div className="review-header">
                <div>
                  <h3>Ca cần duyệt {compactId(review.case_id)}</h3>
                  <p>Review {compactId(review.review_id)}</p>
                </div>
                <StatusBadge value={review.status} />
              </div>
              <Message tone="warning">{review.reason}</Message>
              <ResultTable results={review.analysis_results} />
              <div className="decision-actions">
                <button
                  className="primary"
                  onClick={() => void handleConfirm(review.review_id)}
                  type="button"
                >
                  Xác nhận AI đúng
                </button>
                <span className="action-note">
                  Dùng khi bác sĩ đồng ý với toàn bộ nhãn AI trong bảng kết quả.
                </span>
              </div>
              <div className="correction-box">
                <h4>Gán lại nhãn đúng</h4>
                <div className="toggle-grid">
                  {demoLabels.map((label) => (
                    <label className="toggle-row" key={label}>
                      <input
                        checked={Boolean(corrections[review.review_id]?.[label])}
                        name={`review-${review.review_id}-correct-label`}
                        onChange={() => selectCorrection(review.review_id, label)}
                        type="radio"
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <button
                  onClick={() => void handleCorrect(review.review_id)}
                  type="button"
                >
                  Lưu nhãn bác sĩ chọn
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function ReadinessKpi({
  label,
  title,
  tone = "neutral",
  value,
}: {
  label: string;
  title?: string | null;
  tone?: "neutral" | "success";
  value: number | string;
}) {
  return (
    <div className={`readiness-kpi ${tone}`} title={title ?? undefined}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function WorkflowStep({
  number,
  state,
  title,
}: {
  number: string;
  state: "active" | "done" | "pending";
  title: string;
}) {
  return (
    <div className={`workflow-step ${state}`}>
      <span>{number}</span>
      <strong>{title}</strong>
    </div>
  );
}

function ActionButton({
  disabled,
  label,
  onClick,
  primary = false,
  title,
}: {
  disabled: boolean;
  label: string;
  onClick: () => void;
  primary?: boolean;
  title: string;
}) {
  return (
    <button
      className={primary ? "primary action-button" : "action-button"}
      disabled={disabled}
      onClick={onClick}
      title={title}
      type="button"
    >
      {label}
    </button>
  );
}
