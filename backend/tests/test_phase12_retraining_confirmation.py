from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
from PIL import Image
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
from app.ml.evaluation_set import FixedEvaluationDataset, get_evaluation_set_status
from app.ml.finetune_dataset import (
    FineTuneManifestDataset,
    build_finetune_dataset,
    load_training_seed_samples,
)
from app.ml.labels import DEMO_LABELS
from app.ml.retraining_dataset import RETRAIN_CLASS_ORDER
from app.ml.types import InferenceOutput
from app.models.ai_model import AIModel
from app.models.analysis_result import AnalysisResult
from app.models.case_review import CaseReview
from app.models.confirmed_label import ConfirmedLabel
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
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


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


def _write_test_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), color=(128, 128, 128)).save(path)


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


def test_retraining_summary_uses_configured_n_and_missing_count(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 2)
    monkeypatch.setattr(settings, "evaluation_set_dir", str(tmp_path / "missing"))
    _confirm_case(
        db_session,
        _seed_completed_case(db_session, positive_label="Effusion"),
    )

    summary = RetrainingService(db_session).get_retraining_summary()

    assert summary["min_confirmed_samples"] == 2
    assert summary["training_ready_cases"] == 1
    assert summary["missing_confirmed_samples"] == 1
    assert summary["evaluation_set_available"] is False
    assert summary["evaluation_warning"]


def test_retraining_summary_counts_only_reviews_after_latest_completed_job(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 2)
    monkeypatch.setattr(settings, "evaluation_set_dir", str(tmp_path / "missing"))
    model = _seed_active_model(db_session)
    old_case = _seed_completed_case(db_session, positive_label="Effusion")
    new_case = _seed_completed_case(db_session, positive_label="Atelectasis")
    _confirm_case(db_session, old_case)
    old_review = db_session.scalar(
        select(CaseReview).where(CaseReview.case_id == old_case.case_id)
    )
    assert old_review is not None
    old_review.reviewed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(
        RetrainingJob(
            status="completed",
            trigger_type="manual",
            base_model_id=model.model_id,
            training_samples_count=1,
            min_required_samples=2,
            created_at=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    )
    _confirm_case(db_session, new_case)
    new_review = db_session.scalar(
        select(CaseReview).where(CaseReview.case_id == new_case.case_id)
    )
    assert new_review is not None
    new_review.reviewed_at = datetime(2026, 1, 3, tzinfo=timezone.utc)
    db_session.commit()

    summary = RetrainingService(db_session).get_retraining_summary()

    assert summary["confirmed_reviews"] == 2
    assert summary["training_ready_cases"] == 1
    assert summary["missing_confirmed_samples"] == 1
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
    monkeypatch.setattr(settings, "training_seed_dir", str(tmp_path / "missing_seed"))
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
    assert '"label_index"' in payload
    assert '"label_name": "Effusion"' in payload
    assert manifest["samples_count"] == 1


def test_training_ready_samples_include_label_index_and_skip_multiple_positives(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 1)
    good_case = _seed_completed_case(db_session, positive_label="No Finding")
    _confirm_case(db_session, good_case)
    bad_case = _seed_completed_case(db_session, positive_label="Effusion")
    _confirm_case(db_session, bad_case)
    bad_review = next(
        review
        for review in RetrainingService(db_session).get_training_ready_samples()
        if review.case_id == bad_case.case_id
    )
    for label in bad_review.confirmed_labels:
        if label.label_name == "Atelectasis":
            label.confirmed_positive = True
    db_session.commit()

    samples = RetrainingService(db_session).get_training_ready_sample_items()

    assert len(samples) == 1
    assert samples[0].case_id == good_case.case_id
    assert samples[0].label_name == "No Finding"
    assert samples[0].label_index == 3
    assert samples[0].image_path


def test_start_retraining_creates_job_and_dispatches_task(
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
        "/api/v1/admin/mlops/retraining/start",
        headers=headers,
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert dispatched == [payload["retraining_job_id"]]
    with session_factory() as db:
        assert db.scalar(select(RetrainingJob)) is not None


def test_start_retraining_rejects_without_enough_confirmed_samples(
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
        "/api/v1/admin/mlops/retraining/start",
        headers=headers,
    )

    assert response.status_code == 400


def test_force_start_retraining_allows_small_manual_test_job(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = client_and_session_factory
    dispatched: list[str] = []
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 5)

    from app.tasks.retraining import fine_tune_model

    monkeypatch.setattr(fine_tune_model, "delay", lambda job_id: dispatched.append(job_id))

    with session_factory() as db:
        admin = _seed_user(db, role=UserRole.ADMIN)
        _seed_active_model(db)
        _confirm_case(db, _seed_completed_case(db, positive_label="Effusion"), admin)
        headers = _auth_header(client, admin)

    response = client.post(
        "/api/v1/admin/mlops/retraining/start",
        headers=headers,
        json={"force": True},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["trigger_type"] == "manual_force"
    assert payload["training_samples_count"] == 1
    assert payload["min_required_samples"] == 5
    assert dispatched == [payload["retraining_job_id"]]


def test_auto_start_retraining_when_enabled_and_threshold_reached(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(settings, "retrain_auto_start", True)
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 1)

    from app.tasks.retraining import fine_tune_model

    monkeypatch.setattr(fine_tune_model, "delay", lambda job_id: dispatched.append(job_id))
    reviewer = _seed_user(db_session, role=UserRole.ADMIN)
    _seed_active_model(db_session)

    ReviewService(db_session).confirm_case_result(
        _seed_completed_case(db_session, positive_label="Effusion").case_id,
        reviewed_by=reviewer.user_id,
    )

    job = db_session.scalar(select(RetrainingJob))
    assert job is not None
    assert job.trigger_type == "threshold"
    assert job.training_samples_count == 1
    assert dispatched == [str(job.retraining_job_id)]


def test_auto_start_does_not_create_duplicate_queued_job(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr(settings, "retrain_auto_start", True)
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 1)

    from app.tasks.retraining import fine_tune_model

    monkeypatch.setattr(fine_tune_model, "delay", lambda job_id: dispatched.append(job_id))
    reviewer = _seed_user(db_session, role=UserRole.ADMIN)
    _seed_active_model(db_session)

    for label_name in ["Effusion", "Atelectasis"]:
        ReviewService(db_session).confirm_case_result(
            _seed_completed_case(db_session, positive_label=label_name).case_id,
            reviewed_by=reviewer.user_id,
        )

    jobs = db_session.scalars(select(RetrainingJob)).all()
    assert len(jobs) == 1
    assert len(dispatched) == 1


def test_missing_evaluation_set_returns_warning_not_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "evaluation_set_dir", str(tmp_path / "missing"))

    status = get_evaluation_set_status()

    assert status.available is False
    assert status.sample_count == 0
    assert status.evaluation_source == "training_split_or_unavailable"
    assert status.warning


def test_training_seed_loader_reads_folder_structure(
    tmp_path: Path,
) -> None:
    for class_name in RETRAIN_CLASS_ORDER:
        _write_test_image(tmp_path / class_name / "sample.png")
    _write_test_image(tmp_path / "Atelectasis" / "extra.jpg")

    samples = load_training_seed_samples(tmp_path, max_per_class=1)

    assert len(samples) == 4
    assert [sample.class_name for sample in samples] == list(RETRAIN_CLASS_ORDER)
    assert [sample.label_index for sample in samples] == [0, 1, 2, 3]
    assert samples[-1].label_name == "No Finding"
    assert all(sample.source == "seed" for sample in samples)


def test_missing_training_seed_does_not_crash(tmp_path: Path) -> None:
    samples = load_training_seed_samples(tmp_path / "missing", max_per_class=100)

    assert samples == []


def test_evaluation_set_loader_reads_folder_structure(tmp_path: Path) -> None:
    for class_name in RETRAIN_CLASS_ORDER:
        _write_test_image(tmp_path / class_name / "eval.png")

    status = get_evaluation_set_status(tmp_path)
    dataset = FixedEvaluationDataset(tmp_path)
    image_tensor, label_index = dataset[0]

    assert status.available is True
    assert status.sample_count == 4
    assert status.class_counts == {class_name: 1 for class_name in RETRAIN_CLASS_ORDER}
    assert image_tensor.shape == (3, 224, 224)
    assert label_index == 0


def test_retraining_summary_does_not_count_seed_toward_n(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for class_name in RETRAIN_CLASS_ORDER:
        _write_test_image(tmp_path / "seed" / class_name / "seed.png")
    monkeypatch.setattr(settings, "training_seed_dir", str(tmp_path / "seed"))
    monkeypatch.setattr(settings, "retrain_include_training_seed", True)
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 1)

    summary = RetrainingService(db_session).get_retraining_summary()

    assert summary["training_seed_count"] == 4
    assert summary["total_finetune_samples"] == 4
    assert summary["training_ready_cases"] == 0
    assert summary["missing_confirmed_samples"] == 1
    assert summary["should_trigger_retraining"] is False


def test_finetune_manifest_combines_seed_and_confirmed_cases(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_dir = tmp_path / "training_seed"
    for class_name in RETRAIN_CLASS_ORDER:
        _write_test_image(seed_dir / class_name / "seed.png")
    monkeypatch.setattr(settings, "training_seed_dir", str(seed_dir))
    monkeypatch.setattr(settings, "retrain_include_training_seed", True)
    monkeypatch.setattr(settings, "retrain_manifest_dir", str(tmp_path / "manifests"))
    confirmed_case = _seed_completed_case(db_session, positive_label="Effusion")
    _confirm_case(db_session, confirmed_case)

    manifest = RetrainingService(db_session).export_manifest_for_job()
    payload = json.loads(Path(str(manifest["manifest_path"])).read_text(encoding="utf-8"))

    assert manifest["seed_count"] == 4
    assert manifest["confirmed_count"] == 1
    assert manifest["samples_count"] == 5
    assert payload["total_train_count"] == 5
    assert {sample["source"] for sample in payload["samples"]} == {
        "seed",
        "confirmed_case",
    }
    assert str(confirmed_case.case_id) in json.dumps(payload)


def test_finetune_dataset_excludes_evaluation_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_dir = tmp_path / "training_seed"
    eval_dir = tmp_path / "evaluation_set"
    _write_test_image(seed_dir / "Effusion" / "seed.png")
    _write_test_image(eval_dir / "Effusion" / "eval.png")
    monkeypatch.setattr(settings, "training_seed_dir", str(seed_dir))
    monkeypatch.setattr(settings, "evaluation_set_dir", str(eval_dir))

    summary = build_finetune_dataset([])

    assert summary.seed_count == 1
    assert summary.total_train_count == 1
    assert str(eval_dir) not in summary.samples[0].image_path


def test_finetune_manifest_dataset_loads_seed_image(tmp_path: Path) -> None:
    image_path = tmp_path / "training_seed" / "Atelectasis" / "seed.png"
    _write_test_image(image_path)
    summary = build_finetune_dataset(
        [],
        training_seed_dir=tmp_path / "training_seed",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"samples": [sample.to_manifest() for sample in summary.samples]}),
        encoding="utf-8",
    )

    dataset = FineTuneManifestDataset(manifest_path)
    image_tensor, label_index = dataset[0]

    assert image_tensor.shape == (3, 224, 224)
    assert label_index == 0


def test_retraining_mlflow_logging_can_be_faked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.tasks import retraining as retraining_task

    class FakeRunContext:
        def __enter__(self):
            return SimpleNamespace(info=SimpleNamespace(run_id="run-retrain"))

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

    class FakeMLflow:
        def __init__(self) -> None:
            self.tracking_uri: str | None = None
            self.params: dict[str, object] = {}
            self.metrics: dict[str, float] = {}
            self.artifacts: list[tuple[str, str | None]] = []

        def set_tracking_uri(self, tracking_uri: str) -> None:
            self.tracking_uri = tracking_uri

        def start_run(self, *, experiment_id: str, run_name: str) -> FakeRunContext:
            self.params["experiment_id"] = experiment_id
            self.params["run_name"] = run_name
            return FakeRunContext()

        def log_params(self, params: dict[str, object]) -> None:
            self.params.update(params)

        def log_metrics(self, metrics: dict[str, float]) -> None:
            self.metrics.update(metrics)

        def log_artifact(
            self,
            path: str,
            artifact_path: str | None = None,
        ) -> None:
            self.artifacts.append((path, artifact_path))

    fake_mlflow = FakeMLflow()
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setattr(retraining_task, "ensure_experiment", lambda: "exp-1")
    monkeypatch.setattr(
        retraining_task,
        "register_model_version",
        lambda **_kwargs: SimpleNamespace(version="9"),
    )

    checkpoint_path = tmp_path / "candidate.pth"
    manifest_path = tmp_path / "manifest.json"
    checkpoint_path.write_bytes(b"checkpoint")
    manifest_path.write_text("{}", encoding="utf-8")
    job = RetrainingJob(
        retraining_job_id=uuid.uuid4(),
        status="running",
        trigger_type="manual",
        base_model_id=uuid.uuid4(),
        training_samples_count=2,
        min_required_samples=2,
    )

    run_id, model_uri, version = retraining_task._log_to_mlflow(
        job=job,
        checkpoint_path=checkpoint_path,
        manifest_path=manifest_path,
        metrics={
            "accuracy": 1.0,
            "precision_score": 1.0,
            "recall_score": 1.0,
            "f1_score": 1.0,
        },
        epochs=1,
        evaluation_source="fixed_evaluation_set",
        evaluation_warning=None,
        seed_count=3,
        confirmed_count=2,
        total_train_count=5,
        per_class_count={
            "Atelectasis": 1,
            "Effusion": 2,
            "Infiltration": 1,
            "No_Finding": 1,
        },
    )

    assert run_id == "run-retrain"
    assert model_uri == "runs:/run-retrain/checkpoint"
    assert version == "9"
    assert fake_mlflow.params["architecture"] == "mobilenet_v3_small"
    assert fake_mlflow.params["task_type"] == "multi_class"
    assert fake_mlflow.params["class_order"] == "Atelectasis,Effusion,Infiltration,No_Finding"
    assert fake_mlflow.params["sample_count"] == 5
    assert fake_mlflow.params["seed_count"] == 3
    assert fake_mlflow.params["confirmed_count"] == 2
    assert fake_mlflow.params["total_train_count"] == 5
    assert "No_Finding" in fake_mlflow.params["per_class_count"]
    assert fake_mlflow.params["epochs"] == 1
    assert fake_mlflow.params["evaluation_source"] == "fixed_evaluation_set"
    assert fake_mlflow.metrics["f1_score"] == 1.0
    assert {"manifest", "checkpoint"}.issubset(
        {artifact_path for _path, artifact_path in fake_mlflow.artifacts}
    )


def test_doctor_cannot_access_admin_retraining_endpoints(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        doctor = _seed_user(db, role=UserRole.USER)
        headers = _auth_header(client, doctor)

    for method, path in [
        ("get", "/api/v1/admin/mlops/retraining/summary"),
        ("post", "/api/v1/admin/mlops/retraining/export-manifest"),
        ("post", "/api/v1/admin/mlops/retraining/trigger"),
        ("post", "/api/v1/admin/mlops/retraining/start"),
    ]:
        response = getattr(client, method)(path, headers=headers)
        assert response.status_code == 403


def test_doctor_review_correction_stores_one_positive_label(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        doctor = _seed_user(db, role=UserRole.USER)
        _seed_active_model(db)
        case = _seed_completed_case(db, positive_label="Effusion")
        review = ensure_pending_review_for_outputs(
            db,
            case_id=case.case_id,
            outputs=_low_confidence_outputs(),
        )
        db.commit()
        assert review is not None
        headers = _auth_header(client, doctor)
        review_id = review.review_id
        doctor_id = doctor.user_id

    response = client.post(
        f"/api/v1/admin/reviews/{review_id}/correct",
        headers=headers,
        json={
            "note": "doctor corrected label",
            "labels": [
                {
                    "label_name": label,
                    "confirmed_positive": label == "Atelectasis",
                }
                for label in DEMO_LABELS
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "corrected"
    assert sum(
        1 for label in payload["confirmed_labels"] if label["confirmed_positive"]
    ) == 1
    assert payload["reviewed_by"] == str(doctor_id)

    visible_reviews = client.get("/api/v1/admin/reviews", headers=headers)
    assert visible_reviews.status_code == 200
    assert any(item["review_id"] == str(review_id) for item in visible_reviews.json())

    update_response = client.post(
        f"/api/v1/admin/reviews/{review_id}/correct",
        headers=headers,
        json={
            "note": "doctor updated corrected label",
            "labels": [
                {
                    "label_name": label,
                    "confirmed_positive": label == "Effusion",
                }
                for label in DEMO_LABELS
            ],
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "corrected"
    assert updated["note"] == "doctor updated corrected label"
    assert [
        label["label_name"]
        for label in updated["confirmed_labels"]
        if label["confirmed_positive"]
    ] == ["Effusion"]


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
