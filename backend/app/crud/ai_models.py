from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_model import AIModel

DEMO_MODEL_NAME = "kaggle-mobilenetv3-small-chest-xray"
DEMO_MODEL_VERSION = "kaggle-v1"
DEMO_MODEL_PATH = "artifacts/models/best_model.pth"


def get_active_model(db: Session) -> AIModel | None:
    return db.execute(
        select(AIModel).where(
            AIModel.is_active.is_(True),
            AIModel.archived_at.is_(None),
        )
    ).scalar_one_or_none()


def list_models(db: Session) -> list[AIModel]:
    return list(
        db.execute(select(AIModel).order_by(AIModel.created_at.desc())).scalars()
    )


def get_model(db: Session, *, model_id: uuid.UUID) -> AIModel | None:
    return db.execute(
        select(AIModel).where(AIModel.model_id == model_id)
    ).scalar_one_or_none()


def get_model_by_name_version(
    db: Session,
    *,
    model_name: str,
    version: str,
) -> AIModel | None:
    return db.execute(
        select(AIModel).where(
            AIModel.model_name == model_name,
            AIModel.version == version,
        )
    ).scalar_one_or_none()


def create_model(
    db: Session,
    *,
    model_name: str,
    version: str,
    model_path: str,
    accuracy: float | None,
    f1_score: float | None,
    precision_score: float | None,
    recall_score: float | None,
    is_active: bool = False,
    mlflow_run_id: str | None = None,
    mlflow_model_uri: str | None = None,
    mlflow_registered_model_name: str | None = None,
    mlflow_model_version: str | None = None,
) -> AIModel:
    model = AIModel(
        model_name=model_name,
        version=version,
        model_path=model_path,
        accuracy=accuracy,
        f1_score=f1_score,
        precision_score=precision_score,
        recall_score=recall_score,
        is_active=is_active,
        mlflow_run_id=mlflow_run_id,
        mlflow_model_uri=mlflow_model_uri,
        mlflow_registered_model_name=mlflow_registered_model_name,
        mlflow_model_version=mlflow_model_version,
    )
    db.add(model)
    db.flush()
    return model


def deactivate_all_models(db: Session) -> None:
    db.execute(update(AIModel).values(is_active=False))
    db.flush()


def activate_model(db: Session, *, model: AIModel) -> AIModel:
    deactivate_all_models(db)
    model.is_active = True
    db.flush()
    return model


def ensure_demo_active_model(db: Session) -> tuple[AIModel, bool]:
    active_model = get_active_model(db)
    if active_model is not None:
        return active_model, False

    demo_model = get_model_by_name_version(
        db,
        model_name=DEMO_MODEL_NAME,
        version=DEMO_MODEL_VERSION,
    )
    created = demo_model is None
    if demo_model is None:
        demo_model = AIModel(
            model_name=DEMO_MODEL_NAME,
            version=DEMO_MODEL_VERSION,
            model_path=DEMO_MODEL_PATH,
            is_active=True,
        )
        db.add(demo_model)
    else:
        demo_model.is_active = True

    db.commit()
    db.refresh(demo_model)
    return demo_model, created
