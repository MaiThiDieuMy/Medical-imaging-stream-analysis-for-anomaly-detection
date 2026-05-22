import { useEffect, useState } from "react";
import {
  archiveCase,
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
import type { CaseDetailResponse, CaseListItem, UserRole } from "../types/api";
import { compactId } from "../utils/format";

type CasesPageProps = {
  role: UserRole;
};

export function CasesPage({ role }: CasesPageProps) {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [selectedCase, setSelectedCase] = useState<CaseDetailResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refreshCases() {
    setError(null);
    setLoading(true);
    try {
      const loadedCases = role === "admin" ? await listCases() : await listMyCases();
      setCases(loadedCases);
      if (!selectedCase && loadedCases.length > 0) {
        await selectCase(loadedCases[0].case_id);
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

  async function handleArchive(caseId: string) {
    if (!window.confirm("Lưu trữ ca chụp này? Dữ liệu và kết quả vẫn được giữ trong hệ thống.")) {
      return;
    }
    setError(null);
    setMessage(null);
    try {
      const archived = await archiveCase(caseId);
      setSelectedCase(archived);
      setMessage("Đã lưu trữ ca chụp. Danh sách chính sẽ không hiển thị ca này nữa.");
      await refreshCases();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không lưu trữ được ca chụp.");
    }
  }

  useEffect(() => {
    void refreshCases();
    return () => {
      if (imageUrl) {
        URL.revokeObjectURL(imageUrl);
      }
    };
  }, [role]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>{role === "admin" ? "Tất cả ca chụp" : "Lịch sử ca chụp"}</h2>
          <p>
            {role === "admin"
              ? "Quản trị viên xem được toàn bộ ca trong hệ thống."
              : "Bác sĩ/KTV chỉ xem các ca do chính mình upload."}
          </p>
        </div>
        <button disabled={loading} onClick={() => void refreshCases()} type="button">
          {loading ? "Đang tải..." : "Refresh"}
        </button>
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="split-layout">
        <div className="panel">
          <h3>Danh sách ca</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Bệnh nhân</th>
                  <th>Status</th>
                  <th>Review</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((item) => (
                  <tr key={item.case_id}>
                    <td title={item.case_id}>{compactId(item.case_id)}</td>
                    <td>
                      {item.patient_name}
                      <small>{item.patient_code}</small>
                    </td>
                    <td>
                      <StatusBadge value={item.status} />
                    </td>
                    <td>{item.review_status ?? "-"}</td>
                    <td>
                      <div className="actions">
                        <button
                          onClick={() => void selectCase(item.case_id)}
                          type="button"
                        >
                          Xem
                        </button>
                        {role === "admin" && (
                          <button
                            onClick={() => void handleArchive(item.case_id)}
                            type="button"
                          >
                            Lưu trữ
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {cases.length === 0 && (
                  <tr>
                    <td colSpan={5}>Chưa có ca chụp.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          {selectedCase ? (
            <>
              <div className="section-heading">
                <h3>Chi tiết ca {compactId(selectedCase.case_id)}</h3>
                <button
                  onClick={() => void openReport(selectedCase.case_id)}
                  type="button"
                >
                  Xuất báo cáo
                </button>
              </div>
              {imageUrl ? (
                <div className="image-preview">
                  <img alt="Ảnh X-quang đã lưu" src={imageUrl} />
                </div>
              ) : (
                <div className="empty-preview">Không tải được ảnh</div>
              )}
              <dl className="detail-list">
                <div>
                  <dt>Bệnh nhân</dt>
                  <dd>
                    {selectedCase.patient.full_name} (
                    {selectedCase.patient.patient_code})
                  </dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <StatusBadge value={selectedCase.status} />
                  </dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{selectedCase.model_version ?? "-"}</dd>
                </div>
                <div>
                  <dt>Review</dt>
                  <dd>{selectedCase.review_status ?? "-"}</dd>
                </div>
                <div>
                  <dt>Lưu trữ</dt>
                  <dd>{selectedCase.archived_at ?? "-"}</dd>
                </div>
                <div>
                  <dt>File</dt>
                  <dd>{selectedCase.image?.file_name ?? "-"}</dd>
                </div>
              </dl>
              <ResultTable results={selectedCase.results} />
              {selectedCase.results.length > 0 && (
                <TrainingConfirmationPanel
                  caseId={selectedCase.case_id}
                  caseStatus={selectedCase.status}
                  onUpdated={() => void selectCase(selectedCase.case_id)}
                  results={selectedCase.results}
                />
              )}
            </>
          ) : (
            <p className="muted">Chọn một ca để xem chi tiết.</p>
          )}
        </div>
      </div>
    </section>
  );
}
