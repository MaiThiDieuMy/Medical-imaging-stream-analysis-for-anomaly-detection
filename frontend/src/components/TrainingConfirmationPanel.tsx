import { useEffect, useMemo, useState } from "react";
import {
  confirmCaseResult,
  correctCaseLabels,
  getCaseReviewStatus,
} from "../api/client";
import type {
  AnalysisResultItem,
  CaseReviewStatusResponse,
  LabelCorrection,
} from "../types/api";
import { compactId } from "../utils/format";
import { Message } from "./Message";
import { StatusBadge } from "./StatusBadge";

const demoLabels = ["No Finding", "Effusion", "Infiltration", "Atelectasis"];

type TrainingConfirmationPanelProps = {
  caseId: string;
  caseStatus: string;
  results: AnalysisResultItem[];
  onUpdated?: () => void;
};

export function TrainingConfirmationPanel({
  caseId,
  caseStatus,
  results,
  onUpdated,
}: TrainingConfirmationPanelProps) {
  const [reviewStatus, setReviewStatus] =
    useState<CaseReviewStatusResponse | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string>(demoLabels[0]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const completed = caseStatus === "completed";
  const trainingReady = ["confirmed", "corrected"].includes(
    reviewStatus?.status ?? "",
  );
  const predictedLabel = useMemo(
    () => results.find((result) => result.predicted_positive)?.label_name,
    [results],
  );

  useEffect(() => {
    setSelectedLabel(predictedLabel ?? demoLabels[0]);
  }, [predictedLabel]);

  useEffect(() => {
    if (!completed || !caseId) {
      setReviewStatus(null);
      return;
    }
    let cancelled = false;
    getCaseReviewStatus(caseId)
      .then((status) => {
        if (!cancelled) {
          setReviewStatus(status);
        }
      })
      .catch((exc) => {
        if (!cancelled) {
          setError(
            exc instanceof Error
              ? exc.message
              : "Không tải được trạng thái xác nhận.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, completed]);

  async function handleConfirm() {
    setError(null);
    setMessage(null);
    try {
      setLoading(true);
      const status = await confirmCaseResult(caseId);
      setReviewStatus(status);
      setMessage(
        "Đã xác nhận kết quả AI là đúng. Ca này được đưa vào dữ liệu training-ready.",
      );
      onUpdated?.();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không xác nhận được kết quả.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCorrect() {
    setError(null);
    setMessage(null);
    try {
      setLoading(true);
      const labels: LabelCorrection[] = demoLabels.map((label) => ({
        label_name: label,
        confirmed_positive: label === selectedLabel,
      }));
      const status = await correctCaseLabels(caseId, labels);
      setReviewStatus(status);
      setMessage(
        "Đã lưu nhãn bác sĩ chọn. Ca này được đưa vào dữ liệu training-ready.",
      );
      onUpdated?.();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không lưu được nhãn đã sửa.");
    } finally {
      setLoading(false);
    }
  }

  if (!completed) {
    return (
      <Message>
        Ca chưa hoàn tất inference nên chưa thể xác nhận nhãn cho retraining.
      </Message>
    );
  }

  return (
    <div className="clinical-review-box">
      <div className="section-heading">
        <div>
          <h4>Xác nhận dữ liệu huấn luyện</h4>
          <p className="muted">
            Chỉ xác nhận khi bác sĩ/KTV đã xem kết quả. Dữ liệu đã xác nhận mới
            được tính cho retraining.
          </p>
        </div>
        <StatusBadge value={reviewStatus?.status ?? "chưa xác nhận"} />
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      {trainingReady ? (
        <div>
          <Message tone="success">
            Ca {compactId(caseId)} đã có nhãn xác nhận và được tính vào
            retraining buffer.
          </Message>
          <div className="toggle-grid">
            {reviewStatus?.confirmed_labels.map((label) => (
              <div className="toggle-row" key={label.label_name}>
                <strong>{label.label_name}</strong>
                <StatusBadge value={label.confirmed_positive} />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <>
          <Message tone="warning">
            Kết quả AI thô chưa phải dữ liệu huấn luyện. Chọn một trong hai hành
            động bên dưới sau khi đã đối chiếu ảnh và kết quả.
          </Message>
          <div className="decision-actions">
            <button
              className="primary"
              disabled={loading}
              onClick={() => void handleConfirm()}
              type="button"
            >
              Xác nhận AI đúng
            </button>
            <span className="action-note">
              Dùng khi toàn bộ nhãn AI phù hợp với đánh giá của bác sĩ.
            </span>
          </div>
          <div className="correction-box">
            <h4>Hoặc chọn nhãn đúng để sửa</h4>
            <div className="toggle-grid">
              {demoLabels.map((label) => (
                <label className="toggle-row" key={label}>
                  <input
                    checked={selectedLabel === label}
                    name={`case-${caseId}-correct-label`}
                    onChange={() => setSelectedLabel(label)}
                    type="radio"
                  />
                  {label}
                </label>
              ))}
            </div>
            <button disabled={loading} onClick={() => void handleCorrect()} type="button">
              Lưu nhãn bác sĩ chọn
            </button>
          </div>
        </>
      )}
    </div>
  );
}
