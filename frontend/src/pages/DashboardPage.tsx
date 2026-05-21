import { useEffect, useMemo, useState } from "react";
import {
  getMonitoringSummary,
  listCases,
  listMyCases,
  listPendingReviews,
  listUsers,
} from "../api/client";
import { Message } from "../components/Message";
import { StatusBadge } from "../components/StatusBadge";
import type { CaseListItem, CaseReview, MonitoringSummary, UserPublic } from "../types/api";
import { compactId } from "../utils/format";
import type { PageKey } from "../utils/navigation";

type DashboardPageProps = {
  currentUser: UserPublic;
  onNavigate: (page: PageKey) => void;
};

export function DashboardPage({ currentUser, onNavigate }: DashboardPageProps) {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [reviews, setReviews] = useState<CaseReview[]>([]);
  const [monitoring, setMonitoring] = useState<MonitoringSummary | null>(null);
  const [totalUsers, setTotalUsers] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = currentUser.role === "admin";

  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      setError(null);
      try {
        const [caseList, reviewList, monitoringSummary, userList] = await Promise.all([
          isAdmin ? listCases() : listMyCases(),
          listPendingReviews(),
          isAdmin ? getMonitoringSummary().catch(() => null) : Promise.resolve(null),
          isAdmin ? listUsers().catch(() => []) : Promise.resolve([]),
        ]);
        if (!cancelled) {
          setCases(caseList);
          setReviews(reviewList);
          setMonitoring(monitoringSummary);
          setTotalUsers(userList.length);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Không tải được dashboard.");
        }
      }
    }

    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

  const completedCases = useMemo(
    () => cases.filter((item) => item.status === "completed").length,
    [cases],
  );
  const processingCases = useMemo(
    () => cases.filter((item) => ["queued", "processing"].includes(item.status)).length,
    [cases],
  );

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Hệ thống phân tích ảnh X-quang lồng ngực</h2>
          <p>
            {isAdmin
              ? "Bảng tổng quan cho quản trị vận hành, mô hình, người dùng và ca cần duyệt."
              : "Bảng tổng quan cho Bác sĩ/KTV theo dõi ca đã upload và ca cần xác nhận nhãn."}
          </p>
        </div>
        <StatusBadge value={isAdmin ? monitoring?.backend_status ?? "admin" : "doctor"} />
      </div>

      {error && <Message tone="error">{error}</Message>}

      <div className="summary-grid">
        <SummaryItem label={isAdmin ? "Tổng ca chụp" : "Ca của tôi"} value={cases.length} />
        <SummaryItem label="Đã hoàn tất" value={completedCases} />
        <SummaryItem label="Đang xử lý" value={processingCases} />
        <SummaryItem label="Ca cần duyệt" value={reviews.length} />
        {isAdmin && (
          <>
            <SummaryItem label="Người dùng" value={totalUsers ?? "-"} />
            <SummaryItem
              label="Training-ready"
              value={monitoring?.training_ready_cases ?? "-"}
            />
            <SummaryItem label="Redis" value={monitoring?.redis_broker_status ?? "-"} />
          </>
        )}
      </div>

      <div className="split-layout">
        <div className="panel">
          <div className="section-heading">
            <h3>{isAdmin ? "Vận hành hệ thống" : "Luồng làm việc"}</h3>
          </div>
          <div className="quick-actions">
            {!isAdmin && (
              <button className="primary" onClick={() => onNavigate("analyze")} type="button">
                Phân tích ảnh
              </button>
            )}
            <button onClick={() => onNavigate("cases")} type="button">
              {isAdmin ? "Xem tất cả ca chụp" : "Xem lịch sử ca"}
            </button>
            <button onClick={() => onNavigate("reviews")} type="button">
              Duyệt/gán nhãn lại
            </button>
            {isAdmin && (
              <>
                <button onClick={() => onNavigate("users")} type="button">
                  Quản lý người dùng
                </button>
                <button onClick={() => onNavigate("models")} type="button">
                  Quản lý mô hình
                </button>
                <button onClick={() => onNavigate("monitoring")} type="button">
                  Monitoring
                </button>
              </>
            )}
          </div>
        </div>

        <div className="panel">
          <h3>Ca gần đây</h3>
          <div className="status-table">
            {cases.slice(0, 5).map((item) => (
              <div key={item.case_id}>
                <span title={item.case_id}>
                  {item.patient_name} ({compactId(item.case_id)})
                </span>
                <StatusBadge value={item.status} />
                <strong>{item.review_status ?? "-"}</strong>
              </div>
            ))}
            {cases.length === 0 && <p className="muted">Chưa có ca chụp.</p>}
          </div>
        </div>
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
