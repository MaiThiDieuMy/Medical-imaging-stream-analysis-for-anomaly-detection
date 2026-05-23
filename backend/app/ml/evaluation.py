from __future__ import annotations

import torch
from torch.utils.data import DataLoader


def _macro_classification_metrics(
    y_true: list[int],
    y_pred: list[int],
    *,
    num_classes: int,
) -> dict[str, float]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    if not y_true:
        raise ValueError("At least one sample is required for evaluation")

    accuracy = sum(
        1 for truth, prediction in zip(y_true, y_pred) if truth == prediction
    ) / len(y_true)

    precision_values: list[float] = []
    recall_values: list[float] = []
    f1_values: list[float] = []
    for class_index in range(num_classes):
        true_positive = sum(
            1
            for truth, prediction in zip(y_true, y_pred)
            if truth == class_index and prediction == class_index
        )
        false_positive = sum(
            1
            for truth, prediction in zip(y_true, y_pred)
            if truth != class_index and prediction == class_index
        )
        false_negative = sum(
            1
            for truth, prediction in zip(y_true, y_pred)
            if truth == class_index and prediction != class_index
        )
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
        precision_values.append(precision)
        recall_values.append(recall)
        f1_values.append(f1_score)

    return {
        "accuracy": accuracy,
        "precision_score": sum(precision_values) / num_classes,
        "recall_score": sum(recall_values) / num_classes,
        "f1_score": sum(f1_values) / num_classes,
    }


def multiclass_evaluation_report(
    y_true: list[int],
    y_pred: list[int],
    *,
    class_names: list[str],
) -> dict[str, object]:
    num_classes = len(class_names)
    metrics = _macro_classification_metrics(
        y_true,
        y_pred,
        num_classes=num_classes,
    )
    per_class: dict[str, dict[str, float | int]] = {}
    confusion_matrix = [
        [0 for _ in range(num_classes)]
        for _ in range(num_classes)
    ]
    for truth, prediction in zip(y_true, y_pred):
        confusion_matrix[truth][prediction] += 1

    for class_index, class_name in enumerate(class_names):
        true_positive = confusion_matrix[class_index][class_index]
        false_positive = sum(
            confusion_matrix[other_index][class_index]
            for other_index in range(num_classes)
            if other_index != class_index
        )
        false_negative = sum(
            confusion_matrix[class_index][other_index]
            for other_index in range(num_classes)
            if other_index != class_index
        )
        support = sum(confusion_matrix[class_index])
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
        per_class[class_name] = {
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "support": support,
        }

    return {
        "metrics": metrics,
        "metric_average": "macro",
        "per_class": per_class,
        "confusion_matrix": confusion_matrix,
        "class_names": class_names,
    }


def evaluate_multiclass_model(
    model: torch.nn.Module,
    dataloader: DataLoader[tuple[torch.Tensor, torch.Tensor]],
    device: torch.device | str,
    *,
    num_classes: int = 4,
) -> dict[str, float]:
    target_device = torch.device(device)
    model.eval()
    true_labels: list[int] = []
    predicted_labels: list[int] = []
    with torch.inference_mode():
        for images, labels in dataloader:
            images = images.to(target_device)
            logits = model(images)
            predictions = torch.argmax(logits, dim=1).detach().cpu().tolist()
            true_labels.extend(int(label) for label in labels.detach().cpu().tolist())
            predicted_labels.extend(int(label) for label in predictions)
    return _macro_classification_metrics(true_labels, predicted_labels, num_classes=num_classes)


def evaluate_multiclass_model_report(
    model: torch.nn.Module,
    dataloader: DataLoader[tuple[torch.Tensor, torch.Tensor]],
    device: torch.device | str,
    *,
    class_names: list[str],
) -> dict[str, object]:
    target_device = torch.device(device)
    model.eval()
    true_labels: list[int] = []
    predicted_labels: list[int] = []
    with torch.inference_mode():
        for images, labels in dataloader:
            images = images.to(target_device)
            logits = model(images)
            predictions = torch.argmax(logits, dim=1).detach().cpu().tolist()
            true_labels.extend(int(label) for label in labels.detach().cpu().tolist())
            predicted_labels.extend(int(label) for label in predictions)
    return multiclass_evaluation_report(
        true_labels,
        predicted_labels,
        class_names=class_names,
    )
