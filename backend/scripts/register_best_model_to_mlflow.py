from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.schemas.admin import MLflowLocalCheckpointRegisterRequest  # noqa: E402
from app.services.model_admin import ModelAdminService, ModelAdminServiceError  # noqa: E402

DOCKER_MODEL_PATH = Path("/app/artifacts/models/best_model.pth")
LOCAL_MODEL_PATH = Path("artifacts/models/best_model.pth")


def _default_model_path() -> str:
    if settings.model_weights_path:
        return settings.model_weights_path
    if DOCKER_MODEL_PATH.exists():
        return str(DOCKER_MODEL_PATH)
    return str(LOCAL_MODEL_PATH)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register the local MobileNetV3-Small checkpoint to MLflow."
    )
    parser.add_argument("--model-path", default=_default_model_path())
    parser.add_argument(
        "--model-name",
        default=settings.mlflow_registered_model_name,
        help="AIModel metadata name. MLflow registry name comes from config.",
    )
    parser.add_argument("--version", default="kaggle-best-v1")
    parser.add_argument(
        "--architecture",
        default=settings.model_architecture or "mobilenet_v3_small",
    )
    parser.add_argument("--task-type", default="multi_class", choices=["multi_class"])
    parser.add_argument("--accuracy", type=float, default=0.0)
    parser.add_argument("--precision-score", type=float, default=0.0)
    parser.add_argument("--recall-score", type=float, default=0.0)
    parser.add_argument("--f1-score", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = MLflowLocalCheckpointRegisterRequest(
        model_name=args.model_name,
        version=args.version,
        model_path=args.model_path,
        architecture=args.architecture,
        task_type=args.task_type,
        accuracy=args.accuracy,
        precision_score=args.precision_score,
        recall_score=args.recall_score,
        f1_score=args.f1_score,
    )

    db = SessionLocal()
    try:
        result = ModelAdminService(db).register_local_checkpoint_with_mlflow(payload)
    except ModelAdminServiceError as exc:
        raise SystemExit(f"MLflow registration failed: {exc.message}") from exc
    finally:
        db.close()

    print("Registered local checkpoint to MLflow")
    print(f"ai_model_id: {result.ai_model.model_id}")
    print(f"model_name: {result.ai_model.model_name}")
    print(f"version: {result.ai_model.version}")
    print(f"mlflow_run_id: {result.run_id}")
    print(f"mlflow_model_uri: {result.model_uri}")
    print(f"registered_model_name: {result.registered_model_name}")
    print(f"mlflow_model_version: {result.mlflow_model_version}")
    print(f"mlflow_ui_url: {result.mlflow_ui_url}")


if __name__ == "__main__":
    main()
