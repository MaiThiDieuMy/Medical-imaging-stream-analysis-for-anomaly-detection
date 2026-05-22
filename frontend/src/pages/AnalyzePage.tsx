import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  analyzeImage,
  getCaseResults,
  getJobStatus,
  listMyCases,
} from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import { TrainingConfirmationPanel } from "../components/TrainingConfirmationPanel";
import type {
  AnalyzeFormValues,
  AnalyzeResponse,
  CaseListItem,
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

const departments = [
  "Cấp cứu",
  "Chẩn đoán hình ảnh",
  "Hô hấp",
  "Nội tổng quát",
  "Ngoại trú",
  "ICU",
];

type AnalyzePageProps = {
  onOpenCases?: () => void;
};

export function AnalyzePage({ onOpenCases }: AnalyzePageProps) {
  const [values, setValues] = useState<AnalyzeFormValues>(initialValues);
  const [knownCases, setKnownCases] = useState<CaseListItem[]>([]);
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
  const currentCaseStatus = String(
    caseResults?.status ?? jobStatus?.status ?? response?.status ?? "",
  );
  const matchingPatientCases = useMemo(() => {
    const patientCode = values.patient_code.trim().toLowerCase();
    if (!patientCode) {
      return [];
    }
    return knownCases.filter(
      (item) => item.patient_code.toLowerCase() === patientCode,
    );
  }, [knownCases, values.patient_code]);

  useEffect(() => {
    listMyCases()
      .then(setKnownCases)
      .catch(() => {
        setKnownCases([]);
      });
  }, []);

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
      setError("Vui lòng nhập mã bệnh nhân, họ tên và giới tính.");
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
      listMyCases().then(setKnownCases).catch(() => undefined);
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
          <h2>Phân tích ảnh X-quang</h2>
          <p>
            Tạo ca mới, kiểm tra thông tin bệnh nhân và gửi ảnh vào hàng đợi AI.
          </p>
        </div>
        <StatusBadge value={jobStatus?.status ?? response?.status ?? "sẵn sàng"} />
      </div>

      <div className="analysis-layout">
        <form className="panel form-grid analysis-form" onSubmit={handleSubmit}>
          <div className="form-section span-2">
            <span className="step-badge">1</span>
            <div>
              <h3>Thông tin bệnh nhân</h3>
              <p className="muted">
                Mã bệnh nhân được dùng để đối chiếu lịch sử ca đã upload.
              </p>
            </div>
          </div>
          <label>
            Mã bệnh nhân
            <input
              className={matchingPatientCases.length > 0 ? "input-warning" : ""}
              onChange={(event) =>
                setValues({ ...values, patient_code: event.target.value })
              }
              required
              value={values.patient_code}
            />
            {matchingPatientCases.length > 0 && (
              <small className="field-hint warning-text">
                Đã có {matchingPatientCases.length} ca với mã này. Hãy kiểm tra
                đúng bệnh nhân trước khi gửi ảnh mới.
              </small>
            )}
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
              rows={3}
              value={values.note}
            />
          </label>

          <div className="form-section span-2">
            <span className="step-badge">2</span>
            <div>
              <h3>Ảnh cần phân tích</h3>
              <p className="muted">Hỗ trợ PNG/JPG. Không tải lên dữ liệu bệnh nhân thật trong môi trường demo.</p>
            </div>
          </div>
          <label className="span-2">
            Ảnh X-quang
            <input
              accept="image/png,image/jpeg"
              onChange={(event) => setImage(event.target.files?.[0] ?? null)}
              required
              type="file"
            />
          </label>
          <button className="primary span-2 submit-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Đang gửi ảnh vào hàng đợi..." : "Gửi ảnh để AI phân tích"}
          </button>
        </form>

        <div className="panel">
          <div className="section-heading">
            <h3>Preview và kết quả</h3>
            <StatusBadge value={isPolling ? "đang xử lý" : response?.status ?? "chưa gửi"} />
          </div>
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

          {error && <Message tone="error">{error}</Message>}
          {response?.cache_hit && (
            <Message tone="success">
              Kết quả được lấy từ cache, không tạo job mới.
            </Message>
          )}
          {isPolling && <Message>AI đang xử lý. Kết quả sẽ tự cập nhật khi hoàn tất.</Message>}
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
              <dt>Trạng thái</dt>
              <dd>
                <StatusBadge value={jobStatus?.status ?? response?.status ?? "-"} />
              </dd>
            </div>
          </dl>
          <div className="section-heading">
            <h3>Kết quả AI</h3>
            {response?.case_id && onOpenCases && (
              <button onClick={onOpenCases} type="button">
                Mở ca trong lịch sử
              </button>
            )}
          </div>
          <ResultTable results={results} />
          {response?.case_id && results.length > 0 && (
            <TrainingConfirmationPanel
              caseId={response.case_id}
              caseStatus={currentCaseStatus}
              results={results}
            />
          )}
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
