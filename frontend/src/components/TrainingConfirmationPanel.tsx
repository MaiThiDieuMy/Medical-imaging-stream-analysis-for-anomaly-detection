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
  const [note, setNote] = useState("");
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
  const confirmedLabel = useMemo(
    () =>
      reviewStatus?.confirmed_labels.find((label) => label.confirmed_positive)
        ?.label_name ?? null,
    [reviewStatus],
  );

  useEffect(() => {
    setSelectedLabel(confirmedLabel ?? predictedLabel ?? demoLabels[0]);
    setNote(reviewStatus?.note ?? "");
  }, [confirmedLabel, predictedLabel, reviewStatus?.note]);

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
      const status = await confirmCaseResult(caseId, note);
      setReviewStatus(status);
      setMessage("Đã lưu xác nhận AI đúng cho ca này.");
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
      const status = await correctCaseLabels(caseId, labels, note);
      setReviewStatus(status);
      setMessage("Đã lưu nhãn bác sĩ chọn cho ca này.");
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
        Ca chưa hoàn tất inference nên chưa thể xác nhận nhãn cho dữ liệu huấn
        luyện.
      </Message>
    );
  }

  return (
    <div className="clinical-review-box">
      <div className="section-heading">
        <div>
          <h4>Xác nhận nhãn sau phân tích</h4>
          <p className="muted">
            Chỉ xác nhận khi bác sĩ/KTV đã xem kết quả. Chỉ các ca đã được bác
            sĩ xác nhận hoặc gán nhãn lại mới được dùng cho dữ liệu huấn luyện.
          </p>
        </div>
        <StatusBadge value={reviewStatus?.status ?? "chưa xác nhận"} />
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      {trainingReady ? (
        <Message tone="success">
          {reviewStatus?.status === "corrected"
            ? "Nhãn đã gán lại"
            : "Nhãn AI đã được xác nhận"}
          : <strong>{confirmedLabel ?? "-"}</strong>. Bác sĩ/KTV có thể cập nhật lại
          nhãn và ghi chú chuyên môn nếu cần chỉnh sửa cho ca {compactId(caseId)}.
        </Message>
      ) : (
        <Message tone="warning">
          Kết quả AI thô chưa phải dữ liệu huấn luyện. Chọn một trong hai hành
          động bên dưới sau khi đã đối chiếu ảnh và kết quả.
        </Message>
      )}

      <label className="note-field">
        Ghi chú chuyên môn
        <textarea
          onChange={(event) => setNote(event.target.value)}
          placeholder="Nhập ghi chú lâm sàng ngắn nếu cần"
          rows={2}
          value={note}
        />
      </label>

      <div className="decision-actions">
        <button
          className="primary"
          disabled={loading}
          onClick={() => void handleConfirm()}
          type="button"
        >
          {trainingReady ? "Cập nhật xác nhận" : "Xác nhận AI đúng"}
        </button>
        <span className="action-note">
          Dùng khi nhãn AI phù hợp với đánh giá của bác sĩ sau khi xem ảnh.
        </span>
      </div>

      <div className="correction-box">
        <h4>
          {trainingReady ? "Chỉnh sửa nhãn xác nhận" : "Gán nhãn lại"}
        </h4>
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
          {trainingReady ? "Lưu nhãn đã chỉnh sửa" : "Lưu nhãn đã chọn"}
        </button>
      </div>
    </div>
  );
}
