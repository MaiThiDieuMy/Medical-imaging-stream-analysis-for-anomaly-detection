from __future__ import annotations

from collections.abc import Sequence


def _flatten_binary(values: Sequence[bool] | Sequence[Sequence[bool]]) -> list[bool]:
    flattened: list[bool] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            flattened.extend(bool(item) for item in value)
        else:
            flattened.append(bool(value))
    return flattened


def calculate_classification_metrics(
    y_true: Sequence[bool] | Sequence[Sequence[bool]],
    y_pred: Sequence[bool] | Sequence[Sequence[bool]],
) -> dict[str, float]:
    true_values = _flatten_binary(y_true)
    pred_values = _flatten_binary(y_pred)
    if len(true_values) != len(pred_values):
        raise ValueError("y_true and y_pred must have the same number of values")
    if not true_values:
        raise ValueError("At least one label value is required")

    true_positive = sum(1 for truth, pred in zip(true_values, pred_values) if truth and pred)
    true_negative = sum(
        1 for truth, pred in zip(true_values, pred_values) if not truth and not pred
    )
    false_positive = sum(
        1 for truth, pred in zip(true_values, pred_values) if not truth and pred
    )
    false_negative = sum(
        1 for truth, pred in zip(true_values, pred_values) if truth and not pred
    )

    accuracy = (true_positive + true_negative) / len(true_values)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1_score = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    return {
        "accuracy": accuracy,
        "precision_score": precision,
        "recall_score": recall,
        "f1_score": f1_score,
    }
