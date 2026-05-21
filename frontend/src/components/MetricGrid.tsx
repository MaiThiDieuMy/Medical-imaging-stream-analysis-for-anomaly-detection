import { formatMetric } from "../utils/format";

type MetricGridProps = {
  metrics: Record<string, number | null | undefined>;
};

const labels: Record<string, string> = {
  accuracy: "Accuracy",
  f1_score: "F1",
  precision_score: "Precision",
  recall_score: "Recall",
};

export function MetricGrid({ metrics }: MetricGridProps) {
  return (
    <div className="metric-grid">
      {Object.entries(metrics).map(([key, value]) => (
        <div className="metric" key={key}>
          <span>{labels[key] ?? key}</span>
          <strong>{formatMetric(value)}</strong>
        </div>
      ))}
    </div>
  );
}
