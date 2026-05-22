import { useEffect, useState } from "react";
import { getMonitoringSummary } from "../api/client";
import { Message } from "../components/Message";
import { StatusBadge } from "../components/StatusBadge";
import type { MonitoringSummary } from "../types/api";

type MonitoringTab = "overview" | "infrastructure" | "logs" | "troubleshooting";

const TABS: Array<{ key: MonitoringTab; label: string }> = [
  { key: "overview", label: "Tổng quan" },
  { key: "infrastructure", label: "Hạ tầng" },
  { key: "logs", label: "Logs" },
  { key: "troubleshooting", label: "Xử lý sự cố" },
];

const INFRASTRUCTURE_LINKS = [
  {
    label: "Prometheus",
    href: "http://localhost:9090",
    description: "Kiểm tra targets, alerts và truy vấn PromQL.",
  },
  {
    label: "Grafana",
    href: "http://localhost:3000",
    description: "Xem dashboard hệ thống, ứng dụng, Celery/Redis và logs.",
  },
  {
    label: "cAdvisor",
    href: "http://localhost:8080",
    description: "Theo dõi CPU, memory và runtime metrics của container.",
  },
  {
    label: "Flower",
    href: "http://localhost:5555",
    description: "Theo dõi Celery worker và task queue.",
  },
  {
    label: "RedisInsight",
    href: "http://localhost:5540",
    description: "Kiểm tra Redis broker và result backend.",
  },
  {
    label: "MinIO Console",
    href: "http://localhost:9001",
    description: "Kiểm tra bucket ảnh X-quang đã upload.",
  },
  {
    label: "MLflow",
    href: "http://localhost:5000",
    description: "Theo dõi runs, artifacts và model registry metadata.",
  },
];

const DASHBOARD_LINKS = [
  {
    label: "System Overview",
    href: "http://localhost:3000/d/system-overview/system-overview?orgId=1",
  },
  {
    label: "Application Overview",
    href: "http://localhost:3000/d/application-overview/application-overview?orgId=1",
  },
  {
    label: "Celery And Redis",
    href: "http://localhost:3000/d/celery-redis/celery-and-redis?orgId=1",
  },
  {
    label: "Logs Overview",
    href: "http://localhost:3000/d/logs-overview/logs-overview?orgId=1",
  },
  {
    label: "PostgreSQL And MinIO",
    href: "http://localhost:3000/d/postgres-minio/postgresql-and-minio?orgId=1",
  },
];

export function MonitoringPage() {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<MonitoringTab>("overview");

  async function refreshSummary() {
    setError(null);
    setLoading(true);
    try {
      setSummary(await getMonitoringSummary());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Không tải được monitoring.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshSummary();
  }, []);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h2>Monitoring</h2>
          <p>
            Summary vận hành trong app. Dùng Grafana/Prometheus khi cần phân tích
            sâu hơn.
          </p>
        </div>
        <div className="actions">
          <a className="button-link" href="http://localhost:9090/targets" rel="noreferrer" target="_blank">
            Prometheus targets
          </a>
          <a className="button-link" href="http://localhost:3000" rel="noreferrer" target="_blank">
            Grafana
          </a>
          <button disabled={loading} onClick={() => void refreshSummary()} type="button">
            {loading ? "Đang tải..." : "Tải lại"}
          </button>
        </div>
      </div>

      <div className="tab-list" role="tablist" aria-label="Monitoring sections">
        {TABS.map((tab) => (
          <button
            className={activeTab === tab.key ? "active" : ""}
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && <Message tone="error">{error}</Message>}

      {activeTab === "overview" && <OverviewTab summary={summary} />}
      {activeTab === "infrastructure" && <InfrastructureTab />}
      {activeTab === "logs" && <LogsTab />}
      {activeTab === "troubleshooting" && <TroubleshootingTab summary={summary} />}
    </section>
  );
}

function OverviewTab({ summary }: { summary: MonitoringSummary | null }) {
  if (!summary) {
    return (
      <div className="panel empty-state">
        <strong>Chưa có monitoring summary</strong>
        <p>Thử tải lại hoặc kiểm tra backend tại cổng 8000.</p>
      </div>
    );
  }

  return (
    <>
      <div className="summary-grid">
        <SummaryItem label="Backend" value={summary.backend_status} />
        <SummaryItem
          label="Database"
          value={summary.database_reachable ? "ok" : "unreachable"}
        />
        <SummaryItem label="Redis broker" value={summary.redis_broker_status} />
        <SummaryItem
          label="Celery queue"
          value={summary.celery_queue_length ?? "unknown"}
        />
        <SummaryItem label="Total cases" value={summary.total_cases} />
        <SummaryItem label="Pending reviews" value={summary.pending_reviews} />
        <SummaryItem label="Training-ready" value={summary.training_ready_cases} />
      </div>

      <div className="split-layout">
        <div className="panel">
          <h3>Active model</h3>
          {summary.active_model ? (
            <dl className="detail-list">
              <div>
                <dt>Name</dt>
                <dd>{summary.active_model.model_name}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{summary.active_model.version}</dd>
              </div>
              <div>
                <dt>F1</dt>
                <dd>{summary.active_model.f1_score ?? "-"}</dd>
              </div>
            </dl>
          ) : (
            <Message tone="warning">Chưa có active model.</Message>
          )}
        </div>

        <div className="panel">
          <h3>Runtime metrics</h3>
          <KeyValueTable values={summary.metrics} />
        </div>
      </div>

      <div className="split-layout">
        <div className="panel">
          <h3>Jobs by status</h3>
          <StatusTable values={summary.total_jobs_by_status} />
        </div>
        <div className="panel">
          <h3>Reviews by status</h3>
          <StatusTable values={summary.reviews_by_status} />
        </div>
      </div>
    </>
  );
}

function InfrastructureTab() {
  return (
    <>
      <div className="panel">
        <h3>Grafana dashboards</h3>
        <p className="muted">Các dashboard đã được provision sẵn bằng Prometheus và Loki.</p>
        <div className="link-grid">
          {DASHBOARD_LINKS.map((link) => (
            <a className="link-card" href={link.href} key={link.href} rel="noreferrer" target="_blank">
              <strong>{link.label}</strong>
              <span>Mở dashboard</span>
            </a>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Operations tools</h3>
        <div className="link-grid">
          {INFRASTRUCTURE_LINKS.map((link) => (
            <a className="link-card" href={link.href} key={link.href} rel="noreferrer" target="_blank">
              <strong>{link.label}</strong>
              <span>{link.description}</span>
            </a>
          ))}
        </div>
      </div>
    </>
  );
}

function LogsTab() {
  return (
    <div className="split-layout">
      <div className="panel">
        <h3>Log dashboards</h3>
        <p className="muted">
          Promtail đọc Docker logs và đẩy vào Loki. Dùng Grafana Explore để lọc
          theo service như backend, celery_worker, postgres hoặc minio.
        </p>
        <div className="actions">
          <a
            className="button-link"
            href="http://localhost:3000/d/logs-overview/logs-overview?orgId=1"
            rel="noreferrer"
            target="_blank"
          >
            Logs dashboard
          </a>
          <a className="button-link" href="http://localhost:3000/explore?orgId=1" rel="noreferrer" target="_blank">
            Grafana Explore
          </a>
          <a className="button-link" href="http://localhost:3100/ready" rel="noreferrer" target="_blank">
            Loki ready
          </a>
        </div>
      </div>

      <div className="panel">
        <h3>Log queries gợi ý</h3>
        <div className="code-list">
          <code>{'{service="backend"}'}</code>
          <code>{'{service="celery_worker"}'}</code>
          <code>{'{service="backend"} |= "cache hit"'}</code>
          <code>{'{service="celery_worker"} |= "Worker failed job"'}</code>
        </div>
      </div>
    </div>
  );
}

function TroubleshootingTab({ summary }: { summary: MonitoringSummary | null }) {
  return (
    <div className="panel">
      <h3>Checklist vận hành</h3>
      <div className="checklist">
        <CheckItem
          label="Backend API"
          value={summary?.backend_status ?? "unknown"}
          hint="Nếu lỗi, mở /health, /docs và logs service backend."
        />
        <CheckItem
          label="Database"
          value={summary?.database_reachable ? "ok" : "unreachable"}
          hint="Nếu unreachable, kiểm tra postgres health và alembic upgrade."
        />
        <CheckItem
          label="Redis / Celery"
          value={summary?.redis_broker_status ?? "unknown"}
          hint="Nếu job queued lâu, mở Flower và kiểm tra celery_worker logs."
        />
        <CheckItem
          label="Queue backlog"
          value={summary?.celery_queue_length ?? "unknown"}
          hint="Nếu queue tăng liên tục, kiểm tra worker, model checkpoint và Redis."
        />
        <CheckItem
          label="Cache counters"
          value={
            summary
              ? `${summary.metrics.analyze_cache_hits_total ?? 0} hit / ${
                  summary.metrics.analyze_cache_misses_total ?? 0
                } miss`
              : "unknown"
          }
          hint="Cache hit không tạo case/job mới; nếu nghi ngờ, kiểm tra case history."
        />
      </div>
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

function StatusTable({ values }: { values: Record<string, number> }) {
  return (
    <div className="status-table">
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <span>{key}</span>
          <StatusBadge value={value > 0 ? key : "none"} />
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function KeyValueTable({ values }: { values: Record<string, number> }) {
  if (Object.keys(values).length === 0) {
    return <p className="muted">Chưa có request metric trong process hiện tại.</p>;
  }
  return (
    <div className="status-table">
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <span>{key}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function CheckItem({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | string;
  hint: string;
}) {
  return (
    <div>
      <strong>{label}</strong>
      <span>{value}</span>
      <small>{hint}</small>
    </div>
  );
}
