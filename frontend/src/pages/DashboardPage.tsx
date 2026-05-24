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
import type {
  CaseListItem,
  CaseReview,
  MonitoringSummary,
  UserPublic,
} from "../types/api";
import { compactId, formatDateTime, formatMetric } from "../utils/format";
import type { PageKey } from "../utils/navigation";

type DashboardPageProps = {
  currentUser: UserPublic;
  onNavigate: (page: PageKey) => void;
  onOpenCase: (caseId: string) => void;
};

export function DashboardPage({
  currentUser,
  onNavigate,
  onOpenCase,
}: DashboardPageProps) {
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
        const [caseList, reviewList, monitoringSummary, userList] =
          await Promise.all([
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
  const todayCases = useMemo(() => {
    const today = new Date().toDateString();
    return cases.filter((item) => new Date(item.created_at).toDateString() === today)
      .length;
  }, [cases]);

  return (
    <section className="page">
      <div className="dashboard-hero">
        <div>
          <span className="eyebrow">
            {isAdmin ? "Vận hành hệ thống" : "Không gian làm việc lâm sàng"}
          </span>
          <h2>Phân tích ảnh X-quang lồng ngực</h2>
          <p>
            {isAdmin
              ? "Theo dõi hệ thống, hàng đợi inference, model đang hoạt động và các ca cần xử lý."
              : "Theo dõi ca của tôi, mở nhanh lịch sử, xem ảnh và xác nhận nhãn sau khi AI hoàn tất."}
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
        {isAdmin ? (
          <>
            <SummaryItem label="Tổng ca chụp" value={cases.length} />
            <SummaryItem label="Hoàn tất" value={completedCases} />
            <SummaryItem label="Ca cần duyệt" value={reviews.length} />
            <SummaryItem label="Người dùng" value={totalUsers ?? "-"} />
            <SummaryItem
              label="Training-ready"
              value={monitoring?.training_ready_cases ?? "-"}
            />
            <SummaryItem
              label="Queue"
              value={monitoring?.celery_queue_length ?? "Chưa rõ"}
            />
          </>
        ) : (
          <>
            <SummaryItem label="Tổng ca của tôi" value={cases.length} />
            <SummaryItem label="Hoàn tất" value={completedCases} />
            <SummaryItem label="Cần xác nhận" value={reviews.length} />
            <SummaryItem label="Lỗi cần xử lý" value={failedCases} />
            <SummaryItem label="Ca hôm nay" value={todayCases} />
          </>
        )}
      </div>

      {isAdmin ? (
        <AdminDashboard
          monitoring={monitoring}
          onNavigate={onNavigate}
          onOpenCase={onOpenCase}
          recentCases={cases.slice(0, 5)}
          reviews={reviews}
          totalCases={cases.length}
        />
      ) : (
        <DoctorDashboard
          onNavigate={onNavigate}
          onOpenCase={onOpenCase}
          processingCases={processingCases}
          recentCases={cases.slice(0, 5)}
          reviews={reviews}
          totalCases={cases.length}
        />
      )}
    </section>
  );
}

function DoctorDashboard({
  onNavigate,
  onOpenCase,
  processingCases,
  recentCases,
  reviews,
  totalCases,
}: {
  onNavigate: (page: PageKey) => void;
  onOpenCase: (caseId: string) => void;
  processingCases: number;
  recentCases: CaseListItem[];
  reviews: CaseReview[];
  totalCases: number;
}) {
  return (
    <div className="split-layout">
      <div className="panel action-panel">
        <h3>Luồng làm việc hôm nay</h3>
        <p className="muted">
          Bắt đầu bằng ca chụp mới, theo dõi tiến trình AI, sau đó xác nhận hoặc
          gán lại nhãn khi cần.
        </p>
        <div className="shortcut-grid">
          <button
            className="shortcut-card primary"
            onClick={() => onNavigate("analyze")}
            type="button"
          >
            <strong>Phân tích ảnh mới</strong>
            <span>Tạo ca X-quang và gửi ảnh vào hàng đợi AI</span>
          </button>
          <button
            className="shortcut-card"
            onClick={() => onNavigate("cases")}
            type="button"
          >
            <strong>Xem lịch sử ca chụp</strong>
            <span>Mở ảnh, kết quả, báo cáo và trạng thái xác nhận</span>
          </button>
          <button
            className="shortcut-card"
            onClick={() => onNavigate("reviews")}
            type="button"
          >
            <strong>Duyệt ca cần xác nhận</strong>
            <span>{reviews.length} ca đang chờ bác sĩ/KTV xem lại</span>
          </button>
        </div>
        {processingCases > 0 && (
          <div className="inline-status-action">
            <div>
              <strong>{processingCases} ca đang trong hàng đợi/xử lý</strong>
              <span>Theo dõi tiến trình trong lịch sử ca chụp.</span>
            </div>
            <button onClick={() => onNavigate("cases")} type="button">
              Mở lịch sử
            </button>
          </div>
        )}
      </div>

      <RecentCasesPanel
        cases={recentCases}
        onOpenCase={onOpenCase}
        onViewAll={() => onNavigate("cases")}
        totalCases={totalCases}
      />
    </div>
  );
}

function AdminDashboard({
  monitoring,
  onNavigate,
  onOpenCase,
  recentCases,
  reviews,
  totalCases,
}: {
  monitoring: MonitoringSummary | null;
  onNavigate: (page: PageKey) => void;
  onOpenCase: (caseId: string) => void;
  recentCases: CaseListItem[];
  reviews: CaseReview[];
  totalCases: number;
}) {
  return (
    <div className="dashboard-grid">
      <div className="dashboard-column">
        <div className="panel">
          <div className="section-heading">
            <div>
              <h3>Sức khỏe hệ thống</h3>
              <p className="muted">Tín hiệu vận hành chính từ backend và queue.</p>
            </div>
            <button onClick={() => onNavigate("monitoring")} type="button">
              Mở giám sát
            </button>
          </div>
          <div className="health-list">
            <HealthItem label="Backend" value={monitoring?.backend_status ?? "unknown"} />
            <HealthItem
              label="CSDL"
              value={monitoring?.database_reachable ? "ok" : "unreachable"}
            />
            <HealthItem label="Redis" value={monitoring?.redis_broker_status ?? "unknown"} />
            <HealthItem
              label="Hàng đợi Celery"
              value={String(monitoring?.celery_queue_length ?? "Chưa rõ")}
            />
          </div>
        </div>

        <div className="panel action-panel">
          <h3>Việc cần xử lý</h3>
          <p className="muted">
            Ưu tiên duyệt các ca chưa xác nhận trước khi xuất manifest hoặc huấn luyện lại.
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
      </div>

      <div className="dashboard-column">
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
                <dt>Tên model</dt>
                <dd>{monitoring.active_model.model_name}</dd>
              </div>
              <div>
                <dt>Phiên bản</dt>
                <dd>{monitoring.active_model.version}</dd>
              </div>
              <div>
                <dt>F1</dt>
                <dd>{formatMetric(monitoring.active_model.f1_score)}</dd>
              </div>
              <div>
                <dt>Nguồn</dt>
                <dd>{modelSourceLabel(monitoring.active_model)}</dd>
              </div>
            </dl>
          ) : (
            <Message tone="warning">
              Chưa có model đang hoạt động. Hãy seed hoặc kích hoạt model.
            </Message>
          )}
        </div>

        <RecentCasesPanel
          cases={recentCases}
          onOpenCase={onOpenCase}
          onViewAll={() => onNavigate("cases")}
          totalCases={totalCases}
        />
      </div>
    </div>
  );
}

function RecentCasesPanel({
  cases,
  onOpenCase,
  onViewAll,
  totalCases,
}: {
  cases: CaseListItem[];
  onOpenCase: (caseId: string) => void;
  onViewAll: () => void;
  totalCases: number;
}) {
  return (
    <div className="panel">
      <div className="section-heading">
        <div>
          <h3>Ca gần đây</h3>
          <p className="muted">Hiển thị tối đa 5 ca mới nhất.</p>
        </div>
        <div className="actions">
          <span className="count-pill">
            {cases.length}/{totalCases} ca
          </span>
          <button onClick={onViewAll} type="button">
            Xem tất cả ca
          </button>
        </div>
      </div>
      <div className="recent-case-list">
        {cases.map((item) => (
          <div className="recent-case-item" key={item.case_id}>
            <div>
              <strong>{item.patient_name}</strong>
              <span>
                {item.patient_code} · {formatDateTime(item.created_at)} ·{" "}
                {compactId(item.case_id)}
              </span>
            </div>
            <StatusBadge value={item.status} />
            <button onClick={() => onOpenCase(item.case_id)} type="button">
              Xem chi tiết
            </button>
          </div>
        ))}
        {cases.length === 0 && <p className="muted">Chưa có ca chụp.</p>}
      </div>
    </div>
  );
}

function modelSourceLabel(model: MonitoringSummary["active_model"]): string {
  if (!model) {
    return "-";
  }
  return model.mlflow_model_uri || model.mlflow_run_id ? "MLflow" : "Local";
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
