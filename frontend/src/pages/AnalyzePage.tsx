import { FormEvent, useEffect, useMemo, useState } from "react";
import { analyzeImage, getCaseResults, getJobStatus } from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import type {
  AnalyzeFormValues,
  AnalyzeResponse,
  CaseResultsResponse,
  JobStatusResponse,
} from "../types/api";
import { compactId } from "../utils/format";

const initialValues: AnalyzeFormValues = {
  patient_code: "",
  full_name: "",
  gender: "",
  birth_year: "",
  department: "",
  note: "",
};

type AnalyzePageProps = {
  onOpenCases?: () => void;
};

export function AnalyzePage({ onOpenCases }: AnalyzePageProps) {
  const [values, setValues] = useState<AnalyzeFormValues>(initialValues);
  const [image, setImage] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [caseResults, setCaseResults] = useState<CaseResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPolling, setIsPolling] = useState(false);

  const results = useMemo(
    () => caseResults?.results ?? response?.results ?? [],
    [caseResults, response],
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
    setResponse(null);
    setJobStatus(null);
    setCaseResults(null);

    if (!values.patient_code.trim() || !values.full_name.trim() || !values.gender.trim()) {
      setError("Vui lòng nhập patient_code, full_name và gender.");
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

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Phân tích X-quang ngực</h2>
          <p>Bác sĩ/KTV nhập metadata và bấm Phân tích AI khi cần chạy AI.</p>
        </div>
        <StatusBadge value={jobStatus?.status ?? response?.status ?? "ready"} />
      </div>

      <div className="split-layout">
        <form className="panel form-grid" onSubmit={handleSubmit}>
          <label>
            Patient code
            <input
              onChange={(event) =>
                setValues({ ...values, patient_code: event.target.value })
              }
              required
              value={values.patient_code}
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
            <input
              onChange={(event) =>
                setValues({ ...values, gender: event.target.value })
              }
              required
              value={values.gender}
            />
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
            <input
              onChange={(event) =>
                setValues({ ...values, department: event.target.value })
              }
              value={values.department}
            />
          </label>
          <label className="span-2">
            Ghi chú
            <textarea
              onChange={(event) =>
                setValues({ ...values, note: event.target.value })
              }
              rows={3}
              value={values.note}
            />
          </label>
          <label className="span-2">
            Ảnh X-quang
            <input
              accept="image/png,image/jpeg"
              onChange={(event) => setImage(event.target.files?.[0] ?? null)}
              required
              type="file"
            />
          </label>
          <button className="primary span-2" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Đang gửi..." : "Phân tích AI"}
          </button>
        </form>

        <div className="panel">
          <h3>Ảnh đã chọn</h3>
          {previewUrl ? (
            <div className="image-preview">
              <img alt="Ảnh X-quang được chọn để phân tích" src={previewUrl} />
            </div>
          ) : (
            <div className="empty-preview">Chưa chọn ảnh</div>
          )}
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

          <h3>Trạng thái</h3>
          {error && <Message tone="error">{error}</Message>}
          {response?.cache_hit && (
            <Message tone="success">
              Kết quả được lấy từ cache, không tạo job mới.
            </Message>
          )}
          {isPolling && <Message>Đang cập nhật trạng thái job...</Message>}
          <dl className="detail-list">
            <div>
              <dt>Cache hit</dt>
              <dd>
                <StatusBadge value={response?.cache_hit ?? false} />
              </dd>
            </div>
            <div>
              <dt>Case ID</dt>
              <dd title={response?.case_id ?? ""}>{compactId(response?.case_id)}</dd>
            </div>
            <div>
              <dt>Job ID</dt>
              <dd title={response?.job_id ?? ""}>{compactId(response?.job_id)}</dd>
            </div>
            <div>
              <dt>Model version</dt>
              <dd>{response?.model_version ?? "-"}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <StatusBadge value={jobStatus?.status ?? response?.status ?? "-"} />
              </dd>
            </div>
          </dl>
          <h3>Kết quả</h3>
          {response?.case_id && onOpenCases && (
            <button onClick={onOpenCases} type="button">
              Xem chi tiết ca
            </button>
          )}
          <ResultTable results={results} />
        </div>
      </div>
    </section>
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
