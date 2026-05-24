import { describe, expect, it } from "vitest";
import {
  compactId,
  formatArchiveStatus,
  formatCacheStatus,
  formatDateTime,
  formatPercent,
  formatProcessingStatus,
  formatReviewReason,
  formatReviewStatus,
} from "./format";

describe("format utilities", () => {
  it("formats probabilities as percentages", () => {
    expect(formatPercent(0.8234)).toBe("82.3%");
    expect(formatPercent(null)).toBe("-");
  });

  it("compacts long ids", () => {
    expect(compactId("12345678-aaaa-bbbb-cccc-123456789abc")).toBe(
      "12345678...9abc",
    );
  });

  it("formats date time safely", () => {
    expect(formatDateTime(null)).toBe("-");
    expect(formatDateTime("not-a-date")).toBe("not-a-date");
    expect(formatDateTime("2026-05-23T08:30:00Z")).toContain("2026");
  });

  it("formats workflow statuses in Vietnamese", () => {
    expect(formatProcessingStatus("queued")).toBe("Đang chờ");
    expect(formatProcessingStatus("completed")).toBe("Hoàn tất");
    expect(formatReviewStatus("corrected")).toBe("Đã gán nhãn lại");
    expect(formatArchiveStatus("archived")).toBe("Đã lưu trữ");
    expect(formatCacheStatus(true)).toBe("Lấy từ cache");
    expect(formatCacheStatus(false)).toBe("Phân tích mới");
  });

  it("formats review reasons into clinical Vietnamese copy", () => {
    expect(formatReviewReason("Doctor/admin manual confirmation for completed case.")).toBe(
      "Ca đã được bác sĩ/quản trị viên xác nhận thủ công.",
    );
    expect(formatReviewReason("max_probability=0.65 low_confidence_threshold=0.7")).toBe(
      "Độ tin cậy cao nhất thấp hơn ngưỡng yêu cầu, cần bác sĩ xem lại.",
    );
    expect(formatReviewReason("probabilities near decision threshold")).toBe(
      "Một số nhãn nằm gần ngưỡng quyết định nên cần bác sĩ xác nhận.",
    );
    expect(formatReviewReason("unknown reason")).toBe(
      "Ca cần được bác sĩ xem lại trước khi dùng cho huấn luyện.",
    );
  });
});
