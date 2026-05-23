from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import uuid

import torch
from torch import nn
from torch.utils.data import Dataset
from torch.utils.data import DataLoader, Subset, random_split

from app.core.config import settings
from app.core.database import SessionLocal
from app.crud.ai_models import activate_model, create_model, get_active_model
from app.ml.evaluation import evaluate_multiclass_model_report
from app.ml.model_loader import load_model
from app.ml.retraining_dataset import RETRAIN_CLASS_ORDER, RetrainingManifestDataset
from app.mlops.mlflow_registry import ensure_experiment, register_model_version
from app.models.retraining_job import RetrainingJob
from app.services.retraining import RetrainingService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _parse_job_id(retraining_job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(retraining_job_id)
    except ValueError as exc:
        raise ValueError(f"Invalid retraining_job_id: {retraining_job_id}") from exc


def _split_dataset(
    dataset: RetrainingManifestDataset,
) -> tuple[Subset, Subset, str | None]:
    sample_count = len(dataset)
    if sample_count < 2:
        full = Subset(dataset, list(range(sample_count)))
        return full, full, "validation split too small; evaluated on training data"

    validation_count = max(1, int(sample_count * settings.retrain_validation_split))
    if validation_count >= sample_count:
        validation_count = 1
    train_count = sample_count - validation_count
    generator = torch.Generator().manual_seed(42)
    train_dataset, validation_dataset = random_split(
        dataset,
        [train_count, validation_count],
        generator=generator,
    )
    return train_dataset, validation_dataset, None


def _runtime_path(path: str) -> Path:
    configured = Path(path)
    if configured.parts[:2] in {
        ("\\", "app"),
        ("/", "app"),
    }:
        app_relative = Path(*configured.parts[2:])
        for base_path in (Path.cwd(), Path.cwd().parent):
            candidate = base_path / app_relative
            if candidate.exists():
                return candidate
        return app_relative
    return configured


def _training_and_evaluation_datasets(
    dataset: RetrainingManifestDataset,
) -> tuple[Dataset, Dataset, str, str | None]:
    eval_manifest_path = settings.retrain_eval_manifest_path.strip()
    if eval_manifest_path:
        resolved_eval_path = _runtime_path(eval_manifest_path)
        if resolved_eval_path.exists():
            return (
                dataset,
                RetrainingManifestDataset(resolved_eval_path),
                str(resolved_eval_path),
                None,
            )
        train_dataset, validation_dataset, split_warning = _split_dataset(dataset)
        warning_parts = [f"configured eval manifest not found: {eval_manifest_path}"]
        if split_warning:
            warning_parts.append(split_warning)
        return (
            train_dataset,
            validation_dataset,
            "train_manifest_split",
            "; ".join(warning_parts),
        )

    train_dataset, validation_dataset, split_warning = _split_dataset(dataset)
    warning = split_warning or "fixed evaluation manifest not configured; used train manifest split"
    return train_dataset, validation_dataset, "train_manifest_split", warning


def _count_parameters(model: nn.Module, *, trainable: bool) -> int:
    return sum(
        parameter.numel()
        for parameter in model.parameters()
        if parameter.requires_grad is trainable
    )


def _train_classifier_head(
    model: nn.Module,
    train_loader: DataLoader,
    *,
    device: torch.device,
) -> dict[str, int | str]:
    for parameter in model.parameters():
        parameter.requires_grad = False
    classifier = getattr(model, "classifier", None)
    if isinstance(classifier, nn.Module):
        for parameter in classifier.parameters():
            parameter.requires_grad = True
    else:
        for parameter in model.parameters():
            parameter.requires_grad = True

    unfrozen_blocks = 0
    requested_blocks = max(0, settings.retrain_unfreeze_last_blocks)
    feature_extractor = getattr(model, "features", None)
    if requested_blocks and isinstance(feature_extractor, nn.Sequential):
        blocks = list(feature_extractor.children())
        for block in blocks[-requested_blocks:]:
            for parameter in block.parameters():
                parameter.requires_grad = True
        unfrozen_blocks = min(requested_blocks, len(blocks))

    trainable_parameters = [
        parameter for parameter in model.parameters() if parameter.requires_grad
    ]
    if not trainable_parameters:
        raise ValueError("No trainable parameters available for retraining")

    optimizer = torch.optim.Adam(
        trainable_parameters,
        lr=settings.retrain_learning_rate,
    )
    criterion = nn.CrossEntropyLoss()
    model.train()
    for _epoch in range(settings.retrain_epochs):
        for images, labels in train_loader:
            images = images.to(device)
            labels = labels.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
    return {
        "fine_tune_strategy": (
            "classifier_head_plus_last_blocks"
            if unfrozen_blocks
            else "classifier_head_only"
        ),
        "frozen_layers": "all_except_classifier_and_optional_last_blocks",
        "optimizer": "Adam",
        "loss": "CrossEntropyLoss",
        "unfrozen_last_blocks": unfrozen_blocks,
        "trainable_parameters": _count_parameters(model, trainable=True),
        "frozen_parameters": _count_parameters(model, trainable=False),
    }


def _flat_report_metrics(
    report: dict[str, object],
    *,
    prefix: str = "",
) -> dict[str, float]:
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        return {}
    flat: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, (int, float)):
            flat[f"{prefix}{key}"] = float(value)
    for alias, source in {
        "macro_precision": "precision_score",
        "macro_recall": "recall_score",
        "macro_f1": "f1_score",
    }.items():
        value = metrics.get(source)
        if isinstance(value, (int, float)):
            flat[f"{prefix}{alias}"] = float(value)
    per_class = report.get("per_class")
    if isinstance(per_class, dict):
        for class_name, class_metrics in per_class.items():
            if not isinstance(class_metrics, dict):
                continue
            normalized_name = str(class_name).lower().replace(" ", "_")
            for metric_name in ("precision", "recall", "f1_score", "support"):
                metric_value = class_metrics.get(metric_name)
                if isinstance(metric_value, (int, float)):
                    flat[f"{prefix}{normalized_name}_{metric_name}"] = float(metric_value)
    return flat


def _log_to_mlflow(
    *,
    job: RetrainingJob,
    checkpoint_path: Path,
    manifest_path: Path,
    metrics: dict[str, float],
    candidate_report: dict[str, object],
    base_report: dict[str, object] | None,
    training_details: dict[str, int | str],
    evaluation_source: str,
    warning: str | None,
) -> tuple[str | None, str | None, str | None]:
    try:
        import mlflow
    except ImportError:
        logger.warning("MLflow is unavailable; retraining artifacts were saved locally")
        return None, None, None

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    experiment_id = ensure_experiment()
    run_name = f"retrain-{job.retraining_job_id}"
    class_mapping_path = checkpoint_path.with_suffix(".classes.json")
    class_mapping_path.write_text(
        json.dumps(
            {
                "class_order": list(RETRAIN_CLASS_ORDER),
                "display_labels": {"No_Finding": "No Finding"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    training_config_path = checkpoint_path.with_suffix(".training.json")
    evaluation_report_path = checkpoint_path.with_suffix(".evaluation.json")
    label_distribution_path = checkpoint_path.with_suffix(".labels.json")
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    mlflow_metrics = _flat_report_metrics(candidate_report)
    if base_report is not None:
        mlflow_metrics.update(_flat_report_metrics(base_report, prefix="base_"))
    training_config_path.write_text(
        json.dumps(
            {
                "base_model_id": str(job.base_model_id),
                "dataset_manifest_id": (
                    str(job.dataset_manifest_id)
                    if job.dataset_manifest_id is not None
                    else None
                ),
                "dataset_manifest_path": str(manifest_path),
                "architecture": settings.model_architecture,
                "task_type": "multi_class_single_label",
                "metric_average": "macro",
                "fine_tune_strategy": training_details["fine_tune_strategy"],
                "frozen_layers": training_details["frozen_layers"],
                "optimizer": training_details["optimizer"],
                "loss": training_details["loss"],
                "unfrozen_last_blocks": training_details["unfrozen_last_blocks"],
                "trainable_parameters": training_details["trainable_parameters"],
                "frozen_parameters": training_details["frozen_parameters"],
                "epochs": settings.retrain_epochs,
                "batch_size": settings.retrain_batch_size,
                "learning_rate": settings.retrain_learning_rate,
                "validation_split": settings.retrain_validation_split,
                "evaluation_source": evaluation_source,
                "fixed_eval_manifest_path": settings.retrain_eval_manifest_path or None,
                "confirmed_samples_count": manifest_payload.get("confirmed_samples_count"),
                "replay_samples_count": manifest_payload.get("replay_samples_count"),
                "replay_samples_per_class": manifest_payload.get("replay_samples_per_class"),
                "label_names": list(RETRAIN_CLASS_ORDER),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    evaluation_report_path.write_text(
        json.dumps(
            {
                "candidate": candidate_report,
                "base": base_report,
                "metrics": metrics,
                "metric_average": "macro",
                "evaluation_source": evaluation_source,
                "warning": warning,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    label_distribution_path.write_text(
        json.dumps(
            manifest_payload.get("label_distribution", {}),
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        with mlflow.start_run(experiment_id=experiment_id, run_name=run_name) as run:
            mlflow.log_params(
                {
                    "base_model_id": str(job.base_model_id),
                    "base_model_version": (
                        job.base_model.version if job.base_model is not None else ""
                    ),
                    "dataset_manifest_id": (
                        str(job.dataset_manifest_id)
                        if job.dataset_manifest_id is not None
                        else ""
                    ),
                    "dataset_manifest_version": (
                        job.dataset_manifest.version
                        if job.dataset_manifest is not None
                        else ""
                    ),
                    "dataset_manifest_path": str(manifest_path),
                    "architecture": settings.model_architecture,
                    "task_type": "multi_class_single_label",
                    "metric_average": "macro",
                    "fine_tune_strategy": training_details["fine_tune_strategy"],
                    "frozen_layers": training_details["frozen_layers"],
                    "optimizer": training_details["optimizer"],
                    "loss": training_details["loss"],
                    "unfrozen_last_blocks": training_details["unfrozen_last_blocks"],
                    "trainable_parameters": training_details["trainable_parameters"],
                    "frozen_parameters": training_details["frozen_parameters"],
                    "evaluation_source": evaluation_source,
                    "fixed_eval_manifest_path": settings.retrain_eval_manifest_path,
                    "confirmed_samples_count": manifest_payload.get("confirmed_samples_count", ""),
                    "replay_samples_count": manifest_payload.get("replay_samples_count", ""),
                    "replay_samples_per_class": manifest_payload.get("replay_samples_per_class", ""),
                    "training_samples_count": job.training_samples_count,
                    "epochs": settings.retrain_epochs,
                    "batch_size": settings.retrain_batch_size,
                    "learning_rate": settings.retrain_learning_rate,
                    "validation_split": settings.retrain_validation_split,
                    "label_names": ",".join(RETRAIN_CLASS_ORDER),
                }
            )
            mlflow.set_tags(
                {
                    "project": "medical-imaging-stream-analysis",
                    "task": "chest-xray-classification",
                    "stage": "candidate",
                    "created_by": (
                        str(job.triggered_by_id)
                        if job.triggered_by_id is not None
                        else ""
                    ),
                }
            )
            mlflow.log_metrics(mlflow_metrics or metrics)
            mlflow.log_artifact(str(manifest_path), artifact_path="manifest")
            mlflow.log_artifact(str(checkpoint_path), artifact_path="checkpoint")
            mlflow.log_artifact(str(class_mapping_path), artifact_path="checkpoint")
            mlflow.log_artifact(str(training_config_path), artifact_path="training")
            mlflow.log_artifact(str(evaluation_report_path), artifact_path="evaluation")
            mlflow.log_artifact(str(label_distribution_path), artifact_path="manifest")
            run_id = str(getattr(run.info, "run_id"))
        model_uri = f"runs:/{run_id}/checkpoint"
        registered = register_model_version(
            model_uri=model_uri,
            run_id=run_id,
            registered_model_name=settings.mlflow_registered_model_name,
        )
        return run_id, model_uri, registered.version
    finally:
        class_mapping_path.unlink(missing_ok=True)
        training_config_path.unlink(missing_ok=True)
        evaluation_report_path.unlink(missing_ok=True)
        label_distribution_path.unlink(missing_ok=True)


@celery_app.task(name="app.tasks.retraining.fine_tune_model", bind=True)
def fine_tune_model(self, retraining_job_id: str) -> dict[str, str | bool | None]:
    parsed_job_id = _parse_job_id(retraining_job_id)
    db = SessionLocal()
    service = RetrainingService(db)
    try:
        job = service.get_job(parsed_job_id)
        service.mark_job_running(job)
        if not job.manifest_path:
            raise ValueError("Retraining job has no dataset manifest path")
        manifest_path = Path(job.manifest_path)

        dataset = RetrainingManifestDataset(manifest_path)
        train_dataset, validation_dataset, evaluation_source, warning = (
            _training_and_evaluation_datasets(dataset)
        )
        train_loader = DataLoader(
            train_dataset,
            batch_size=settings.retrain_batch_size,
            shuffle=True,
        )
        validation_loader = DataLoader(
            validation_dataset,
            batch_size=settings.retrain_batch_size,
            shuffle=False,
        )

        base_model = get_active_model(db)
        if base_model is None:
            raise ValueError("No active model available for retraining")
        loaded = load_model(
            model_source=settings.model_source,
            model_path=settings.model_weights_path or base_model.model_path,
            architecture=settings.model_architecture,
            device=settings.model_device,
            allow_demo_model=settings.allow_demo_model,
        )
        model = loaded.model
        device = loaded.device
        base_report = evaluate_multiclass_model_report(
            model,
            validation_loader,
            device,
            class_names=list(RETRAIN_CLASS_ORDER),
        )
        training_details = _train_classifier_head(model, train_loader, device=device)
        service.mark_job_evaluating(job)
        candidate_report = evaluate_multiclass_model_report(
            model,
            validation_loader,
            device,
            class_names=list(RETRAIN_CLASS_ORDER),
        )
        raw_metrics = candidate_report["metrics"]
        if not isinstance(raw_metrics, dict):
            raise ValueError("Evaluation report did not return metrics")
        metrics = {
            "accuracy": float(raw_metrics["accuracy"]),
            "precision_score": float(raw_metrics["precision_score"]),
            "recall_score": float(raw_metrics["recall_score"]),
            "f1_score": float(raw_metrics["f1_score"]),
        }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        output_dir = Path(settings.retrain_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = output_dir / f"retrained_{timestamp}.pth"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "classes": list(RETRAIN_CLASS_ORDER),
            },
            checkpoint_path,
        )

        service.mark_job_registering(job)
        mlflow_run_id, mlflow_model_uri, mlflow_version = _log_to_mlflow(
            job=job,
            checkpoint_path=checkpoint_path,
            manifest_path=manifest_path,
            metrics=metrics,
            candidate_report=candidate_report,
            base_report=base_report,
            training_details=training_details,
            evaluation_source=evaluation_source,
            warning=warning,
        )
        candidate = create_model(
            db,
            model_name=settings.mlflow_registered_model_name,
            version=f"rt-{timestamp}",
            model_path=str(checkpoint_path),
            accuracy=metrics["accuracy"],
            precision_score=metrics["precision_score"],
            recall_score=metrics["recall_score"],
            f1_score=metrics["f1_score"],
            is_active=False,
            mlflow_run_id=mlflow_run_id,
            mlflow_model_uri=mlflow_model_uri,
            mlflow_registered_model_name=settings.mlflow_registered_model_name,
            mlflow_model_version=mlflow_version,
        )
        promoted = False
        raw_base_metrics = base_report.get("metrics")
        base_eval_metrics = raw_base_metrics if isinstance(raw_base_metrics, dict) else {}
        base_f1_score = base_eval_metrics.get("f1_score")
        base_recall_score = base_eval_metrics.get("recall_score")
        candidate_recall_score = candidate.recall_score
        if (
            settings.auto_promote_retrained_model
            and isinstance(base_f1_score, (int, float))
            and isinstance(base_recall_score, (int, float))
            and candidate.f1_score is not None
            and candidate_recall_score is not None
            and candidate.f1_score >= float(base_f1_score)
            and candidate_recall_score
            >= float(base_recall_score) - settings.promotion_max_recall_drop
        ):
            activate_model(db, model=candidate)
            promoted = True

        service.mark_job_completed(
            job,
            candidate_model_id=candidate.model_id,
            output_model_path=str(checkpoint_path),
            mlflow_run_id=mlflow_run_id,
            mlflow_model_uri=mlflow_model_uri,
            metrics=metrics,
            warning=warning,
        )
        return {
            "retraining_job_id": str(job.retraining_job_id),
            "status": "completed",
            "candidate_model_id": str(candidate.model_id),
            "promoted": promoted,
            "mlflow_run_id": mlflow_run_id,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Fine-tune job failed: retraining_job_id=%s", retraining_job_id)
        try:
            job = service.get_job(parsed_job_id)
            service.mark_job_failed(job, exc)
        except Exception:
            logger.exception("Failed to mark retraining job failed: %s", retraining_job_id)
        raise
    finally:
        db.close()
