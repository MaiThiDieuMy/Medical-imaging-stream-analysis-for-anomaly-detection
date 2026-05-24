import { useEffect, useMemo, useState } from "react";
import {
  getCaseDetail,
  getCaseImage,
  getCaseReportHtml,
  listCases,
  listMyCases,
} from "../api/client";
import { Message } from "../components/Message";
import { ResultTable } from "../components/ResultTable";
import { StatusBadge } from "../components/StatusBadge";
import { TrainingConfirmationPanel } from "../components/TrainingConfirmationPanel";
import type {
  CaseDetailResponse,
  CaseListItem,
  UserRole,
} from "../types/api";
import {
  compactId,
  formatDateTime,
  formatProcessingStatus,
  formatReviewStatus,
} from "../utils/format";

type CasesPageProps = {
  role: UserRole;
  initialCaseId?: string | null;
  onOpenReviews?: () => void;
};

export function CasesPage({ role, initialCaseId, onOpenReviews }: CasesPageProps) {
  const isAdmin = role === "admin";
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [selectedCase, setSelectedCase] = useState<CaseDetailResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [reviewFilter, setReviewFilter] = useState("all");
  const [modelFilter, setModelFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const filteredCases = useMemo(() => {
    const query = search.trim().toLowerCase();
    return cases.filter((item) => {
      const matchesQuery =
        !query ||
        item.patient_code.toLowerCase().includes(query) ||
        item.patient_name.toLowerCase().includes(query) ||
        item.case_id.toLowerCase().includes(query);
      const matchesStatus = statusFilter === "all" || item.status === statusFilter;
      const currentReview = item.review_status ?? "none";
      const matchesReview =
        reviewFilter === "all" ||
        (reviewFilter === "none" && currentReview === "none") ||
        currentReview === reviewFilter;
      const matchesModel =
        modelFilter === "all" || item.model_version === modelFilter;
      return matchesQuery && matchesStatus && matchesReview && matchesModel;
    });
  }, [cases, modelFilter, reviewFilter, search, statusFilter]);

  const modelVersions = useMemo(
    () =>
      Array.from(
        new Set(cases.map((item) => item.model_version).filter(Boolean)),
      ).sort() as string[],
    [cases],
  );

  async function refreshCases(caseIdToOpen?: string | null) {
    setError(null);
    setLoading(true);
    try {
      const loadedCases = isAdmin ? await listCases() : await listMyCases();
      setCases(loadedCases);
      const targetCaseId = caseIdToOpen ?? selectedCase?.case_id;
      if (targetCaseId && loadedCases.some((item) => item.case_id === targetCaseId)) {
        await selectCase(targetCaseId);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tải được danh sách ca.");
    } finally {
      setLoading(false);
    }
  }

  async function selectCase(caseId: string) {
    setError(null);
    setMessage(null);
    try {
      const detail = await getCaseDetail(caseId);
      setSelectedCase(detail);
      const blob = await getCaseImage(caseId);
      const objectUrl = URL.createObjectURL(blob);
      setImageUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return objectUrl;
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tải được chi tiết ca.");
    }
  }

  async function openReport(caseId: string) {
    setError(null);
    setMessage(null);
    try {
      const html = await getCaseReportHtml(caseId);
      const reportUrl = URL.createObjectURL(
        new Blob([html], { type: "text/html;charset=utf-8" }),
      );
      window.open(reportUrl, "_blank", "noopener,noreferrer");
      setMessage("Đã mở báo cáo HTML. Có thể dùng Print/Save as PDF từ trình duyệt.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không xuất được báo cáo.");
    }
  }

  function copyCaseId(caseId: string) {
    navigator.clipboard
      ?.writeText(caseId)
      .then(() => setMessage("Đã sao chép mã ca."))
      .catch(() => setMessage("Không sao chép được, hãy sao chép thủ công."));
  }

  useEffect(() => {
    void refreshCases(initialCaseId);
    return () => {
      setImageUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
    };
  }, [isAdmin, role, initialCaseId]);

  const pageTitle = isAdmin ? "Tất cả ca chụp" : "Lịch sử ca chụp";

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>{pageTitle}</h2>
          <p>
            {isAdmin
              ? "Quản trị viên xem toàn bộ ca trong hệ thống, kiểm tra trạng thái xử lý và mở báo cáo khi cần."
              : "Tìm ca, xem ảnh, kết quả AI, báo cáo và trạng thái xác nhận."}
          </p>
        </div>
        <button disabled={loading} onClick={() => void refreshCases()} type="button">
          {loading ? "Đang tải..." : "Tải lại danh sách"}
        </button>
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className={`panel filter-panel ${isAdmin ? "admin-case-filter-panel" : "doctor-filter-panel"}`}>
        <label>
          Tìm bệnh nhân hoặc mã ca
          <input
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Nhập mã bệnh nhân, tên hoặc mã ca"
            value={search}
          />
        </label>
        <label>
          Trạng thái
          <select
            onChange={(event) => setStatusFilter(event.target.value)}
            value={statusFilter}
          >
            <option value="all">Tất cả</option>
            <option value="queued">{formatProcessingStatus("queued")}</option>
            <option value="processing">{formatProcessingStatus("processing")}</option>
            <option value="completed">{formatProcessingStatus("completed")}</option>
            <option value="failed">{formatProcessingStatus("failed")}</option>
          </select>
        </label>
        <label>
          Xác nhận
          <select
            onChange={(event) => setReviewFilter(event.target.value)}
            value={reviewFilter}
          >
            <option value="all">Tất cả</option>
            <option value="none">Chưa xác nhận</option>
            <option value="pending">{formatReviewStatus("pending")}</option>
            <option value="confirmed">{formatReviewStatus("confirmed")}</option>
            <option value="corrected">{formatReviewStatus("corrected")}</option>
          </select>
        </label>
        {isAdmin && (
          <label>
            Phiên bản model
            <select
              onChange={(event) => setModelFilter(event.target.value)}
              value={modelFilter}
            >
              <option value="all">Tất cả</option>
              {modelVersions.map((version) => (
                <option key={version} value={version}>
                  {version}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="worklist-layout">
        <div className="panel">
          <div className="section-heading">
            <h3>Danh sách ca</h3>
            <span className="count-pill">
              {filteredCases.length}/{cases.length} ca
            </span>
          </div>
          <div className="table-wrap case-table-wrap">
            <table className="case-history-table">
              <thead>
                <tr>
                  <th>Mã ca</th>
                  <th>Mã BN</th>
                  <th>Tên bệnh nhân</th>
                  {isAdmin && <th>Bác sĩ/KTV</th>}
                  <th>Ngày tạo</th>
                  <th>Trạng thái</th>
                  <th>Kết quả chính</th>
                  <th>Model</th>
                  <th>Xác nhận</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((item) => (
                  <tr
                    className={selectedCase?.case_id === item.case_id ? "selected-row" : ""}
                    key={item.case_id}
                  >
                    <td title={item.case_id}>{compactId(item.case_id)}</td>
                    <td>{item.patient_code}</td>
                    <td>{item.patient_name}</td>
                    {isAdmin && (
                      <td title={item.uploaded_by ?? ""}>
                        {compactId(item.uploaded_by)}
                      </td>
                    )}
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>
                      <StatusBadge value={item.status} />
                    </td>
                    <td>{item.primary_result ?? "-"}</td>
                    <td>{item.model_version ?? "-"}</td>
                    <td>
                      <StatusBadge value={item.review_status ?? "no_review"} />
                    </td>
                    <td>
                      <div className="actions">
                        <button
                          className="primary"
                          onClick={() => void selectCase(item.case_id)}
                          type="button"
                        >
                          Xem chi tiết
                        </button>
                        <button
                          onClick={() => void openReport(item.case_id)}
                          type="button"
                        >
                          Xuất báo cáo
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filteredCases.length === 0 && (
                  <tr>
                    <td colSpan={isAdmin ? 10 : 9}>Không có ca phù hợp bộ lọc.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <CaseDetailPanel
          imageUrl={imageUrl}
          onBack={() => setSelectedCase(null)}
          onCopyCaseId={copyCaseId}
          onOpenReport={openReport}
          onOpenReviews={onOpenReviews}
          onRefreshCase={selectCase}
          selectedCase={selectedCase}
        />
      </div>
    </section>
  );
}

function CaseDetailPanel({
  imageUrl,
  onBack,
  onCopyCaseId,
  onOpenReport,
  onOpenReviews,
  onRefreshCase,
  selectedCase,
}: {
  imageUrl: string | null;
  onBack: () => void;
  onCopyCaseId: (caseId: string) => void;
  onOpenReport: (caseId: string) => Promise<void>;
  onOpenReviews?: () => void;
  onRefreshCase: (caseId: string) => Promise<void>;
  selectedCase: CaseDetailResponse | null;
}) {
  if (!selectedCase) {
    return (
      <div className="panel case-detail-panel">
        <div className="empty-state">
          <strong>Chưa chọn ca</strong>
          <p>Nhấn “Xem chi tiết” ở một ca trong danh sách để xem ảnh và kết quả AI.</p>
        </div>
      </div>
    );
  }

  const predicted = selectedCase.results.find((result) => result.predicted_positive);

  return (
    <div className="panel case-detail-panel">
      <div className="section-heading">
        <div>
          <h3>Chi tiết ca</h3>
          <p className="muted">{selectedCase.patient.full_name}</p>
        </div>
        <div className="actions">
          <button onClick={onBack} type="button">
            Quay lại lịch sử
          </button>
          <button onClick={() => void onOpenReport(selectedCase.case_id)} type="button">
            Xuất báo cáo
          </button>
        </div>
      </div>

      {imageUrl ? (
        <div className="image-preview case-image-preview">
          <img alt="Ảnh X-quang đã lưu" src={imageUrl} />
        </div>
      ) : (
        <div className="empty-preview">Không tải được ảnh</div>
      )}

      <div className="case-detail-grid">
        <section>
          <h4>Thông tin bệnh nhân</h4>
          <dl className="detail-list compact">
            <div>
              <dt>Mã bệnh nhân</dt>
              <dd>{selectedCase.patient.patient_code}</dd>
            </div>
            <div>
              <dt>Họ tên</dt>
              <dd>{selectedCase.patient.full_name}</dd>
            </div>
            <div>
              <dt>Giới tính</dt>
              <dd>{selectedCase.patient.gender}</dd>
            </div>
            <div>
              <dt>Năm sinh</dt>
              <dd>{selectedCase.patient.birth_year ?? "-"}</dd>
            </div>
            <div>
              <dt>Khoa/phòng</dt>
              <dd>{selectedCase.patient.department ?? "-"}</dd>
            </div>
          </dl>
        </section>

        <section>
          <h4>Metadata ca chụp</h4>
          <dl className="detail-list compact">
            <div>
              <dt>Mã ca</dt>
              <dd>
                <code>{selectedCase.case_id}</code>
                <button onClick={() => onCopyCaseId(selectedCase.case_id)} type="button">
                  Sao chép
                </button>
              </dd>
            </div>
            <div>
              <dt>Trạng thái</dt>
              <dd>
                <StatusBadge value={selectedCase.status} />
              </dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{selectedCase.model_version ?? "-"}</dd>
            </div>
            <div>
              <dt>Tệp ảnh</dt>
              <dd>{selectedCase.image?.file_name ?? "-"}</dd>
            </div>
            <div>
              <dt>Ngày tạo</dt>
              <dd>{formatDateTime(selectedCase.created_at)}</dd>
            </div>
          </dl>
        </section>
      </div>

      <div className="case-timeline">
        <TimelineItem label={formatProcessingStatus("queued")} value={selectedCase.job?.created_at} />
        <TimelineItem label={formatProcessingStatus("processing")} value={selectedCase.job?.started_at} />
        <TimelineItem label={formatProcessingStatus("completed")} value={selectedCase.job?.finished_at} />
      </div>

      <div className="section-heading">
        <div>
          <h4>Kết quả AI</h4>
          <p className="muted">
            Dự đoán chính:{" "}
            <strong>{predicted?.label_name ?? selectedCase.results[0]?.label_name ?? "-"}</strong>
          </p>
        </div>
        <StatusBadge value={selectedCase.review_status ?? "no_review"} />
      </div>
      <ResultTable results={selectedCase.results} />

      <dl className="detail-list compact">
        <div>
          <dt>Ghi chú</dt>
          <dd>{selectedCase.note ?? "-"}</dd>
        </div>
        <div>
          <dt>Ghi chú duyệt</dt>
          <dd>{selectedCase.review_note ?? "-"}</dd>
        </div>
      </dl>

      <div className="actions">
        <button onClick={onOpenReviews} type="button">
          Duyệt/gán nhãn lại
        </button>
      </div>

      {selectedCase.results.length > 0 && (
        <TrainingConfirmationPanel
          caseId={selectedCase.case_id}
          caseStatus={selectedCase.status}
          onUpdated={() => void onRefreshCase(selectedCase.case_id)}
          results={selectedCase.results}
        />
      )}
    </div>
  );
}

function TimelineItem({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className={value ? "reached" : ""}>
      <span />
      <strong>{label}</strong>
      <small>{formatDateTime(value)}</small>
    </div>
  );
}
