from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient
import pytest
import torch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.ml.evaluation import evaluate_multiclass_model
from app.ml.labels import DEMO_LABELS
from app.ml.types import InferenceOutput
from app.models.ai_model import AIModel
from app.models.analysis_result import AnalysisResult
from app.models.case_review import CaseReview
from app.models.confirmed_label import ConfirmedLabel
from app.models.dataset_manifest import DatasetManifest
from app.models.enums import ProcessingStatus, UserRole
from app.models.patient import Patient
from app.models.retraining_job import RetrainingJob
from app.models.user import User
from app.models.xray_case import XRayCase
from app.models.xray_image import XRayImage
from app.services.retraining import RetrainingService
from app.services.reviews import ReviewService, ensure_pending_review_for_outputs


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    original_auto_start = settings.auto_start_retraining_job
    settings.auto_start_retraining_job = False
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        settings.auto_start_retraining_job = original_auto_start


@pytest.fixture()
def client_and_session_factory() -> Generator[
    tuple[TestClient, sessionmaker[Session]],
    None,
    None,
]:
    original_auto_start = settings.auto_start_retraining_job
    settings.auto_start_retraining_job = False
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
        settings.auto_start_retraining_job = original_auto_start


def _seed_user(db: Session, *, role: UserRole = UserRole.ADMIN) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{role.value}_{suffix}",
        password_hash=hash_password("demo123"),
        full_name=f"{role.value.title()} Demo",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header(client: TestClient, user: User) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "demo123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_active_model(db: Session, *, f1_score: float = 0.60) -> AIModel:
    model = AIModel(
        model_name="demo-chest-xray",
        version=f"v-{uuid.uuid4().hex[:8]}",
        model_path="demo://active-model",
        accuracy=f1_score,
        precision_score=f1_score,
        recall_score=f1_score,
        f1_score=f1_score,
        is_active=True,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _seed_completed_case(
    db: Session,
    *,
    positive_label: str = "Effusion",
) -> XRayCase:
    model = db.execute(
        select(AIModel).where(AIModel.is_active.is_(True))
    ).scalar_one_or_none()
    if model is None:
        model = _seed_active_model(db)

    patient = Patient(
        patient_code=f"RET-{uuid.uuid4().hex[:8]}",
        full_name="Retraining Demo Patient",
        gender="unknown",
    )
    case = XRayCase(patient=patient, status=ProcessingStatus.COMPLETED)
    db.add(case)
    db.flush()
    db.add(
        XRayImage(
            case_id=case.case_id,
            file_name="demo.png",
            image_path=f"demo://{case.case_id}.png",
            image_hash=uuid.uuid4().hex,
            file_format="png",
        )
    )
    for label_name in DEMO_LABELS:
        is_positive = label_name == positive_label
        db.add(
            AnalysisResult(
                case_id=case.case_id,
                model_id=model.model_id,
                label_name=label_name,
                probability=0.94 if is_positive else 0.02,
                predicted_positive=is_positive,
            )
        )
    db.commit()
    db.refresh(case)
    return case


def _confirm_case(db: Session, case: XRayCase, user: User | None = None) -> None:
    ReviewService(db).confirm_case_result(
        case.case_id,
        reviewed_by=user.user_id if user is not None else None,
    )


def _low_confidence_outputs() -> list[InferenceOutput]:
    return [
        InferenceOutput("No Finding", 0.42, False),
        InferenceOutput("Effusion", 0.55, True),
        InferenceOutput("Infiltration", 0.49, False),
        InferenceOutput("Atelectasis", 0.20, False),
    ]


def test_high_confidence_prediction_is_not_training_ready_without_confirmation(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 1)
    _seed_completed_case(db_session, positive_label="Effusion")

    service = RetrainingService(db_session)
    summary = service.get_retraining_summary()

    assert service.get_training_ready_samples() == []
    assert summary["training_ready_cases"] == 0
    assert summary["should_trigger_retraining"] is False


def test_pending_low_confidence_review_is_not_training_ready(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 1)
    case = _seed_completed_case(db_session, positive_label="Effusion")
    review = ensure_pending_review_for_outputs(
        db_session,
        case_id=case.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()

    assert review is not None
    assert RetrainingService(db_session).get_training_ready_samples() == []


def test_confirm_result_creates_confirmation_evidence(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 1)
    reviewer = _seed_user(db_session, role=UserRole.USER)
    case = _seed_completed_case(db_session, positive_label="Infiltration")

    review = ReviewService(db_session).confirm_case_result(
        case.case_id,
        reviewed_by=reviewer.user_id,
    )
    labels = db_session.scalars(
        select(ConfirmedLabel).where(ConfirmedLabel.review_id == review.review_id)
    ).all()

    assert review.status == "confirmed"
    assert review.reviewed_by_id == reviewer.user_id
    assert len(labels) == len(DEMO_LABELS)
    assert sum(1 for label in labels if label.confirmed_positive) == 1
    assert RetrainingService(db_session).get_retraining_summary()[
        "should_trigger_retraining"
    ] is True


def test_correct_labels_requires_exactly_one_confirmed_positive(
    db_session: Session,
) -> None:
    case = _seed_completed_case(db_session, positive_label="Effusion")
    service = ReviewService(db_session)

    with pytest.raises(Exception):
        service.correct_case_labels(
            case.case_id,
            labels={label: False for label in DEMO_LABELS},
        )

    review = service.correct_case_labels(
        case.case_id,
        labels={
            "No Finding": True,
            "Effusion": False,
            "Infiltration": False,
            "Atelectasis": False,
        },
    )

    assert review.status == "corrected"
    assert sum(
        1 for label in review.confirmed_labels if label.confirmed_positive
    ) == 1


def test_retraining_manifest_contains_confirmed_or_corrected_cases_only(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "retrain_manifest_dir", str(tmp_path))
    confirmed_case = _seed_completed_case(db_session, positive_label="Effusion")
    _confirm_case(db_session, confirmed_case)
    raw_case = _seed_completed_case(db_session, positive_label="No Finding")
    pending_case = _seed_completed_case(db_session, positive_label="Atelectasis")
    ensure_pending_review_for_outputs(
        db_session,
        case_id=pending_case.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()

    manifest = RetrainingService(db_session).export_manifest_for_job()

    payload = Path(str(manifest["manifest_path"])).read_text(encoding="utf-8")
    assert str(confirmed_case.case_id) in payload
    assert str(raw_case.case_id) not in payload
    assert str(pending_case.case_id) not in payload
    assert manifest["samples_count"] == 1


def test_trigger_retraining_creates_job_and_dispatches_task(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = client_and_session_factory
    dispatched: list[str] = []
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 2)

    from app.tasks.retraining import fine_tune_model

    monkeypatch.setattr(fine_tune_model, "delay", lambda job_id: dispatched.append(job_id))

    with session_factory() as db:
        admin = _seed_user(db, role=UserRole.ADMIN)
        _seed_active_model(db)
        _confirm_case(db, _seed_completed_case(db, positive_label="Effusion"), admin)
        _confirm_case(db, _seed_completed_case(db, positive_label="Atelectasis"), admin)
        headers = _auth_header(client, admin)

    response = client.post(
        "/api/v1/admin/mlops/retraining/trigger",
        headers=headers,
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert dispatched == [payload["retraining_job_id"]]
    with session_factory() as db:
        assert db.scalar(select(RetrainingJob)) is not None


def test_trigger_retraining_rejects_without_enough_confirmed_samples(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = client_and_session_factory
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 2)
    with session_factory() as db:
        admin = _seed_user(db, role=UserRole.ADMIN)
        _seed_active_model(db)
        _confirm_case(db, _seed_completed_case(db, positive_label="Effusion"), admin)
        headers = _auth_header(client, admin)

    response = client.post(
        "/api/v1/admin/mlops/retraining/trigger",
        headers=headers,
    )

    assert response.status_code == 400


def test_hybrid_retraining_triggers_on_new_images_but_trains_cumulative_dataset(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "retrain_manifest_dir", str(tmp_path))
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 2)
    admin = _seed_user(db_session, role=UserRole.ADMIN)
    _seed_active_model(db_session)
    service = RetrainingService(db_session)

    _confirm_case(
        db_session,
        _seed_completed_case(db_session, positive_label="Effusion"),
        admin,
    )
    _confirm_case(
        db_session,
        _seed_completed_case(db_session, positive_label="Atelectasis"),
        admin,
    )
    first_job = service.create_retraining_job(triggered_by=admin.user_id)
    service.mark_job_failed(first_job, Exception("test finished first cycle"))

    summary_after_first_cycle = service.get_retraining_summary()
    assert summary_after_first_cycle["training_ready_cases"] == 2
    assert summary_after_first_cycle["new_training_ready_cases"] == 0
    assert summary_after_first_cycle["should_trigger_retraining"] is False

    _confirm_case(
        db_session,
        _seed_completed_case(db_session, positive_label="Infiltration"),
        admin,
    )
    summary_with_one_new_image = service.get_retraining_summary()
    assert summary_with_one_new_image["training_ready_cases"] == 3
    assert summary_with_one_new_image["new_training_ready_cases"] == 1
    assert summary_with_one_new_image["should_trigger_retraining"] is False

    with pytest.raises(Exception) as exc_info:
        service.create_retraining_job(triggered_by=admin.user_id)
    assert "Not enough new confirmed/corrected cases" in str(exc_info.value)

    _confirm_case(
        db_session,
        _seed_completed_case(db_session, positive_label="No Finding"),
        admin,
    )
    summary_with_two_new_images = service.get_retraining_summary()
    assert summary_with_two_new_images["training_ready_cases"] == 4
    assert summary_with_two_new_images["new_training_ready_cases"] == 2
    assert summary_with_two_new_images["should_trigger_retraining"] is True

    second_job = service.create_retraining_job(triggered_by=admin.user_id)
    manifest = db_session.get(DatasetManifest, second_job.dataset_manifest_id)
    assert manifest is not None
    assert manifest.samples_count == 4
    payload = Path(manifest.manifest_path).read_text(encoding="utf-8")
    assert '"selection_strategy": "hybrid_cumulative_training_new_image_trigger"' in payload
    assert len(json.loads(payload)["samples"]) == 4


def test_evaluate_multiclass_model_returns_expected_metrics() -> None:
    class FixedModel(nn.Module):
        def forward(self, inputs: torch.Tensor) -> torch.Tensor:
            return inputs

    inputs = torch.tensor(
        [
            [10.0, 0.0, 0.0, 0.0],
            [0.0, 10.0, 0.0, 0.0],
            [0.0, 0.0, 10.0, 0.0],
            [0.0, 0.0, 10.0, 0.0],
        ]
    )
    labels = torch.tensor([0, 1, 2, 3])
    loader = DataLoader(TensorDataset(inputs, labels), batch_size=2)

    metrics = evaluate_multiclass_model(FixedModel(), loader, torch.device("cpu"))

    assert metrics["accuracy"] == 0.75
    assert set(metrics) == {"accuracy", "precision_score", "recall_score", "f1_score"}
