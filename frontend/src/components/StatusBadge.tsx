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
    normalized === "positive" ||
    normalized === "true" ||
    normalized === "confirmed" ||
    normalized === "corrected"
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
            normalized === "draft"
          ? "warning"
          : "neutral";

  return <span className={`status-badge ${tone}`}>{String(label)}</span>;
}
