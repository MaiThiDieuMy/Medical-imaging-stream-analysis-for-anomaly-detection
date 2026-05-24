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
from app.crud.ai_models import create_model, get_active_model
from app.ml.evaluation import evaluate_multiclass_model
from app.ml.evaluation_set import (
    FALLBACK_EVALUATION_SOURCE,
    build_fixed_evaluation_loader,
)
from app.ml.finetune_dataset import FineTuneManifestDataset
from app.ml.model_loader import (
    ARCHITECTURE_MOBILENET_V3_SMALL,
    MODEL_SOURCE_LOCAL,
    build_model_architecture,
    load_model,
)
from app.ml.retraining_dataset import RETRAIN_CLASS_ORDER
from app.mlops.mlflow_registry import ensure_experiment, register_model_version
from app.models.retraining_job import RetrainingJob
from app.services.retraining import RetrainingService
from app.services.retraining import RETRAINING_TRIGGER_MANUAL_FORCE
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _parse_job_id(retraining_job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(retraining_job_id)
    except ValueError as exc:
        raise ValueError(f"Invalid retraining_job_id: {retraining_job_id}") from exc


def _split_dataset(
    dataset: FineTuneManifestDataset,
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
    epochs: int,
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
    for _epoch in range(epochs):
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
    epochs: int,
    evaluation_source: str,
    evaluation_warning: str | None,
    seed_count: int,
    confirmed_count: int,
    total_train_count: int,
    per_class_count: dict[str, int],
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
    try:
        with mlflow.start_run(experiment_id=experiment_id, run_name=run_name) as run:
            mlflow.log_params(
                {
                    "base_model_id": str(job.base_model_id),
                    "architecture": ARCHITECTURE_MOBILENET_V3_SMALL,
                    "task_type": "multi_class",
                    "class_order": ",".join(RETRAIN_CLASS_ORDER),
                    "sample_count": total_train_count,
                    "seed_count": seed_count,
                    "confirmed_count": confirmed_count,
                    "total_train_count": total_train_count,
                    "per_class_count": json.dumps(per_class_count, sort_keys=True),
                    "epochs": epochs,
                    "batch_size": settings.retrain_batch_size,
                    "learning_rate": settings.retrain_learning_rate,
                    "evaluation_source": evaluation_source,
                    "evaluation_warning": evaluation_warning or "",
                }
            )
            mlflow.log_metrics(metrics)
            mlflow.log_artifact(str(manifest_path), artifact_path="manifest")
            mlflow.log_artifact(str(checkpoint_path), artifact_path="checkpoint")
            mlflow.log_artifact(str(class_mapping_path), artifact_path="checkpoint")
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


def _load_mobile_net_for_retraining(base_model_path: str | None) -> tuple[nn.Module, torch.device]:
    device = torch.device(settings.model_device)
    model_path = settings.model_weights_path or base_model_path or ""
    if model_path and Path(model_path).is_file():
        loaded = load_model(
            model_source=MODEL_SOURCE_LOCAL,
            model_path=model_path,
            architecture=ARCHITECTURE_MOBILENET_V3_SMALL,
            device=device,
            allow_demo_model=False,
        )
        return loaded.model, loaded.device

    if not settings.allow_demo_model:
        raise FileNotFoundError(
            "No MobileNetV3-Small checkpoint found for retraining. "
            "Set MODEL_WEIGHTS_PATH or register an active AIModel with model_path."
        )

    logger.warning(
        "No checkpoint found for retraining; using randomly initialized "
        "MobileNetV3-Small for pipeline testing only."
    )
    model = build_model_architecture(ARCHITECTURE_MOBILENET_V3_SMALL)
    model.to(device)
    return model, device


def _combine_warnings(*warnings: str | None) -> str | None:
    active_warnings = [warning for warning in warnings if warning]
    return "; ".join(active_warnings) if active_warnings else None


@celery_app.task(name="app.tasks.retraining.fine_tune_model", bind=True)
def fine_tune_model(
    self,
    retraining_job_id: str,
    epochs: int | None = None,
) -> dict[str, str | bool | None]:
    parsed_job_id = _parse_job_id(retraining_job_id)
    db = SessionLocal()
    service = RetrainingService(db)
    try:
        job = service.get_job(parsed_job_id)
        service.mark_job_running(job)
        manifest_info = service.export_manifest_for_job(job)
        sample_count = int(manifest_info["samples_count"])
        seed_count = int(manifest_info.get("seed_count", 0))
        confirmed_count = int(manifest_info.get("confirmed_count", sample_count))
        total_train_count = int(manifest_info.get("total_train_count", sample_count))
        per_class_count = dict(manifest_info.get("per_class_count", {}))
        if total_train_count <= 0:
            raise ValueError("Retraining job has no fine-tune samples")
        if (
            confirmed_count < job.min_required_samples
            and job.trigger_type != RETRAINING_TRIGGER_MANUAL_FORCE
        ):
            raise ValueError(
                "Not enough confirmed/corrected samples for retraining: "
                f"{confirmed_count}/{job.min_required_samples}"
            )
        manifest_path = Path(str(manifest_info["manifest_path"]))

        dataset = FineTuneManifestDataset(manifest_path)
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
        evaluation_loader, evaluation_status = build_fixed_evaluation_loader(
            batch_size=settings.retrain_batch_size,
        )
        evaluation_source = evaluation_status.evaluation_source
        evaluation_warning = evaluation_status.warning
        if evaluation_loader is None:
            evaluation_loader = validation_loader
            evaluation_source = FALLBACK_EVALUATION_SOURCE
            evaluation_warning = _combine_warnings(
                evaluation_warning,
                warning,
                "Candidate metrics are based on training validation split only.",
            )

        base_model = get_active_model(db)
        if base_model is None:
            raise ValueError("No active model available for retraining")
        model, device = _load_mobile_net_for_retraining(base_model.model_path)
        effective_epochs = epochs or settings.retrain_epochs
        _train_classifier_head(model, train_loader, device=device, epochs=effective_epochs)
        metrics = evaluate_multiclass_model(model, evaluation_loader, device)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        output_dir = Path(settings.retrain_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = output_dir / f"mobilenetv3_retrained_{timestamp}.pth"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "classes": list(RETRAIN_CLASS_ORDER),
                "architecture": ARCHITECTURE_MOBILENET_V3_SMALL,
                "task_type": "multi_class",
                "base_model_id": str(base_model.model_id),
                "sample_count": total_train_count,
                "seed_count": seed_count,
                "confirmed_count": confirmed_count,
                "total_train_count": total_train_count,
                "per_class_count": per_class_count,
                "evaluation_source": evaluation_source,
                "evaluation_warning": evaluation_warning,
            },
            checkpoint_path,
        )

        mlflow_run_id, mlflow_model_uri, mlflow_version = _log_to_mlflow(
            job=job,
            checkpoint_path=checkpoint_path,
            manifest_path=manifest_path,
            metrics=metrics,
            epochs=effective_epochs,
            evaluation_source=evaluation_source,
            evaluation_warning=evaluation_warning,
            seed_count=seed_count,
            confirmed_count=confirmed_count,
            total_train_count=total_train_count,
            per_class_count=per_class_count,
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

        service.mark_job_completed(
            job,
            candidate_model_id=candidate.model_id,
            output_model_path=str(checkpoint_path),
            mlflow_run_id=mlflow_run_id,
            mlflow_model_uri=mlflow_model_uri,
            metrics=metrics,
            warning=evaluation_warning,
        )
        return {
            "retraining_job_id": str(job.retraining_job_id),
            "status": "completed",
            "candidate_model_id": str(candidate.model_id),
            "promoted": False,
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
