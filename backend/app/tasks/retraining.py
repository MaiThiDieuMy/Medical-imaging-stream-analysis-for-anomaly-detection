from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import uuid

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset, random_split

from app.core.config import settings
from app.core.database import SessionLocal
from app.crud.ai_models import activate_model, create_model, get_active_model
from app.ml.evaluation import evaluate_multiclass_model
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


def _train_classifier_head(
    model: nn.Module,
    train_loader: DataLoader,
    *,
    device: torch.device,
) -> None:
    for parameter in model.parameters():
        parameter.requires_grad = False
    classifier = getattr(model, "classifier", None)
    if isinstance(classifier, nn.Module):
        for parameter in classifier.parameters():
            parameter.requires_grad = True
    else:
        for parameter in model.parameters():
            parameter.requires_grad = True

    trainable_parameters = [
        parameter for parameter in model.parameters() if parameter.requires_grad
    ]
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


def _log_to_mlflow(
    *,
    job: RetrainingJob,
    checkpoint_path: Path,
    manifest_path: Path,
    metrics: dict[str, float],
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
                "task_type": "multi_class",
                "epochs": settings.retrain_epochs,
                "batch_size": settings.retrain_batch_size,
                "learning_rate": settings.retrain_learning_rate,
                "validation_split": settings.retrain_validation_split,
                "label_names": list(RETRAIN_CLASS_ORDER),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    evaluation_report_path.write_text(
        json.dumps({"metrics": metrics, "warning": warning}, indent=2),
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
                    "task_type": "multi_class",
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
            mlflow.log_metrics(metrics)
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
        train_dataset, validation_dataset, warning = _split_dataset(dataset)
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
        _train_classifier_head(model, train_loader, device=device)
        service.mark_job_evaluating(job)
        metrics = evaluate_multiclass_model(model, validation_loader, device)

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
        active = get_active_model(db)
        if (
            settings.auto_promote_retrained_model
            and active is not None
            and (
                active.f1_score is None
                or candidate.f1_score is not None
                and candidate.f1_score >= active.f1_score
            )
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
