import { useEffect, useMemo, useState } from "react";
import {
  checkRetraining,
  confirmReview,
  correctReview,
  exportRetrainingManifest,
  getCaseDetail,
  getCaseImage,
  getRetrainingSummary,
  listPendingReviews,
  listRetrainingJobs,
  listReviews,
  promoteIfBetter,
  startRetraining,
} from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import type {
  CaseDetailResponse,
  CaseReview,
  LabelCorrection,
  RetrainingJob,
  RetrainingSummary,
} from "../types/api";
import {
  compactId,
  formatDateTime,
  formatReviewReason,
} from "../utils/format";

const reviewLabels = ["Atelectasis", "Effusion", "Infiltration", "No Finding"];

type CorrectionState = Record<string, string>;
type NoteState = Record<string, string>;

type ReviewMlopsPageProps = {
  isAdmin: boolean;
};

export function ReviewMlopsPage({ isAdmin }: ReviewMlopsPageProps) {
  return isAdmin ? <AdminReviewMlopsPage /> : <DoctorReviewPage />;
}

function DoctorReviewPage() {
  const [reviews, setReviews] = useState<CaseReview[]>([]);
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const [selectedCase, setSelectedCase] = useState<CaseDetailResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [corrections, setCorrections] = useState<CorrectionState>({});
  const [notes, setNotes] = useState<NoteState>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedReview = useMemo(
    () => reviews.find((review) => review.review_id === selectedReviewId) ?? null,
    [reviews, selectedReviewId],
  );
  const pendingReviews = useMemo(
    () => reviews.filter((review) => review.status === "pending"),
    [reviews],
  );
  const completedReviews = useMemo(
    () => reviews.filter((review) => review.status !== "pending"),
    [reviews],
  );
  const selectedConfirmedLabel =
    selectedReview?.confirmed_labels.find((label) => label.confirmed_positive)
      ?.label_name ?? null;

  async function refreshReviews(nextSelectedId?: string | null) {
    setError(null);
    try {
      const visibleReviews = await listReviews();
      setReviews(visibleReviews);
      setCorrections((current) => {
        const next = { ...current };
        for (const review of visibleReviews) {
          next[review.review_id] = initialSelectedLabel(review);
        }
        return next;
      });
      setNotes((current) => {
        const next = { ...current };
        for (const review of visibleReviews) {
          next[review.review_id] = review.note ?? "";
        }
        return next;
      });
      const preferredId = nextSelectedId === undefined ? selectedReviewId : nextSelectedId;
      const targetId = preferredId ?? visibleReviews[0]?.review_id ?? null;
      setSelectedReviewId(
        visibleReviews.some((review) => review.review_id === targetId)
          ? targetId
          : null,
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tải được danh sách cần duyệt.");
    }
  }

  useEffect(() => {
    void refreshReviews();
  }, []);

  useEffect(() => {
    if (!selectedReview?.case_id) {
      setSelectedCase(null);
      setImageUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
      return;
    }

    const caseId = selectedReview.case_id;
    let cancelled = false;
    async function loadCase() {
      try {
        const detail = await getCaseDetail(caseId);
        const blob = await getCaseImage(caseId);
        if (cancelled) {
          return;
        }
        setSelectedCase(detail);
        const objectUrl = URL.createObjectURL(blob);
        setImageUrl((current) => {
          if (current) {
            URL.revokeObjectURL(current);
          }
          return objectUrl;
        });
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Không tải được ảnh ca cần duyệt.");
        }
      }
    }
    void loadCase();
    return () => {
      cancelled = true;
    };
  }, [selectedReview?.case_id]);

  async function handleConfirm(review: CaseReview) {
    setError(null);
    setMessage(null);
    try {
      const updated = await confirmReview(review.review_id, notes[review.review_id]);
      setMessage("Đã lưu xác nhận AI đúng cho ca này.");
      await refreshReviews(updated.review_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không xác nhận được review.");
    }
  }

  async function handleCorrect(review: CaseReview) {
    setError(null);
    setMessage(null);
    try {
      const selectedLabel = corrections[review.review_id] ?? initialSelectedLabel(review);
      const updated = await correctReview(
        review.review_id,
        correctionPayload(selectedLabel),
        notes[review.review_id],
      );
      setMessage("Đã lưu nhãn bác sĩ chọn cho ca này.");
      await refreshReviews(updated.review_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không lưu được nhãn đã chọn.");
    }
  }

  function setCorrection(reviewId: string, label: string) {
    setCorrections((current) => ({ ...current, [reviewId]: label }));
  }

  function setNote(reviewId: string, note: string) {
    setNotes((current) => ({ ...current, [reviewId]: note }));
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Duyệt/gán nhãn lại</h2>
          <p>
            Chỉ các ca đã được bác sĩ xác nhận hoặc gán nhãn lại mới được dùng
            cho dữ liệu huấn luyện.
          </p>
        </div>
        <StatusBadge value={pendingReviews.length > 0 ? "pending" : "clear"} />
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="review-workspace">
        <div className="panel">
          <div className="section-heading">
            <h3>Ca cần bác sĩ xem lại</h3>
            <span className="count-pill">{pendingReviews.length} ca</span>
          </div>
          <ReviewQueue
            reviews={pendingReviews}
            selectedReviewId={selectedReviewId}
            onSelect={setSelectedReviewId}
          />

          <div className="section-heading stacked-heading">
            <h3>Đã xác nhận/gán nhãn</h3>
            <span className="count-pill">{completedReviews.length} ca</span>
          </div>
          <ReviewQueue
            emptyText="Chưa có ca đã xác nhận hoặc gán nhãn lại."
            reviews={completedReviews}
            selectedReviewId={selectedReviewId}
            onSelect={setSelectedReviewId}
          />
        </div>

        <div className="panel review-detail-panel">
          {selectedReview ? (
            <>
              <div className="review-header">
                <div>
                  <h3>Ca {compactId(selectedReview.case_id)}</h3>
                  <p>Mã duyệt {compactId(selectedReview.review_id)}</p>
                </div>
                <StatusBadge value={selectedReview.status} />
              </div>
              {selectedReview.reason && (
                <Message tone="warning">
                  {formatReviewReason(selectedReview.reason)}
                </Message>
              )}

              {imageUrl ? (
                <div className="image-preview">
                  <img alt="Ảnh X-quang cần duyệt" src={imageUrl} />
                </div>
              ) : (
                <div className="empty-preview">Đang tải ảnh</div>
              )}

              {selectedCase && (
                <dl className="detail-list compact">
                  <div>
                    <dt>Bệnh nhân</dt>
                    <dd>
                      {selectedCase.patient.full_name} (
                      {selectedCase.patient.patient_code})
                    </dd>
                  </div>
                  <div>
                    <dt>Ngày tạo</dt>
                    <dd>{formatDateTime(selectedCase.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{selectedCase.model_version ?? "-"}</dd>
                  </div>
                  <div>
                    <dt>Ghi chú ca</dt>
                    <dd>{selectedCase.note ?? "-"}</dd>
                  </div>
                </dl>
              )}

              <ResultTable results={selectedReview.analysis_results} />

              {selectedReview.status !== "pending" && (
                <Message tone="info">
                  {selectedReview.status === "corrected"
                    ? "Nhãn đã gán lại"
                    : "Nhãn AI đã được xác nhận"}
                  : <strong>{selectedConfirmedLabel ?? "-"}</strong>. Có thể cập nhật
                  lại nhãn xác nhận nếu bác sĩ/KTV phát hiện cần chỉnh.
                </Message>
              )}

              <label className="note-field">
                Ghi chú chuyên môn
                <textarea
                  onChange={(event) => setNote(selectedReview.review_id, event.target.value)}
                  placeholder="Nhập nhận xét ngắn nếu cần"
                  rows={2}
                  value={notes[selectedReview.review_id] ?? ""}
                />
              </label>

              <div className="decision-actions">
                <button
                  className="primary"
                  onClick={() => void handleConfirm(selectedReview)}
                  type="button"
                >
                  {selectedReview.status === "pending"
                    ? "Xác nhận AI đúng"
                    : "Cập nhật xác nhận"}
                </button>
                <span className="action-note">
                  Dùng khi bác sĩ đồng ý với nhãn AI sau khi xem ảnh.
                </span>
              </div>

              <div className="correction-box">
                <h4>Chỉnh sửa nhãn xác nhận</h4>
                <div className="toggle-grid">
                  {reviewLabels.map((label) => (
                    <label className="toggle-row" key={label}>
                      <input
                        checked={(corrections[selectedReview.review_id] ?? reviewLabels[0]) === label}
                        name={`review-${selectedReview.review_id}-correct-label`}
                        onChange={() => setCorrection(selectedReview.review_id, label)}
                        type="radio"
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <button onClick={() => void handleCorrect(selectedReview)} type="button">
                  Lưu nhãn đã chỉnh sửa
                </button>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <strong>Chưa chọn ca</strong>
              <p>Chọn một ca trong danh sách để xem ảnh và duyệt nhãn.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function ReviewQueue({
  emptyText = "Không có ca cần duyệt.",
  onSelect,
  reviews,
  selectedReviewId,
}: {
  emptyText?: string;
  onSelect: (reviewId: string) => void;
  reviews: CaseReview[];
  selectedReviewId: string | null;
}) {
  return (
    <div className="review-queue">
      {reviews.map((review) => (
        <article
          className={`review-list-item ${
            review.review_id === selectedReviewId ? "active" : ""
          }`}
          key={review.review_id}
        >
          <div className="review-item-main">
            <div className="review-item-title">Ca {compactId(review.case_id)}</div>
            <div className="review-item-reason">
              {formatReviewReason(review.reason)}
            </div>
          </div>
          <div className="review-item-side">
            <StatusBadge value={review.status} />
            <button onClick={() => onSelect(review.review_id)} type="button">
              Xem chi tiết
            </button>
          </div>
        </article>
      ))}
      {reviews.length === 0 && (
        <div className="empty-state compact">
          <strong>{emptyText}</strong>
          <p>Các ca phù hợp sẽ xuất hiện tại đây.</p>
        </div>
      )}
    </div>
  );
}

function AdminReviewMlopsPage() {
  const [reviews, setReviews] = useState<CaseReview[]>([]);
  const [summary, setSummary] = useState<RetrainingSummary | null>(null);
  const [jobs, setJobs] = useState<RetrainingJob[]>([]);
  const [corrections, setCorrections] = useState<CorrectionState>({});
  const [forceStart, setForceStart] = useState(false);
  const [showAdvancedTools, setShowAdvancedTools] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshData() {
    const pending = await listPendingReviews();
    const retrainingSummary = await getRetrainingSummary();
    const retrainingJobs = await listRetrainingJobs();
    setReviews(pending);
    setSummary(retrainingSummary);
    setJobs(retrainingJobs);
    setCorrections((current) => {
      const next = { ...current };
      for (const review of pending) {
        if (!next[review.review_id]) {
          next[review.review_id] = initialSelectedLabel(review);
        }
      }
      return next;
    });
  }

  useEffect(() => {
    refreshData().catch((exc) =>
      setError(exc instanceof Error ? exc.message : "Không tải được danh sách cần duyệt."),
    );
  }, []);

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
      const selectedLabel = corrections[reviewId] ?? reviewLabels[0];
      await correctReview(reviewId, correctionPayload(selectedLabel));
      setMessage("Đã lưu nhãn bác sĩ chọn. Ca này được đưa vào retraining buffer.");
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không lưu được nhãn đã chọn.");
    }
  }

  async function handleRetrainingCheck() {
    setError(null);
    setMessage(null);
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
    try {
      const result = await exportRetrainingManifest();
      setMessage(
        `${result.message} Seed=${result.seed_count}; ca mới=${result.confirmed_count}; tổng=${result.total_train_count}; path=${result.manifest_path}`,
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không export được manifest.");
    }
  }

  async function handleTriggerRetraining() {
    setError(null);
    setMessage(null);
    try {
      const job = await startRetraining();
      setMessage(`Đã tạo fine-tune job ${compactId(job.retraining_job_id)}.`);
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không bắt đầu được fine-tune.");
    }
  }

  async function handleForceRetraining() {
    setError(null);
    setMessage(null);
    try {
      const job = await startRetraining({ force: forceStart });
      setMessage(`Đã tạo job kiểm thử pipeline ${compactId(job.retraining_job_id)}.`);
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tạo được job kiểm thử pipeline.");
    }
  }

  async function handlePromoteCandidate(modelId: string) {
    setError(null);
    setMessage(null);
    try {
      const result = await promoteIfBetter(modelId);
      setMessage(
        `${result.promoted ? "Đã chọn model ứng viên làm model hoạt động." : "Chưa chọn model ứng viên."} ${result.reason}`,
      );
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không chọn được model ứng viên.");
    }
  }

  function selectCorrection(reviewId: string, label: string) {
    setCorrections((current) => ({ ...current, [reviewId]: label }));
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Duyệt ca và MLOps</h2>
          <p>Quản trị viên theo dõi review, điều kiện fine-tune và model ứng viên.</p>
        </div>
        <StatusBadge value={summary?.should_trigger_retraining ?? false} />
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="panel">
        <div className="section-heading">
          <div>
            <h3>Điều kiện fine-tune</h3>
            <p className="muted">
              Chỉ các ca đã được bác sĩ xác nhận hoặc gán nhãn lại mới được dùng cho
              fine-tune. Dữ liệu AI thô không được tính.
            </p>
          </div>
          <div className="actions">
            <button onClick={() => void handleRetrainingCheck()} type="button">
              Kiểm tra điều kiện
            </button>
            <button onClick={() => void handleExportManifest()} type="button">
              Xuất manifest
            </button>
            <button
              className="primary"
              disabled={!summary?.should_trigger_retraining}
              onClick={() => void handleTriggerRetraining()}
              type="button"
            >
              Bắt đầu fine-tune
            </button>
          </div>
        </div>
        {summary ? (
          <div className="summary-grid">
            <SummaryItem
              label="Ngưỡng tối thiểu N ca"
              value={summary.min_confirmed_samples}
            />
            <SummaryItem label="Ca mới đã xác nhận/gán lại" value={summary.training_ready_cases} />
            <SummaryItem label="Ảnh seed cục bộ" value={summary.training_seed_count} />
            <SummaryItem
              label="Tổng ảnh fine-tune"
              value={summary.total_finetune_samples}
            />
            <SummaryItem label="Còn thiếu" value={summary.missing_confirmed_samples} />
            <SummaryItem
              label="Tự động tạo job"
              value={summary.retrain_auto_start ? "Bật" : "Tắt"}
            />
            <SummaryItem
              label="Evaluation set"
              value={
                summary.evaluation_set_available
                  ? `${summary.evaluation_set_sample_count} ảnh`
                  : "Thiếu"
              }
            />
            <SummaryItem
              label="Job gần nhất"
              value={summary.latest_job ? summary.latest_job.status : "Chưa có"}
            />
            <SummaryItem label="Chờ duyệt" value={summary.pending_reviews} />
            <SummaryItem label="Đã xác nhận" value={summary.confirmed_reviews} />
            <SummaryItem label="Đã sửa nhãn" value={summary.corrected_reviews} />
            <SummaryItem
              label="Có thể fine-tune"
              value={summary.should_trigger_retraining ? "Có" : "Chưa"}
            />
          </div>
        ) : (
          <p className="muted">Chưa có summary.</p>
        )}
        {summary && summary.missing_confirmed_samples > 0 && (
          <Message tone="info">
            Cần thêm {summary.missing_confirmed_samples} ca đã xác nhận/gán nhãn lại.
          </Message>
        )}
        {summary && (
          <Message tone="info">
            Training seed là dữ liệu gán nhãn sẵn trên hệ thống, dùng để hỗ trợ
            fine-tune nhưng không được tính vào ngưỡng N dữ liệu mới.
          </Message>
        )}
        {summary?.evaluation_warning && (
          <Message tone="warning">{summary.evaluation_warning}</Message>
        )}
        <div className="advanced-tools">
          <button
            className="ghost"
            onClick={() => setShowAdvancedTools((current) => !current)}
            type="button"
          >
            Công cụ kiểm thử pipeline
          </button>
          {showAdvancedTools && (
            <div className="advanced-tools-body">
              <p className="muted">
                Chỉ dùng để kiểm tra luồng kỹ thuật với ít dữ liệu, không dùng để
                đánh giá chất lượng model.
              </p>
              <label className="inline-checkbox">
                <input
                  checked={forceStart}
                  onChange={(event) => setForceStart(event.target.checked)}
                  type="checkbox"
                />
                Cho phép bỏ qua ngưỡng N cho kiểm thử
              </label>
              <button
                disabled={!forceStart}
                onClick={() => void handleForceRetraining()}
                type="button"
              >
                Tạo job kiểm thử
              </button>
            </div>
          )}
        </div>
      </div>

      {jobs.length > 0 && (
        <div className="panel">
          <h3>Fine-tune jobs gần đây</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Trạng thái</th>
                  <th>Mẫu</th>
                  <th>Bắt đầu</th>
                  <th>Kết thúc</th>
                  <th>F1</th>
                  <th>Model ứng viên</th>
                  <th>MLflow</th>
                  <th>Thao tác</th>
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
                    <td>{formatDateTime(job.started_at)}</td>
                    <td>{formatDateTime(job.finished_at)}</td>
                    <td>{job.f1_score ?? "-"}</td>
                    <td title={job.candidate_model_id ?? ""}>
                      {compactId(job.candidate_model_id)}
                    </td>
                    <td>
                      {job.mlflow_run_id ? (
                        <a
                          href={`http://localhost:5000/#/experiments/0/runs/${job.mlflow_run_id}`}
                          rel="noreferrer"
                          target="_blank"
                        >
                          run {compactId(job.mlflow_run_id)}
                        </a>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      {job.candidate_model_id ? (
                        <button
                          onClick={() => void handlePromoteCandidate(job.candidate_model_id!)}
                          type="button"
                        >
                          Chọn nếu tốt hơn
                        </button>
                      ) : (
                        "-"
                      )}
                    </td>
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
            <p>Tất cả ca hiện tại đã được xử lý hoặc chưa có ca nào cần xác nhận.</p>
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
              <Message tone="warning">{formatReviewReason(review.reason)}</Message>
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
                  Dùng khi đồng ý với toàn bộ nhãn AI trong bảng kết quả.
                </span>
              </div>
              <div className="correction-box">
                <h4>Gán lại nhãn đúng</h4>
                <div className="toggle-grid">
                  {reviewLabels.map((label) => (
                    <label className="toggle-row" key={label}>
                      <input
                        checked={(corrections[review.review_id] ?? reviewLabels[0]) === label}
                        name={`review-${review.review_id}-correct-label`}
                        onChange={() => selectCorrection(review.review_id, label)}
                        type="radio"
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <button onClick={() => void handleCorrect(review.review_id)} type="button">
                  Lưu nhãn đã chọn
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function initialSelectedLabel(review: CaseReview): string {
  return (
    review.confirmed_labels.find((label) => label.confirmed_positive)?.label_name ??
    review.analysis_results.find((result) => result.predicted_positive)?.label_name ??
    reviewLabels[0]
  );
}

function correctionPayload(selectedLabel: string): LabelCorrection[] {
  return reviewLabels.map((label) => ({
    label_name: label,
    confirmed_positive: label === selectedLabel,
  }));
}

function SummaryItem({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
