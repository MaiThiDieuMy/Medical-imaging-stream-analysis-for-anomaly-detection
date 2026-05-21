from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any

from app.core.config import settings

MLFLOW_CLASS_ORDER: tuple[str, ...] = (
    "Atelectasis",
    "Effusion",
    "Infiltration",
    "No_Finding",
)
MLFLOW_DISPLAY_LABELS: dict[str, str] = {
    "No_Finding": "No Finding",
}
CHECKPOINT_ARTIFACT_PATH = "checkpoint"


@dataclass(frozen=True)
class LoggedMLflowModel:
    run_id: str
    model_uri: str
    artifact_path: str
    experiment_id: str


@dataclass(frozen=True)
class RegisteredMLflowModelVersion:
    name: str
    version: str | None
    source: str | None
    run_id: str | None
    status: str | None = None
    current_stage: str | None = None


def _import_mlflow() -> tuple[Any, type[Any]]:
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError as exc:
        raise RuntimeError(
            "MLflow is not installed in this environment. "
            "Install backend requirements or use the Docker backend image."
        ) from exc
    return mlflow, MlflowClient


def _object_attr(obj: object, name: str, default: object | None = None) -> object | None:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def get_mlflow_client(
    *,
    tracking_uri: str | None = None,
    client: object | None = None,
) -> object:
    if client is not None:
        return client
    mlflow, client_class = _import_mlflow()
    mlflow.set_tracking_uri(tracking_uri or settings.mlflow_tracking_uri)
    return client_class(tracking_uri=tracking_uri or settings.mlflow_tracking_uri)


def ensure_experiment(
    *,
    experiment_name: str | None = None,
    tracking_uri: str | None = None,
    client: object | None = None,
    mlflow_module: object | None = None,
) -> str:
    target_name = experiment_name or settings.mlflow_experiment_name
    if mlflow_module is None:
        mlflow, _client_class = _import_mlflow()
    else:
        mlflow = mlflow_module
    mlflow.set_tracking_uri(tracking_uri or settings.mlflow_tracking_uri)

    target_client = get_mlflow_client(
        tracking_uri=tracking_uri,
        client=client,
    )
    experiment = target_client.get_experiment_by_name(target_name)
    if experiment is not None:
        return str(_object_attr(experiment, "experiment_id"))
    return str(target_client.create_experiment(target_name))


def _clean_metrics(metrics: dict[str, float | None]) -> dict[str, float]:
    return {
        key: float(value)
        for key, value in metrics.items()
        if value is not None
    }


def _metadata_payload(
    *,
    model_name: str,
    version: str,
    architecture: str,
    task_type: str,
    checkpoint_path: Path,
) -> dict[str, object]:
    return {
        "model_name": model_name,
        "version": version,
        "architecture": architecture,
        "task_type": task_type,
        "class_order": list(MLFLOW_CLASS_ORDER),
        "display_labels": MLFLOW_DISPLAY_LABELS,
        "preprocessing": {
            "resize": "224x224",
            "normalization": "torchvision ImageNet mean/std",
        },
        "checkpoint_path": str(checkpoint_path),
    }


def log_local_checkpoint_model(
    *,
    model_name: str,
    version: str,
    model_path: str | Path,
    architecture: str,
    task_type: str,
    accuracy: float | None,
    precision_score: float | None,
    recall_score: float | None,
    f1_score: float | None,
    tracking_uri: str | None = None,
    experiment_name: str | None = None,
    client: object | None = None,
    mlflow_module: object | None = None,
) -> LoggedMLflowModel:
    checkpoint_path = Path(model_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")
    if not checkpoint_path.is_file():
        raise ValueError(f"Model checkpoint path is not a file: {checkpoint_path}")

    if mlflow_module is None:
        mlflow, _client_class = _import_mlflow()
    else:
        mlflow = mlflow_module

    resolved_tracking_uri = tracking_uri or settings.mlflow_tracking_uri
    mlflow.set_tracking_uri(resolved_tracking_uri)
    experiment_id = ensure_experiment(
        experiment_name=experiment_name,
        tracking_uri=resolved_tracking_uri,
        client=client,
        mlflow_module=mlflow,
    )

    params = {
        "model_name": model_name,
        "version": version,
        "architecture": architecture,
        "task_type": task_type,
        "classes": ",".join(MLFLOW_CLASS_ORDER),
        "checkpoint_path": str(checkpoint_path),
    }
    metrics = _clean_metrics(
        {
            "accuracy": accuracy,
            "precision_score": precision_score,
            "recall_score": recall_score,
            "f1_score": f1_score,
        }
    )

    with mlflow.start_run(experiment_id=experiment_id) as run:
        mlflow.log_params(params)
        if metrics:
            mlflow.log_metrics(metrics)
        mlflow.log_artifact(str(checkpoint_path), artifact_path=CHECKPOINT_ARTIFACT_PATH)

        metadata = _metadata_payload(
            model_name=model_name,
            version=version,
            architecture=architecture,
            task_type=task_type,
            checkpoint_path=checkpoint_path,
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as metadata_file:
            json.dump(metadata, metadata_file, indent=2)
            metadata_path = Path(metadata_file.name)
        try:
            mlflow.log_artifact(
                str(metadata_path),
                artifact_path=CHECKPOINT_ARTIFACT_PATH,
            )
        finally:
            metadata_path.unlink(missing_ok=True)

        run_id = str(_object_attr(run.info, "run_id"))

    return LoggedMLflowModel(
        run_id=run_id,
        model_uri=f"runs:/{run_id}/{CHECKPOINT_ARTIFACT_PATH}",
        artifact_path=CHECKPOINT_ARTIFACT_PATH,
        experiment_id=experiment_id,
    )


def register_model_version(
    *,
    model_uri: str,
    run_id: str,
    registered_model_name: str | None = None,
    client: object | None = None,
) -> RegisteredMLflowModelVersion:
    target_name = registered_model_name or settings.mlflow_registered_model_name
    target_client = get_mlflow_client(client=client)
    try:
        target_client.create_registered_model(target_name)
    except Exception as exc:
        if "RESOURCE_ALREADY_EXISTS" not in str(exc) and "already exists" not in str(exc):
            raise

    version = target_client.create_model_version(
        name=target_name,
        source=model_uri,
        run_id=run_id,
    )
    return RegisteredMLflowModelVersion(
        name=str(_object_attr(version, "name", target_name)),
        version=(
            str(_object_attr(version, "version"))
            if _object_attr(version, "version") is not None
            else None
        ),
        source=(
            str(_object_attr(version, "source"))
            if _object_attr(version, "source") is not None
            else model_uri
        ),
        run_id=(
            str(_object_attr(version, "run_id"))
            if _object_attr(version, "run_id") is not None
            else run_id
        ),
        status=(
            str(_object_attr(version, "status"))
            if _object_attr(version, "status") is not None
            else None
        ),
        current_stage=(
            str(_object_attr(version, "current_stage"))
            if _object_attr(version, "current_stage") is not None
            else None
        ),
    )


def get_registered_model_versions(
    *,
    registered_model_name: str | None = None,
    client: object | None = None,
) -> list[RegisteredMLflowModelVersion]:
    target_name = registered_model_name or settings.mlflow_registered_model_name
    target_client = get_mlflow_client(client=client)
    versions = target_client.search_model_versions(f"name = '{target_name}'")
    return [
        RegisteredMLflowModelVersion(
            name=str(_object_attr(version, "name", target_name)),
            version=str(_object_attr(version, "version", "")),
            source=(
                str(_object_attr(version, "source"))
                if _object_attr(version, "source") is not None
                else None
            ),
            run_id=(
                str(_object_attr(version, "run_id"))
                if _object_attr(version, "run_id") is not None
                else None
            ),
            status=(
                str(_object_attr(version, "status"))
                if _object_attr(version, "status") is not None
                else None
            ),
            current_stage=(
                str(_object_attr(version, "current_stage"))
                if _object_attr(version, "current_stage") is not None
                else None
            ),
        )
        for version in versions
    ]


def get_experiment_runs(
    *,
    experiment_name: str | None = None,
    client: object | None = None,
) -> tuple[str, list[object]]:
    experiment_id = ensure_experiment(
        experiment_name=experiment_name,
        client=client,
    )
    target_client = get_mlflow_client(client=client)
    runs = target_client.search_runs(
        experiment_ids=[experiment_id],
        order_by=["attributes.start_time DESC"],
    )
    return experiment_id, list(runs)


def transition_model_version_stage(
    *,
    registered_model_name: str,
    version: str,
    stage: str,
    client: object | None = None,
) -> None:
    target_client = get_mlflow_client(client=client)
    transition = getattr(target_client, "transition_model_version_stage", None)
    if transition is None:
        raise NotImplementedError(
            "Installed MLflow client does not support model version stages."
        )
    transition(
        name=registered_model_name,
        version=version,
        stage=stage,
        archive_existing_versions=False,
    )
