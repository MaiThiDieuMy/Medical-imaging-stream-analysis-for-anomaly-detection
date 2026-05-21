from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.mlops.mlflow_registry import (
    LoggedMLflowModel,
    RegisteredMLflowModelVersion,
    log_local_checkpoint_model,
    register_model_version,
)
from app.models.ai_model import AIModel
from app.models.enums import UserRole
from app.models.user import User


@pytest.fixture()
def client_and_session_factory() -> Generator[
    tuple[TestClient, sessionmaker[Session]],
    None,
    None,
]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


class FakeRun:
    def __init__(self, run_id: str) -> None:
        self.info = SimpleNamespace(run_id=run_id)

    def __enter__(self) -> "FakeRun":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None


class FakeMLflowModule:
    def __init__(self) -> None:
        self.tracking_uri: str | None = None
        self.params: dict[str, str] = {}
        self.metrics: dict[str, float] = {}
        self.artifacts: list[tuple[str, str | None]] = []

    def set_tracking_uri(self, tracking_uri: str) -> None:
        self.tracking_uri = tracking_uri

    def start_run(self, *, experiment_id: str) -> FakeRun:
        assert experiment_id == "exp-1"
        return FakeRun("run-1")

    def log_params(self, params: dict[str, str]) -> None:
        self.params.update(params)

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self.metrics.update(metrics)

    def log_artifact(self, path: str, artifact_path: str | None = None) -> None:
        self.artifacts.append((path, artifact_path))


class FakeMLflowClient:
    def __init__(self) -> None:
        self.registered_model_names: list[str] = []

    def get_experiment_by_name(self, _name: str) -> SimpleNamespace:
        return SimpleNamespace(experiment_id="exp-1")

    def create_experiment(self, _name: str) -> str:
        return "exp-1"

    def create_registered_model(self, name: str) -> None:
        self.registered_model_names.append(name)

    def create_model_version(
        self,
        *,
        name: str,
        source: str,
        run_id: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            version="1",
            source=source,
            run_id=run_id,
            status="READY",
            current_stage="None",
        )


def _seed_admin(db: Session) -> User:
    user = User(
        username="admin_demo",
        password_hash=hash_password("admin123"),
        full_name="Admin Demo",
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin_demo", "password": "admin123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(model_path: Path, *, version: str = "mlflow-v1") -> dict[str, object]:
    return {
        "model_name": "chest-xray-mobilenetv3-small",
        "version": version,
        "model_path": str(model_path),
        "architecture": "mobilenet_v3_small",
        "task_type": "multi_class",
        "accuracy": 0.81,
        "precision_score": 0.82,
        "recall_score": 0.83,
        "f1_score": 0.84,
    }


def test_mlflow_logging_function_builds_expected_params_and_metrics(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "best_model.pth"
    checkpoint.write_bytes(b"fake-checkpoint")
    fake_mlflow = FakeMLflowModule()
    fake_client = FakeMLflowClient()

    logged = log_local_checkpoint_model(
        model_name="chest-xray-mobilenetv3-small",
        version="mlflow-v1",
        model_path=checkpoint,
        architecture="mobilenet_v3_small",
        task_type="multi_class",
        accuracy=0.81,
        precision_score=0.82,
        recall_score=0.83,
        f1_score=0.84,
        tracking_uri="http://mlflow:5000",
        experiment_name="chest-xray-stream-analysis",
        client=fake_client,
        mlflow_module=fake_mlflow,
    )

    assert logged.run_id == "run-1"
    assert logged.model_uri == "runs:/run-1/checkpoint"
    assert fake_mlflow.tracking_uri == "http://mlflow:5000"
    assert fake_mlflow.params["architecture"] == "mobilenet_v3_small"
    assert fake_mlflow.params["task_type"] == "multi_class"
    assert fake_mlflow.params["classes"] == (
        "Atelectasis,Effusion,Infiltration,No_Finding"
    )
    assert fake_mlflow.params["checkpoint_path"] == str(checkpoint)
    assert fake_mlflow.metrics == {
        "accuracy": 0.81,
        "precision_score": 0.82,
        "recall_score": 0.83,
        "f1_score": 0.84,
    }
    assert ("checkpoint" in {artifact_path for _path, artifact_path in fake_mlflow.artifacts})

    registered = register_model_version(
        model_uri=logged.model_uri,
        run_id=logged.run_id,
        registered_model_name="chest-xray-mobilenetv3-small",
        client=fake_client,
    )
    assert registered.version == "1"
    assert registered.name == "chest-xray-mobilenetv3-small"


def test_mlflow_api_rejects_missing_model_path(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_admin(db)

    response = client.post(
        "/api/v1/admin/mlops/mlflow/register-local-checkpoint",
        headers=_auth_header(client),
        json=_payload(tmp_path / "missing.pth"),
    )

    assert response.status_code == 404
    assert "Model checkpoint not found" in response.json()["detail"]


def test_mlflow_api_creates_ai_model_with_fake_checkpoint(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = client_and_session_factory
    checkpoint = tmp_path / "fake_model.pth"
    checkpoint.write_bytes(b"fake-checkpoint")

    def fake_log_local_checkpoint_model(**_kwargs: object) -> LoggedMLflowModel:
        return LoggedMLflowModel(
            run_id="run-123",
            model_uri="runs:/run-123/checkpoint",
            artifact_path="checkpoint",
            experiment_id="exp-1",
        )

    def fake_register_model_version(**_kwargs: object) -> RegisteredMLflowModelVersion:
        return RegisteredMLflowModelVersion(
            name="chest-xray-mobilenetv3-small",
            version="3",
            source="runs:/run-123/checkpoint",
            run_id="run-123",
            status="READY",
            current_stage="None",
        )

    monkeypatch.setattr(
        "app.services.model_admin.log_local_checkpoint_model",
        fake_log_local_checkpoint_model,
    )
    monkeypatch.setattr(
        "app.services.model_admin.register_model_version",
        fake_register_model_version,
    )

    with session_factory() as db:
        _seed_admin(db)

    response = client.post(
        "/api/v1/admin/mlops/mlflow/register-local-checkpoint",
        headers=_auth_header(client),
        json=_payload(checkpoint),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run_id"] == "run-123"
    assert payload["mlflow_model_version"] == "3"
    assert payload["ai_model"]["is_active"] is False
    assert payload["ai_model"]["mlflow_run_id"] == "run-123"

    with session_factory() as db:
        model = db.scalar(
            select(AIModel).where(AIModel.mlflow_run_id == "run-123")
        )
        assert model is not None
        assert model.mlflow_model_uri == "runs:/run-123/checkpoint"
        assert model.mlflow_model_version == "3"
