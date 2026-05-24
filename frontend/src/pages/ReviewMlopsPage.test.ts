import { describe, expect, it } from "vitest";
import type { RetrainingSummary } from "../types/api";
import {
  getAdminRetrainingBadgeValue,
  getAdminSummaryFallbackText,
  shouldShowAdminEmptyState,
} from "./ReviewMlopsPage";
import { formatStatusLabel } from "../utils/format";

const baseSummary: RetrainingSummary = {
  min_confirmed_samples: 5,
  pending_reviews: 0,
  confirmed_reviews: 0,
  corrected_reviews: 0,
  training_ready_cases: 0,
  training_seed_enabled: true,
  training_seed_dir: "/app/artifacts/training_seed",
  training_seed_count: 0,
  total_finetune_samples: 0,
  finetune_per_class_count: {},
  missing_confirmed_samples: 5,
  should_trigger_retraining: false,
  retrain_auto_start: false,
  evaluation_set_available: false,
  evaluation_set_sample_count: 0,
  evaluation_set_dir: "/app/artifacts/evaluation_set",
  evaluation_warning: null,
  running_job: null,
  latest_job: null,
};

describe("admin MLOps loading state helpers", () => {
  it("uses loading copy instead of the old no-summary copy during initial load", () => {
    expect(getAdminSummaryFallbackText(true, null)).toBe(
      "Đang tải điều kiện fine-tune...",
    );
    expect(getAdminSummaryFallbackText(true, null)).not.toBe("Chưa có summary.");
  });

  it("only shows empty review state after initial loading is complete", () => {
    expect(shouldShowAdminEmptyState(true, 0)).toBe(false);
    expect(shouldShowAdminEmptyState(false, 0)).toBe(true);
    expect(shouldShowAdminEmptyState(false, 2)).toBe(false);
  });

  it("formats admin retraining status badge states clearly", () => {
    expect(formatStatusLabel(getAdminRetrainingBadgeValue(true, null))).toBe(
      "Đang tải",
    );
    expect(formatStatusLabel(getAdminRetrainingBadgeValue(false, baseSummary))).toBe(
      "Chưa đủ điều kiện",
    );
    expect(
      formatStatusLabel(
        getAdminRetrainingBadgeValue(false, {
          ...baseSummary,
          should_trigger_retraining: true,
        }),
      ),
    ).toBe("Đủ điều kiện");
  });
});
