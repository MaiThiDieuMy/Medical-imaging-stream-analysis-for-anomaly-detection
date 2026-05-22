import { useEffect, useState } from "react";
import {
  checkRetraining,
  confirmReview,
  correctReview,
  exportRetrainingManifest,
  getRetrainingSummary,
  listPendingReviews,
  listRetrainingJobs,
  triggerRetraining,
} from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import type {
  CaseReview,
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
  const [corrections, setCorrections] = useState<CorrectionState>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshData() {
    const pending = await listPendingReviews();
    const retrainingSummary = isAdmin ? await getRetrainingSummary() : null;
    const retrainingJobs = isAdmin ? await listRetrainingJobs() : [];
    setReviews(pending);
    setSummary(retrainingSummary);
    setJobs(retrainingJobs);
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
      setError(exc instanceof Error ? exc.message : "Không tải được danh sách cần duyệt."),
    );
  }, [isAdmin]);

  async function handleConfirm(reviewId: string) {
    setError(null);
    setMessage(null);
    try {
      await confirmReview(reviewId);
      setMessage("Đã xác nhận AI đúng. Ca này được đưa vào retraining buffer.");
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
      setMessage("Đã lưu nhãn bác sĩ chọn. Ca này được đưa vào retraining buffer.");
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không lưu được nhãn đã chọn.");
    }
  }

  async function handleRetrainingCheck() {
    setError(null);
    setMessage(null);
    if (!isAdmin) {
      setMessage("Chỉ Quản trị viên được kiểm tra retraining summary.");
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
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không export được manifest.");
    }
  }

  async function handleTriggerRetraining() {
    setError(null);
    setMessage(null);
    if (!isAdmin) {
      setMessage("Chỉ Quản trị viên được trigger retraining.");
      return;
    }
    try {
      const job = await triggerRetraining();
      setMessage(`Đã tạo retraining job ${compactId(job.retraining_job_id)}.`);
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không trigger được retraining.");
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
            Xem các ca AI chưa đủ chắc chắn, xác nhận nếu AI đúng hoặc gán lại
            nhãn để tạo dữ liệu huấn luyện đáng tin cậy.
          </p>
        </div>
        <StatusBadge value={summary?.should_trigger_retraining ?? false} />
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="panel">
        <div className="section-heading">
          <div>
            <h3>Retraining readiness</h3>
            <p className="muted">
              Chỉ các ca đã được xác nhận hoặc sửa nhãn mới được tính là
              training-ready.
            </p>
          </div>
          <div className="actions">
            <button
              disabled={!isAdmin}
              onClick={() => void handleRetrainingCheck()}
              type="button"
            >
              Kiểm tra điều kiện
            </button>
            <button
              disabled={!isAdmin}
              onClick={() => void handleExportManifest()}
              type="button"
            >
              Xuất manifest
            </button>
            <button
              className="primary"
              disabled={!isAdmin || !summary?.should_trigger_retraining}
              onClick={() => void handleTriggerRetraining()}
              type="button"
            >
              Bắt đầu retraining
            </button>
          </div>
        </div>
        {!isAdmin ? (
          <p className="muted">
            Bác sĩ/KTV chỉ cần duyệt nhãn. Phần retraining summary dành cho
            Quản trị viên.
          </p>
        ) : summary ? (
          <div className="summary-grid">
            <SummaryItem label="Tối thiểu" value={summary.min_confirmed_samples} />
            <SummaryItem label="Chờ duyệt" value={summary.pending_reviews} />
            <SummaryItem label="Đã xác nhận" value={summary.confirmed_reviews} />
            <SummaryItem label="Đã sửa nhãn" value={summary.corrected_reviews} />
            <SummaryItem label="Training-ready" value={summary.training_ready_cases} />
            <SummaryItem
              label="Có thể train"
              value={summary.should_trigger_retraining ? "Có" : "Chưa"}
            />
            <SummaryItem
              label="Job đang chạy"
              value={
                summary.running_job
                  ? compactId(summary.running_job.retraining_job_id)
                  : "-"
              }
            />
            <SummaryItem
              label="Job mới nhất"
              value={
                summary.latest_job
                  ? compactId(summary.latest_job.retraining_job_id)
                  : "-"
              }
            />
          </div>
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

      <div className="review-list">
        {reviews.length === 0 ? (
          <div className="panel empty-state">
            <strong>Không có ca cần duyệt</strong>
            <p>Tất cả ca hiện tại đã được xử lý hoặc chưa có ca nào cần bác sĩ xác nhận.</p>
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

function SummaryItem({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
