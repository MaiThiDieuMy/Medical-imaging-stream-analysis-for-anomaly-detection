import { useEffect, useState } from "react";
import {
  checkRetraining,
  confirmReview,
  correctReview,
  exportRetrainingManifest,
  getRetrainingSummary,
  listPendingReviews,
} from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import type { CaseReview, LabelCorrection, RetrainingSummary } from "../types/api";
import { compactId } from "../utils/format";

const demoLabels = ["No Finding", "Effusion", "Infiltration", "Atelectasis"];

type CorrectionState = Record<string, Record<string, boolean>>;

type ReviewMlopsPageProps = {
  isAdmin: boolean;
};

export function ReviewMlopsPage({ isAdmin }: ReviewMlopsPageProps) {
  const [reviews, setReviews] = useState<CaseReview[]>([]);
  const [summary, setSummary] = useState<RetrainingSummary | null>(null);
  const [corrections, setCorrections] = useState<CorrectionState>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshData() {
    const pending = await listPendingReviews();
    const retrainingSummary = isAdmin ? await getRetrainingSummary() : null;
    setReviews(pending);
    setSummary(retrainingSummary);
    setCorrections((current) => {
      const next = { ...current };
      for (const review of pending) {
        if (!next[review.review_id]) {
          next[review.review_id] = Object.fromEntries(
            demoLabels.map((label) => {
              const predicted = review.analysis_results.find(
                (result) => result.label_name === label,
              )?.predicted_positive;
              return [label, Boolean(predicted)];
            }),
          );
        }
      }
      return next;
    });
  }

  useEffect(() => {
    refreshData().catch((exc) =>
      setError(exc instanceof Error ? exc.message : "Không tải được review."),
    );
  }, [isAdmin]);

  async function handleConfirm(reviewId: string) {
    setError(null);
    setMessage(null);
    try {
      await confirmReview(reviewId);
      setMessage("Đã confirm AI labels. Case này đã vào retraining buffer.");
      await refreshData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không confirm được review.");
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
      setMessage("Đã lưu corrected labels. Case này đã vào retraining buffer.");
      await refreshData();
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "Không lưu được corrected labels.",
      );
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

  function setCorrection(reviewId: string, label: string, value: boolean) {
    setCorrections((current) => ({
      ...current,
      [reviewId]: {
        ...(current[reviewId] ?? {}),
        [label]: value,
      },
    }));
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Duyệt/gán nhãn lại</h2>
          <p>Pending reviews chưa training-ready cho tới khi được confirm/correct.</p>
        </div>
        <StatusBadge value={summary?.should_trigger_retraining ?? false} />
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="panel">
        <div className="section-heading">
          <h3>Retraining summary</h3>
          <button
            disabled={!isAdmin}
            onClick={() => void handleRetrainingCheck()}
            type="button"
          >
            Check retraining
          </button>
          <button
            disabled={!isAdmin}
            onClick={() => void handleExportManifest()}
            type="button"
          >
            Export manifest
          </button>
        </div>
        {!isAdmin ? (
          <p className="muted">
            Pending reviews chưa training-ready cho tới khi được doctor/admin
            confirm/correct. Chỉ Quản trị viên xem được retraining summary.
          </p>
        ) : summary ? (
          <div className="summary-grid">
            <SummaryItem label="Min samples" value={summary.min_confirmed_samples} />
            <SummaryItem label="Pending" value={summary.pending_reviews} />
            <SummaryItem label="Confirmed" value={summary.confirmed_reviews} />
            <SummaryItem label="Corrected" value={summary.corrected_reviews} />
            <SummaryItem label="Training-ready" value={summary.training_ready_cases} />
            <SummaryItem
              label="Should trigger"
              value={summary.should_trigger_retraining ? "yes" : "no"}
            />
          </div>
        ) : (
          <p className="muted">Chưa có summary.</p>
        )}
      </div>

      <div className="review-list">
        {reviews.length === 0 ? (
          <div className="panel">
            <p className="muted">Không có pending review.</p>
          </div>
        ) : (
          reviews.map((review) => (
            <article className="panel review-card" key={review.review_id}>
              <div className="review-header">
                <div>
                  <h3>Review {compactId(review.review_id)}</h3>
                  <p>Case {compactId(review.case_id)}</p>
                </div>
                <StatusBadge value={review.status} />
              </div>
              <Message tone="warning">{review.reason}</Message>
              <ResultTable results={review.analysis_results} />
              <div className="review-actions">
                <button
                  className="primary"
                  onClick={() => void handleConfirm(review.review_id)}
                  type="button"
                >
                  Confirm AI labels
                </button>
              </div>
              <div className="correction-box">
                <h4>Correct labels</h4>
                <div className="toggle-grid">
                  {demoLabels.map((label) => (
                    <label className="toggle-row" key={label}>
                      <input
                        checked={Boolean(corrections[review.review_id]?.[label])}
                        onChange={(event) =>
                          setCorrection(review.review_id, label, event.target.checked)
                        }
                        type="checkbox"
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <button
                  onClick={() => void handleCorrect(review.review_id)}
                  type="button"
                >
                  Submit corrected labels
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
