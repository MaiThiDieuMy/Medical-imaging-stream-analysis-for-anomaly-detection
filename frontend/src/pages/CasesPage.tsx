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
    if (
      !window.confirm(
        "Ẩn ca này khỏi danh sách chính? Dữ liệu, ảnh và kết quả vẫn được giữ trong hệ thống.",
      )
    ) {
      return;
    }
    setError(null);
    setMessage(null);
    try {
      const archived = await archiveCase(caseId);
      setSelectedCase(archived);
      setMessage("Đã lưu trữ ca chụp. Ca này không còn xuất hiện trong danh sách chính.");
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
              ? "Quản trị viên xem được toàn bộ ca trong hệ thống và có thể lưu trữ ca đã xử lý."
              : "Chọn một ca trong danh sách để xem ảnh, kết quả AI và trạng thái xác nhận."}
          </p>
        </div>
        <button disabled={loading} onClick={() => void refreshCases()} type="button">
          {loading ? "Đang tải..." : "Tải lại danh sách"}
        </button>
      </div>

      {error && <Message tone="error">{error}</Message>}
      {message && <Message tone="success">{message}</Message>}

      <div className="worklist-layout">
        <div className="panel">
          <div className="section-heading">
            <h3>Danh sách ca</h3>
            <span className="count-pill">{cases.length} ca</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Bệnh nhân</th>
                  <th>Trạng thái</th>
                  <th>Xác nhận</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((item) => (
                  <tr
                    className={selectedCase?.case_id === item.case_id ? "selected-row" : ""}
                    key={item.case_id}
                  >
                    <td title={item.case_id}>{compactId(item.case_id)}</td>
                    <td>
                      {item.patient_name}
                      <small>{item.patient_code}</small>
                    </td>
                    <td>
                      <StatusBadge value={item.status} />
                    </td>
                    <td>{item.review_status ?? "Chưa xác nhận"}</td>
                    <td>
                      <div className="actions">
                        <button
                          className="primary"
                          onClick={() => void selectCase(item.case_id)}
                          type="button"
                        >
                          Mở chi tiết
                        </button>
                        {role === "admin" && (
                          <button
                            className="danger"
                            onClick={() => void handleArchive(item.case_id)}
                            type="button"
                          >
                            Lưu trữ ca
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

        <div className="panel case-detail-panel">
          {selectedCase ? (
            <>
              <div className="section-heading">
                <div>
                  <h3>Chi tiết ca {compactId(selectedCase.case_id)}</h3>
                  <p className="muted">{selectedCase.patient.full_name}</p>
                </div>
                <button
                  onClick={() => void openReport(selectedCase.case_id)}
                  type="button"
                >
                  Xuất báo cáo HTML
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
                  <dt>Xác nhận</dt>
                  <dd>{selectedCase.review_status ?? "Chưa xác nhận"}</dd>
                </div>
                <div>
                  <dt>Lưu trữ</dt>
                  <dd>{selectedCase.archived_at ?? "Chưa lưu trữ"}</dd>
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
            <div className="empty-state">
              <strong>Chưa chọn ca</strong>
              <p>
                Nhấn “Mở chi tiết” ở một ca trong danh sách để xem ảnh, kết quả
                AI và hành động xác nhận.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
