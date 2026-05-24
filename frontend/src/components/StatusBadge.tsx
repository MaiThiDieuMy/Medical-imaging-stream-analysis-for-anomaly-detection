import { formatStatusLabel } from "../utils/format";

type StatusBadgeProps = {
  value: string | boolean | null | undefined;
};

export function StatusBadge({ value }: StatusBadgeProps) {
  const label = value === true ? "true" : value === false ? "false" : value ?? "-";
  const normalized = String(label).toLowerCase();
  const tone =
    normalized === "completed" ||
    normalized === "active" ||
    normalized === "connected" ||
    normalized === "ok" ||
    normalized === "clear" ||
    normalized === "positive" ||
    normalized === "mlops_ready" ||
    normalized === "true" ||
    normalized === "confirmed" ||
    normalized === "corrected" ||
    normalized === "dự đoán chính"
      ? "positive"
      : normalized === "failed" ||
          normalized === "false" ||
          normalized === "missing" ||
          normalized === "unavailable" ||
          normalized === "unreachable" ||
          normalized === "inactive"
        ? "negative"
        : normalized === "pending" ||
          normalized === "queued" ||
            normalized === "processing" ||
            normalized === "mlops_loading" ||
            normalized === "mlops_not_ready" ||
            normalized === "draft" ||
            normalized === "archived"
          ? "warning"
          : "neutral";

  return <span className={`status-badge ${tone}`}>{formatStatusLabel(value)}</span>;
}
