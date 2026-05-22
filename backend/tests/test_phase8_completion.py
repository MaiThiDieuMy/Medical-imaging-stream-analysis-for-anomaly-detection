from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.ml.labels import DEMO_LABELS
from app.models.ai_model import AIModel
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.case_review import CaseReview
from app.models.confirmed_label import ConfirmedLabel
from app.models.enums import ProcessingStatus, UserRole
from app.models.patient import Patient
from app.models.user import User
from app.models.xray_case import XRayCase
from app.models.xray_image import XRayImage
from app.services.mlops import MLOpsService


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


def _seed_user(db: Session, username: str, password: str, role: UserRole) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=username,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _image_path(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    Image.new("RGB", (16, 16), (64, 96, 128)).save(path)
    return path


def _seed_case(
    db: Session,
    *,
    model: AIModel,
    uploaded_by: User,
    patient_code: str,
    image_path: Path,
    status: ProcessingStatus = ProcessingStatus.COMPLETED,
) -> XRayCase:
    patient = Patient(
        patient_code=patient_code,
        full_name=f"Patient {patient_code}",
        gender="unknown",
    )
    case = XRayCase(
        patient=patient,
        uploaded_by_id=uploaded_by.user_id,
        status=status,
        note="demo note",
    )
    db.add(case)
    db.flush()
    db.add_all(
        [
            XRayImage(
                case_id=case.case_id,
                file_name=image_path.name,
                image_path=str(image_path),
                image_hash=f"hash-{patient_code}",
                file_format="png",
            ),
            AnalysisJob(
                case_id=case.case_id,
                model_id=model.model_id,
                status=status,
            ),
        ]
    )
    for label_name in DEMO_LABELS:
        db.add(
            AnalysisResult(
                case_id=case.case_id,
                model_id=model.model_id,
                label_name=label_name,
                probability=0.75,
                predicted_positive=True,
            )
        )
    db.commit()
    db.refresh(case)
    return case


def _seed_model(db: Session) -> AIModel:
    model = AIModel(
        model_name="demo-chest-xray",
        version="demo-v1",
        model_path="demo://chest-xray/demo-v1",
        is_active=True,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def test_doctor_my_cases_filters_to_uploaded_cases(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        model = _seed_model(db)
        doctor = _seed_user(db, "doctor_demo", "doctor123", UserRole.USER)
        other = _seed_user(db, "doctor_two", "doctor123", UserRole.USER)
        own_case = _seed_case(
            db,
            model=model,
            uploaded_by=doctor,
            patient_code="OWN-001",
            image_path=_image_path(tmp_path, "own.png"),
        )
        own_case_id = str(own_case.case_id)
        _seed_case(
            db,
            model=model,
            uploaded_by=other,
            patient_code="OTHER-001",
            image_path=_image_path(tmp_path, "other.png"),
        )

    response = client.get(
        "/api/v1/cases/my",
        headers=_auth_header(client, "doctor_demo", "doctor123"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["case_id"] for item in payload] == [own_case_id]


def test_admin_cases_lists_all_cases(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        model = _seed_model(db)
        admin = _seed_user(db, "admin_demo", "admin123", UserRole.ADMIN)
        doctor = _seed_user(db, "doctor_demo", "doctor123", UserRole.USER)
        _seed_case(
            db,
            model=model,
            uploaded_by=admin,
            patient_code="ADM-001",
            image_path=_image_path(tmp_path, "admin.png"),
        )
        _seed_case(
            db,
            model=model,
            uploaded_by=doctor,
            patient_code="DOC-001",
            image_path=_image_path(tmp_path, "doctor.png"),
        )

    response = client.get(
        "/api/v1/cases",
        headers=_auth_header(client, "admin_demo", "admin123"),
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_case_report_endpoint_returns_html(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        model = _seed_model(db)
        doctor = _seed_user(db, "doctor_demo", "doctor123", UserRole.USER)
        case = _seed_case(
            db,
            model=model,
            uploaded_by=doctor,
            patient_code="REP-001",
            image_path=_image_path(tmp_path, "report.png"),
        )

    response = client.get(
        f"/api/v1/cases/{case.case_id}/report",
        headers=_auth_header(client, "doctor_demo", "doctor123"),
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Patient REP-001" in response.text
    assert "No Finding" in response.text


def test_manifest_export_excludes_pending_reviews(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, session_factory = client_and_session_factory
    monkeypatch.setattr(settings, "retraining_manifest_dir", str(tmp_path))
    with session_factory() as db:
        model = _seed_model(db)
        doctor = _seed_user(db, "doctor_demo", "doctor123", UserRole.USER)
        ready_case = _seed_case(
            db,
            model=model,
            uploaded_by=doctor,
            patient_code="READY-001",
            image_path=_image_path(tmp_path, "ready.png"),
        )
        pending_case = _seed_case(
            db,
            model=model,
            uploaded_by=doctor,
            patient_code="PEND-001",
            image_path=_image_path(tmp_path, "pending.png"),
        )
        ready_review = CaseReview(
            case_id=ready_case.case_id,
            status="confirmed",
            reason="confirmed demo",
        )
        pending_review = CaseReview(
            case_id=pending_case.case_id,
            status="pending",
            reason="pending demo",
        )
        db.add_all([ready_review, pending_review])
        db.flush()
        for label_name in DEMO_LABELS:
            db.add(
                ConfirmedLabel(
                    review_id=ready_review.review_id,
                    case_id=ready_case.case_id,
                    label_name=label_name,
                    confirmed_positive=label_name == "Effusion",
                )
            )
        db.commit()

        result = MLOpsService(db).export_manifest()

    manifest = json.loads(Path(str(result["manifest_path"])).read_text())
    assert manifest["samples_count"] == 1
    assert manifest["samples"][0]["case_id"] == str(ready_case.case_id)
    assert "labels" in manifest["samples"][0]


def test_metrics_endpoint_returns_prometheus_text(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session_factory
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "analyze_requests_total" in response.text
    assert "analysis_jobs_total" in response.text
    assert "backend_info" in response.text
    assert "celery_queue_length" in response.text
    assert "model_active_info" in response.text
