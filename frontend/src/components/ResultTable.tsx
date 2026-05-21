import type { AnalysisResultItem, ReviewResultItem } from "../types/api";
import { formatPercent } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

type ResultTableProps = {
  results: Array<AnalysisResultItem | ReviewResultItem>;
};

export function ResultTable({ results }: ResultTableProps) {
  if (results.length === 0) {
    return <p className="muted">Chưa có kết quả.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Nhãn</th>
            <th>Xác suất</th>
            <th>Dương tính</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr key={result.label_name}>
              <td>{result.label_name}</td>
              <td>{formatPercent(result.probability)}</td>
              <td>
                <StatusBadge value={result.predicted_positive} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
