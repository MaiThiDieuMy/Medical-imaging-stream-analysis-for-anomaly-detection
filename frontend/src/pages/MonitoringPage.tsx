import { useEffect, useState } from "react";
import { getMonitoringSummary } from "../api/client";
import { Message } from "../components/Message";
import { StatusBadge } from "../components/StatusBadge";
import type { MonitoringSummary } from "../types/api";

export function MonitoringPage() {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
          <p>Thông tin vận hành về backend, database, Redis, job và review.</p>
        </div>
        <div className="actions">
          <a className="button-link" href="http://localhost:3000" rel="noreferrer" target="_blank">
            Grafana
          </a>
          <button disabled={loading} onClick={() => void refreshSummary()} type="button">
            {loading ? "Đang tải..." : "Refresh"}
          </button>
        </div>
      </div>

      {error && <Message tone="error">{error}</Message>}

      {summary ? (
        <>
          <div className="summary-grid">
            <SummaryItem label="Backend" value={summary.backend_status} />
            <SummaryItem
              label="Database"
              value={summary.database_reachable ? "ok" : "unreachable"}
            />
            <SummaryItem label="Redis broker" value={summary.redis_broker_status} />
            <SummaryItem label="Total cases" value={summary.total_cases} />
            <SummaryItem label="Pending reviews" value={summary.pending_reviews} />
            <SummaryItem
              label="Training-ready"
              value={summary.training_ready_cases}
            />
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
                <p className="muted">Chưa có active model.</p>
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
      ) : (
        <div className="panel">
          <p className="muted">Chưa có monitoring summary.</p>
        </div>
      )}
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
