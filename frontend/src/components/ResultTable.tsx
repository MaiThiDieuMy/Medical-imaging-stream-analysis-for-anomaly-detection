import type { AnalysisResultItem, ReviewResultItem } from "../types/api";
import { formatPercent } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

type ResultTableProps = {
  results: Array<AnalysisResultItem | ReviewResultItem>;
};

export function ResultTable({ results }: ResultTableProps) {
  if (results.length === 0) {
    return (
      <div className="empty-state compact">
        <strong>Chưa có kết quả AI</strong>
        <p>Kết quả sẽ xuất hiện sau khi job inference hoàn tất.</p>
      </div>
    );
  }

  const sortedResults = [...results].sort(
    (left, right) => right.probability - left.probability,
  );
  const topResult = sortedResults[0];

  return (
    <div className="ai-result-card">
      <div className="ai-result-summary">
        <div>
          <span className="eyebrow">AI đề xuất</span>
          <strong>{topResult.label_name}</strong>
          <p>Độ tin cậy {formatPercent(topResult.probability)}</p>
        </div>
        <StatusBadge value={topResult.predicted_positive ? "Dự đoán chính" : "Cần xem lại"} />
      </div>

      <div className="result-list" aria-label="AI result probabilities">
        {sortedResults.map((result) => (
          <div className="result-row" key={result.label_name}>
            <div>
              <strong>{result.label_name}</strong>
              <span>{result.predicted_positive ? "Được AI chọn" : "Không phải nhãn chính"}</span>
            </div>
            <div className="probability-cell">
              <span>{formatPercent(result.probability)}</span>
              <div
                aria-hidden="true"
                className="probability-track"
              >
                <div
                  className={result.predicted_positive ? "positive" : ""}
                  style={{ width: formatPercent(result.probability) }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
