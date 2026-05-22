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
  const failedCases = useMemo(
    () => cases.filter((item) => item.status === "failed").length,
    [cases],
  );

  return (
    <section className="page">
      <div className="dashboard-hero">
        <div>
          <span className="eyebrow">{isAdmin ? "Admin operations" : "Clinical workspace"}</span>
          <h2>Hệ thống phân tích ảnh X-quang lồng ngực</h2>
          <p>
            {isAdmin
              ? "Theo dõi sức khỏe hệ thống, hàng đợi inference, review cần xử lý và model đang hoạt động."
              : "Theo dõi ca đã upload, mở nhanh lịch sử và xác nhận nhãn sau khi AI hoàn tất."}
          </p>
        </div>
        <div className="hero-status">
          <StatusBadge value={isAdmin ? monitoring?.backend_status ?? "admin" : "doctor"} />
          <strong>{currentUser.full_name}</strong>
          <span>{isAdmin ? "Quản trị viên" : "Bác sĩ/KTV"}</span>
        </div>
      </div>

      {error && <Message tone="error">{error}</Message>}

      <div className="summary-grid dashboard-kpis">
        <SummaryItem label={isAdmin ? "Tổng ca chụp" : "Ca của tôi"} value={cases.length} />
        <SummaryItem label="Đã hoàn tất" value={completedCases} />
        <SummaryItem label="Đang xử lý" value={processingCases} />
        <SummaryItem label="Thất bại" value={failedCases} />
        <SummaryItem label="Ca cần duyệt" value={reviews.length} />
        {isAdmin && (
          <>
            <SummaryItem label="Người dùng" value={totalUsers ?? "-"} />
            <SummaryItem
              label="Training-ready"
              value={monitoring?.training_ready_cases ?? "-"}
            />
            <SummaryItem
              label="Queue"
              value={monitoring?.celery_queue_length ?? "unknown"}
            />
          </>
        )}
      </div>

      {isAdmin ? (
        <AdminDashboard
          monitoring={monitoring}
          onNavigate={onNavigate}
          recentCases={cases.slice(0, 6)}
          reviews={reviews}
        />
      ) : (
        <DoctorDashboard
          onNavigate={onNavigate}
          recentCases={cases.slice(0, 5)}
          reviews={reviews}
        />
      )}
    </section>
  );
}

function DoctorDashboard({
  onNavigate,
  recentCases,
  reviews,
}: {
  onNavigate: (page: PageKey) => void;
  recentCases: CaseListItem[];
  reviews: CaseReview[];
}) {
  return (
    <div className="split-layout">
      <div className="panel action-panel">
        <h3>Luồng làm việc hôm nay</h3>
        <p className="muted">
          Bắt đầu bằng phân tích ảnh mới, sau đó mở lịch sử để xác nhận kết quả.
        </p>
        <div className="quick-actions">
          <button className="primary" onClick={() => onNavigate("analyze")} type="button">
            Phân tích ảnh mới
          </button>
          <button onClick={() => onNavigate("cases")} type="button">
            Mở lịch sử ca
          </button>
          <button onClick={() => onNavigate("reviews")} type="button">
            Duyệt {reviews.length} ca cần xác nhận
          </button>
        </div>
      </div>

      <RecentCasesPanel cases={recentCases} />
    </div>
  );
}

function AdminDashboard({
  monitoring,
  onNavigate,
  recentCases,
  reviews,
}: {
  monitoring: MonitoringSummary | null;
  onNavigate: (page: PageKey) => void;
  recentCases: CaseListItem[];
  reviews: CaseReview[];
}) {
  return (
    <>
      <div className="admin-grid">
        <div className="panel">
          <div className="section-heading">
            <div>
              <h3>Sức khỏe hệ thống</h3>
              <p className="muted">Tín hiệu vận hành chính từ backend và queue.</p>
            </div>
            <button onClick={() => onNavigate("monitoring")} type="button">
              Mở monitoring
            </button>
          </div>
          <div className="health-list">
            <HealthItem label="Backend" value={monitoring?.backend_status ?? "unknown"} />
            <HealthItem
              label="Database"
              value={monitoring?.database_reachable ? "ok" : "unreachable"}
            />
            <HealthItem label="Redis" value={monitoring?.redis_broker_status ?? "unknown"} />
            <HealthItem
              label="Celery queue"
              value={String(monitoring?.celery_queue_length ?? "unknown")}
            />
          </div>
        </div>

        <div className="panel">
          <div className="section-heading">
            <div>
              <h3>Model đang hoạt động</h3>
              <p className="muted">Model dùng cho các ca inference mới.</p>
            </div>
            <button onClick={() => onNavigate("models")} type="button">
              Quản lý model
            </button>
          </div>
          {monitoring?.active_model ? (
            <dl className="detail-list compact">
              <div>
                <dt>Name</dt>
                <dd>{monitoring.active_model.model_name}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{monitoring.active_model.version}</dd>
              </div>
              <div>
                <dt>F1</dt>
                <dd>{monitoring.active_model.f1_score ?? "-"}</dd>
              </div>
            </dl>
          ) : (
            <Message tone="warning">Chưa có active model. Hãy seed hoặc kích hoạt model.</Message>
          )}
        </div>
      </div>

      <div className="split-layout">
        <div className="panel action-panel">
          <h3>Việc cần xử lý</h3>
          <p className="muted">
            Ưu tiên review các ca chưa xác nhận trước khi export manifest hoặc retraining.
          </p>
          <div className="quick-actions">
            <button className="primary" onClick={() => onNavigate("reviews")} type="button">
              Duyệt {reviews.length} ca cần xác nhận
            </button>
            <button onClick={() => onNavigate("cases")} type="button">
              Xem tất cả ca
            </button>
            <button onClick={() => onNavigate("users")} type="button">
              Quản lý người dùng
            </button>
          </div>
        </div>

        <RecentCasesPanel cases={recentCases} />
      </div>
    </>
  );
}

function RecentCasesPanel({ cases }: { cases: CaseListItem[] }) {
  return (
    <div className="panel">
      <h3>Ca gần đây</h3>
      <div className="status-table">
        {cases.map((item) => (
          <div key={item.case_id}>
            <span title={item.case_id}>
              {item.patient_name} ({compactId(item.case_id)})
            </span>
            <StatusBadge value={item.status} />
            <strong>{item.review_status ?? "Chưa xác nhận"}</strong>
          </div>
        ))}
        {cases.length === 0 && <p className="muted">Chưa có ca chụp.</p>}
      </div>
    </div>
  );
}

function HealthItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="health-item">
      <span>{label}</span>
      <StatusBadge value={value} />
    </div>
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
