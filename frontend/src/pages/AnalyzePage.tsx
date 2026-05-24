import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  analyzeImage,
  getCaseReportHtml,
  getCaseResults,
  getJobStatus,
} from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import { TrainingConfirmationPanel } from "../components/TrainingConfirmationPanel";
import type {
  AnalyzeFormValues,
  AnalyzeResponse,
  CaseResultsResponse,
  JobStatusResponse,
} from "../types/api";
import { compactId, formatCacheStatus, formatProcessingStatus } from "../utils/format";

const initialValues: AnalyzeFormValues = {
  full_name: "",
  gender: "",
  birth_year: "",
  department: "",
  note: "",
};

const departments = [
  "Cấp cứu",
  "Chẩn đoán hình ảnh",
  "Hô hấp",
  "Nội tổng quát",
  "Ngoại trú",
  "ICU",
];

const timelineSteps = ["queued", "processing", "completed"] as const;

type AnalyzePageProps = {
  onOpenCase?: (caseId: string) => void;
};

export function AnalyzePage({ onOpenCase }: AnalyzePageProps) {
  const [values, setValues] = useState<AnalyzeFormValues>(initialValues);
  const [image, setImage] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [caseResults, setCaseResults] = useState<CaseResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPolling, setIsPolling] = useState(false);

  const results = useMemo(
    () => caseResults?.results ?? response?.results ?? [],
    [caseResults, response],
  );
  const currentStatus = String(
    caseResults?.status ?? jobStatus?.status ?? response?.status ?? "ready",
  );
  useEffect(() => {
    if (!image) {
      setPreviewUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(image);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [image]);

  useEffect(() => {
    if (!response?.job_id || !response.case_id || response.cache_hit) {
      return;
    }
    if (!["queued", "processing"].includes(response.status)) {
      return;
    }

    let cancelled = false;
    let interval: number | undefined;
    const poll = async () => {
      try {
        setIsPolling(true);
        const status = await getJobStatus(response.job_id as string);
        if (cancelled) {
          return;
        }
        setJobStatus(status);
        if (status.status === "completed" && response.case_id) {
          const fetchedResults = await getCaseResults(response.case_id);
          if (!cancelled) {
            setCaseResults(fetchedResults);
            setIsPolling(false);
            if (interval !== undefined) {
              window.clearInterval(interval);
            }
          }
        }
        if (status.status === "failed") {
          setError(status.error_message ?? "Job phân tích thất bại.");
          setIsPolling(false);
          if (interval !== undefined) {
            window.clearInterval(interval);
          }
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Không lấy được trạng thái.");
          setIsPolling(false);
        }
      }
    };

    void poll();
    interval = window.setInterval(() => {
      void poll();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [response]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setResponse(null);
    setJobStatus(null);
    setCaseResults(null);

    if (!values.full_name.trim() || !values.gender.trim()) {
      setError("Vui lòng nhập họ tên và giới tính.");
      return;
    }
    if (!image) {
      setError("Vui lòng chọn ảnh PNG hoặc JPG.");
      return;
    }
    if (!["image/png", "image/jpeg", "image/jpg"].includes(image.type)) {
      setError("Ảnh phải là PNG hoặc JPG.");
      return;
    }

    try {
      setIsSubmitting(true);
      const analyzeResponse = await analyzeImage(values, image);
      setResponse(analyzeResponse);
      if (analyzeResponse.case_id && analyzeResponse.cache_hit) {
        setCaseResults({
          case_id: analyzeResponse.case_id,
          status: analyzeResponse.status,
          model_id: analyzeResponse.model_id,
          model_version: analyzeResponse.model_version,
          results: analyzeResponse.results,
        });
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không gửi được yêu cầu.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function openReport() {
    if (!response?.case_id) {
      return;
    }
    setError(null);
    try {
      const html = await getCaseReportHtml(response.case_id);
      const reportUrl = URL.createObjectURL(
        new Blob([html], { type: "text/html;charset=utf-8" }),
      );
      window.open(reportUrl, "_blank", "noopener,noreferrer");
      setMessage("Đã mở báo cáo HTML trong tab mới.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không xuất được báo cáo.");
    }
  }

  function resetAnalyzeForm() {
    setValues(initialValues);
    setImage(null);
    setResponse(null);
    setJobStatus(null);
    setCaseResults(null);
    setError(null);
    setMessage(null);
    setIsPolling(false);
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Phân tích ảnh X-quang</h2>
          <p>
            Tạo ca mới, kiểm tra thông tin bệnh nhân và gửi ảnh vào hàng đợi AI
            khi bác sĩ/KTV bấm phân tích.
          </p>
        </div>
        <StatusBadge value={currentStatus} />
      </div>

      <form className="analysis-layout" onSubmit={handleSubmit}>
        <div className="panel analysis-image-panel">
          <div className="section-heading">
            <div>
              <h3>Ảnh X-quang</h3>
              <p className="muted">Chọn ảnh PNG/JPG và kiểm tra preview trước khi gửi.</p>
            </div>
            <span className="step-badge">1</span>
          </div>
          {previewUrl ? (
            <div className="image-preview">
              <img alt="Ảnh X-quang được chọn để phân tích" src={previewUrl} />
            </div>
          ) : (
            <div className="empty-preview">Chưa chọn ảnh</div>
          )}
          <label>
            Tệp ảnh
            <input
              accept="image/png,image/jpeg"
              onChange={(event) => setImage(event.target.files?.[0] ?? null)}
              required
              type="file"
            />
          </label>
          <dl className="detail-list compact">
            <div>
              <dt>Tên file</dt>
              <dd>{image?.name ?? "-"}</dd>
            </div>
            <div>
              <dt>Dung lượng</dt>
              <dd>{image ? formatFileSize(image.size) : "-"}</dd>
            </div>
            <div>
              <dt>MIME type</dt>
              <dd>{image?.type || "-"}</dd>
            </div>
          </dl>
        </div>

        <div className="panel analysis-work-panel">
          <div className="form-grid compact-form">
            <div className="form-section span-2">
              <span className="step-badge">2</span>
              <div>
                <h3>Thông tin bệnh nhân</h3>
                <p className="muted">
                  Mã bệnh nhân giúp đối chiếu lịch sử ca đã upload trước đó.
                </p>
              </div>
            </div>
            <label>
              Ma benh nhan
              <input
                disabled
                placeholder="Tu dong tao khi luu"
                value=""
              />
            </label>
            <label>
              Họ tên
              <input
                onChange={(event) =>
                  setValues({ ...values, full_name: event.target.value })
                }
                required
                value={values.full_name}
              />
            </label>
            <label>
              Giới tính
              <select
                onChange={(event) =>
                  setValues({ ...values, gender: event.target.value })
                }
                required
                value={values.gender}
              >
                <option value="">Chọn giới tính</option>
                <option value="Nam">Nam</option>
                <option value="Nữ">Nữ</option>
                <option value="Khác">Khác</option>
              </select>
            </label>
            <label>
              Năm sinh
              <input
                max="2100"
                min="1900"
                onChange={(event) =>
                  setValues({ ...values, birth_year: event.target.value })
                }
                type="number"
                value={values.birth_year}
              />
            </label>
            <label>
              Khoa/phòng
              <select
                onChange={(event) =>
                  setValues({ ...values, department: event.target.value })
                }
                value={values.department}
              >
                <option value="">Chọn khoa/phòng</option>
                {departments.map((department) => (
                  <option key={department} value={department}>
                    {department}
                  </option>
                ))}
              </select>
            </label>
            <label className="span-2">
              Ghi chú lâm sàng
              <textarea
                onChange={(event) =>
                  setValues({ ...values, note: event.target.value })
                }
                placeholder="Ví dụ: sốt, ho kéo dài, nghi tràn dịch..."
                rows={2}
                value={values.note}
              />
            </label>
            <button className="primary span-2 submit-button" disabled={isSubmitting} type="submit">
              {isSubmitting ? "Đang gửi ảnh vào hàng đợi..." : "Phân tích AI"}
            </button>
          </div>

          <div className="analysis-status-block">
            {error && <Message tone="error">{error}</Message>}
            {message && <Message tone="success">{message}</Message>}
            {response?.cache_hit && (
              <Message tone="success">
                {formatCacheStatus(true)}: kết quả được lấy từ cache, không tạo job mới.
              </Message>
            )}
            {isPolling && (
              <Message>AI đang xử lý. Kết quả sẽ tự cập nhật khi hoàn tất.</Message>
            )}
            <StatusTimeline status={currentStatus} />
            <dl className="detail-list compact">
              <div>
                <dt>Mã ca</dt>
                <dd title={response?.case_id ?? ""}>{compactId(response?.case_id)}</dd>
              </div>
              <div>
                <dt>Mã job</dt>
                <dd title={response?.job_id ?? ""}>{compactId(response?.job_id)}</dd>
              </div>
              <div>
                <dt>Phiên bản model</dt>
                <dd>{response?.model_version ?? "-"}</dd>
              </div>
            </dl>
            {response?.case_id && (
              <div className="actions">
                <button
                  onClick={() => onOpenCase?.(response.case_id as string)}
                  type="button"
                >
                  Xem chi tiết ca
                </button>
                <button onClick={() => void openReport()} type="button">
                  Xuất báo cáo
                </button>
                <button onClick={resetAnalyzeForm} type="button">
                  Phân tích ảnh mới
                </button>
              </div>
            )}
          </div>

          <div>
            <h3>Kết quả AI</h3>
            <ResultTable results={results} />
          </div>
          {response?.case_id && results.length > 0 && (
            <TrainingConfirmationPanel
              caseId={response.case_id}
              caseStatus={currentStatus}
              results={results}
            />
          )}
        </div>
      </form>
    </section>
  );
}

function StatusTimeline({ status }: { status: string }) {
  const failed = status === "failed";
  const activeIndex = timelineSteps.findIndex((step) => step === status);
  return (
    <div className="status-timeline" aria-label="Trạng thái xử lý">
      {timelineSteps.map((step, index) => {
        const reached = activeIndex >= index || status === "completed";
        return (
          <div className={reached ? "reached" : ""} key={step}>
            <span>{index + 1}</span>
            <strong>{formatProcessingStatus(step)}</strong>
          </div>
        );
      })}
      {failed && (
        <div className="failed reached">
          <span>!</span>
          <strong>{formatProcessingStatus("failed")}</strong>
        </div>
      )}
    </div>
  );
}

function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}
