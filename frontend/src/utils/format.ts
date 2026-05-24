export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function formatMetric(value: number | null | undefined): string {
  return formatPercent(value);
}

const processingStatusLabels: Record<string, string> = {
  queued: "Đang chờ",
  processing: "Đang xử lý",
  completed: "Hoàn tất",
  failed: "Thất bại",
};

const reviewStatusLabels: Record<string, string> = {
  pending: "Chờ duyệt",
  confirmed: "Đã xác nhận",
  corrected: "Đã gán nhãn lại",
  rejected: "Đã từ chối",
  no_review: "Chưa xác nhận",
};

const archiveStatusLabels: Record<string, string> = {
  active: "Đang hoạt động",
  archived: "Đã lưu trữ",
};

const generalStatusLabels: Record<string, string> = {
  ...processingStatusLabels,
  ...reviewStatusLabels,
  ...archiveStatusLabels,
  clear: "Không còn ca chờ duyệt",
  active: "Đang hoạt động",
  inactive: "Đã khóa",
  connected: "Đã kết nối",
  missing: "Thiếu cấu hình",
  unavailable: "Không khả dụng",
  unreachable: "Không kết nối được",
  unknown: "Chưa rõ",
  "redis-client-unavailable": "Thiếu Redis client",
  ok: "Hoạt động",
  none: "Không có",
  true: "Có",
  false: "Không",
  doctor: "Bác sĩ/KTV",
  admin: "Quản trị viên",
  draft: "Bản nháp",
  positive: "Dương tính",
  "dự đoán chính": "Dự đoán chính",
  "cần xem lại": "Cần xem lại",
  "chưa xác nhận": "Chưa xác nhận",
};

export function formatProcessingStatus(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return processingStatusLabels[value.toLowerCase()] ?? value;
}

export function formatReviewStatus(value: string | null | undefined): string {
  if (!value) {
    return "Chưa xác nhận";
  }
  return reviewStatusLabels[value.toLowerCase()] ?? value;
}

export function formatCacheStatus(value: boolean): string {
  return value ? "Lấy từ cache" : "Phân tích mới";
}

export function formatArchiveStatus(value: "active" | "archived"): string {
  return archiveStatusLabels[value];
}

export function formatStatusLabel(value: string | boolean | null | undefined): string {
  if (value === true) {
    return generalStatusLabels.true;
  }
  if (value === false) {
    return generalStatusLabels.false;
  }
  if (!value) {
    return "-";
  }
  const key = String(value).toLowerCase();
  return generalStatusLabels[key] ?? String(value);
}

export function formatReviewReason(reason: string | null | undefined): string {
  if (!reason?.trim()) {
    return "Ca cần được bác sĩ xem lại trước khi dùng cho huấn luyện.";
  }
  const normalized = reason.toLowerCase();
  if (reason === "Doctor/admin manual confirmation for completed case.") {
    return "Ca đã được bác sĩ/quản trị viên xác nhận thủ công.";
  }
  if (reason === "Doctor/admin manual label correction for completed case.") {
    return "Ca đã được bác sĩ/quản trị viên gán nhãn lại thủ công.";
  }
  if (
    normalized.includes("max_probability") &&
    normalized.includes("low_confidence_threshold")
  ) {
    return "Độ tin cậy cao nhất thấp hơn ngưỡng yêu cầu, cần bác sĩ xem lại.";
  }
  if (normalized.includes("probabilities near decision threshold")) {
    return "Một số nhãn nằm gần ngưỡng quyết định nên cần bác sĩ xác nhận.";
  }
  return "Ca cần được bác sĩ xem lại trước khi dùng cho huấn luyện.";
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function compactId(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  if (value.length <= 12) {
    return value;
  }
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}
