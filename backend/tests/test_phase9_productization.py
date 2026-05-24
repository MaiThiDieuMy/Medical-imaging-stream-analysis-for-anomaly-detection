from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.ml.labels import DEMO_LABELS
from app.models.ai_model import AIModel
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.enums import ProcessingStatus, UserRole
from app.models.patient import Patient
from app.models.user import User
from app.models.xray_case import XRayCase
from app.models.xray_image import XRayImage


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


def _seed_user(
    db: Session,
    username: str,
    password: str,
    role: UserRole,
    *,
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=username,
        role=role,
        is_active=is_active,
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


def _seed_model(db: Session, *, active: bool, version: str) -> AIModel:
    model = AIModel(
        model_name="phase9-model",
        version=version,
        model_path=f"artifacts/models/{version}.pth",
        is_active=active,
        f1_score=0.72 if active else 0.74,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _image_path(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    Image.new("RGB", (16, 16), (64, 96, 128)).save(path)
    return path


def _seed_case(
    db: Session,
    *,
    model: AIModel,
    uploaded_by: User,
    image_path: Path,
) -> XRayCase:
    patient = Patient(
        patient_code="PHASE9-001",
        full_name="Phase 9 Patient",
        gender="unknown",
    )
    case = XRayCase(
        patient=patient,
        uploaded_by_id=uploaded_by.user_id,
        status=ProcessingStatus.COMPLETED,
    )
    db.add(case)
    db.flush()
    db.add_all(
        [
            XRayImage(
                case_id=case.case_id,
                file_name=image_path.name,
                image_path=str(image_path),
                image_hash="phase9-hash",
                file_format="png",
            ),
            AnalysisJob(
                case_id=case.case_id,
                model_id=model.model_id,
                status=ProcessingStatus.COMPLETED,
            ),
        ]
    )
    for label_name in DEMO_LABELS:
        db.add(
            AnalysisResult(
                case_id=case.case_id,
                model_id=model.model_id,
                label_name=label_name,
                probability=0.8,
                predicted_positive=True,
            )
        )
    db.commit()
    db.refresh(case)
    return case


def test_inactive_user_cannot_login(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_user(
            db,
            "doctor_inactive",
            "doctor123",
            UserRole.USER,
            is_active=False,
        )

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor_inactive", "password": "doctor123"},
    )

    assert response.status_code == 403


def test_admin_can_deactivate_user_and_doctor_cannot_manage_users(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        admin = _seed_user(db, "admin_demo", "admin123", UserRole.ADMIN)
        doctor = _seed_user(db, "doctor_demo", "doctor123", UserRole.USER)
        doctor_id = doctor.user_id
        assert admin.is_active

    doctor_response = client.patch(
        f"/api/v1/admin/users/{doctor_id}",
        json={"is_active": False},
        headers=_auth_header(client, "doctor_demo", "doctor123"),
    )
    assert doctor_response.status_code == 403

    admin_response = client.patch(
        f"/api/v1/admin/users/{doctor_id}",
        json={
            "full_name": "Bác sĩ đã cập nhật",
            "role": "admin",
            "is_active": False,
        },
        headers=_auth_header(client, "admin_demo", "admin123"),
    )
    assert admin_response.status_code == 200
    admin_payload = admin_response.json()
    assert admin_payload["full_name"] == "Bác sĩ đã cập nhật"
    assert admin_payload["role"] == "admin"
    assert admin_payload["is_active"] is False

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor_demo", "password": "doctor123"},
    )
    assert login_response.status_code == 403


def test_admin_archives_case_without_deleting_results(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        model = _seed_model(db, active=True, version="active-v1")
        _seed_user(db, "admin_demo", "admin123", UserRole.ADMIN)
        doctor = _seed_user(db, "doctor_demo", "doctor123", UserRole.USER)
        case = _seed_case(
            db,
            model=model,
            uploaded_by=doctor,
            image_path=_image_path(tmp_path, "phase9.png"),
        )
        case_id = case.case_id

    doctor_response = client.post(
        f"/api/v1/cases/{case_id}/archive",
        headers=_auth_header(client, "doctor_demo", "doctor123"),
    )
    assert doctor_response.status_code == 200
    assert doctor_response.json()["archived_at"] is not None

    admin_response = client.post(
        f"/api/v1/cases/{case_id}/archive",
        headers=_auth_header(client, "admin_demo", "admin123"),
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["archived_at"] is not None

    list_response = client.get(
        "/api/v1/cases",
        headers=_auth_header(client, "admin_demo", "admin123"),
    )
    assert list_response.status_code == 200
    assert list_response.json() == []

    archived_list_response = client.get(
        "/api/v1/cases?archive_filter=archived",
        headers=_auth_header(client, "admin_demo", "admin123"),
    )
    assert archived_list_response.status_code == 200
    assert [item["case_id"] for item in archived_list_response.json()] == [
        str(case_id),
    ]

    restore_response = client.patch(
        f"/api/v1/cases/{case_id}/restore",
        headers=_auth_header(client, "doctor_demo", "doctor123"),
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["archived_at"] is None

    my_cases_response = client.get(
        "/api/v1/cases/my",
        headers=_auth_header(client, "doctor_demo", "doctor123"),
    )
    assert my_cases_response.status_code == 200
    assert [item["case_id"] for item in my_cases_response.json()] == [str(case_id)]

    with session_factory() as db:
        results_count = db.scalar(
            select(func.count())
            .select_from(AnalysisResult)
            .where(AnalysisResult.case_id == case_id)
        )
        restored_case = db.get(XRayCase, case_id)
        assert restored_case is not None
        assert restored_case.archived_at is None
        assert results_count == len(DEMO_LABELS)


def test_doctor_cannot_archive_another_doctors_case(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        model = _seed_model(db, active=True, version="active-v1")
        owner = _seed_user(db, "doctor_owner", "doctor123", UserRole.USER)
        other = _seed_user(db, "doctor_other", "doctor123", UserRole.USER)
        case = _seed_case(
            db,
            model=model,
            uploaded_by=owner,
            image_path=_image_path(tmp_path, "owned.png"),
        )
        case_id = case.case_id
        assert other.is_active

    response = client.post(
        f"/api/v1/cases/{case_id}/archive",
        headers=_auth_header(client, "doctor_other", "doctor123"),
    )

    assert response.status_code == 404


def test_doctor_cannot_restore_another_doctors_case(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        model = _seed_model(db, active=True, version="active-v1")
        owner = _seed_user(db, "doctor_owner", "doctor123", UserRole.USER)
        other = _seed_user(db, "doctor_other", "doctor123", UserRole.USER)
        case = _seed_case(
            db,
            model=model,
            uploaded_by=owner,
            image_path=_image_path(tmp_path, "owned.png"),
        )
        case.archived_at = datetime.now(timezone.utc)
        db.commit()
        case_id = case.case_id
        assert other.is_active

    response = client.patch(
        f"/api/v1/cases/{case_id}/restore",
        headers=_auth_header(client, "doctor_other", "doctor123"),
    )

    assert response.status_code == 404


def test_doctor_updates_patient_without_changing_patient_id(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        model = _seed_model(db, active=True, version="active-v1")
        doctor = _seed_user(db, "doctor_demo", "doctor123", UserRole.USER)
        case = _seed_case(
            db,
            model=model,
            uploaded_by=doctor,
            image_path=_image_path(tmp_path, "patient-edit.png"),
        )
        patient_id = case.patient.patient_id
        patient_code = case.patient.patient_code

    headers = _auth_header(client, "doctor_demo", "doctor123")
    response = client.patch(
        f"/api/v1/patients/{patient_id}",
        json={
            "patient_code": "SHOULD-NOT-CHANGE",
            "full_name": "Updated Patient",
        },
        headers=headers,
    )
    assert response.status_code == 422

    response = client.patch(
        f"/api/v1/patients/{patient_id}",
        json={
            "full_name": "Updated Patient",
            "gender": "female",
            "birth_year": 1988,
            "department": "Radiology",
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["patient_code"] == patient_code
    assert payload["full_name"] == "Updated Patient"
    assert payload["birth_year"] == 1988

    with session_factory() as db:
        patient = db.get(Patient, patient_id)
        assert patient is not None
        assert patient.patient_code == patient_code
        assert patient.full_name == "Updated Patient"


def test_admin_archives_inactive_model_but_not_active_model(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_user(db, "admin_demo", "admin123", UserRole.ADMIN)
        active = _seed_model(db, active=True, version="active-v1")
        inactive = _seed_model(db, active=False, version="candidate-v1")
        active_id = active.model_id
        inactive_id = inactive.model_id

    headers = _auth_header(client, "admin_demo", "admin123")
    active_response = client.post(
        f"/api/v1/admin/models/{active_id}/archive",
        headers=headers,
    )
    assert active_response.status_code == 409

    inactive_response = client.post(
        f"/api/v1/admin/models/{inactive_id}/archive",
        headers=headers,
    )
    assert inactive_response.status_code == 200
    assert inactive_response.json()["archived_at"] is not None

    activate_response = client.post(
        f"/api/v1/admin/models/{inactive_id}/activate",
        headers=headers,
    )
    assert activate_response.status_code == 409


def test_admin_deletes_retrained_model_weights_without_mlflow_history(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    client, session_factory = client_and_session_factory
    weights_path = tmp_path / "candidate.pth"
    weights_path.write_bytes(b"weights")
    with session_factory() as db:
        _seed_user(db, "admin_demo", "admin123", UserRole.ADMIN)
        _seed_model(db, active=True, version="active-v1")
        candidate = AIModel(
            model_name="phase9-retrained",
            version="candidate-v1",
            model_path=str(weights_path),
            is_active=False,
            mlflow_run_id="run-123",
            mlflow_model_uri="runs:/run-123/checkpoint",
            mlflow_registered_model_name="registered-model",
            mlflow_model_version="7",
        )
        db.add(candidate)
        db.commit()
        candidate_id = candidate.model_id

    response = client.delete(
        f"/api/v1/admin/models/{candidate_id}",
        headers=_auth_header(client, "admin_demo", "admin123"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["archived_at"] is not None
    assert payload["model_path"].startswith("deleted://local-weights/")
    assert payload["mlflow_run_id"] == "run-123"
    assert payload["mlflow_model_uri"] == "runs:/run-123/checkpoint"
    assert not weights_path.exists()


def test_admin_cannot_delete_active_or_baseline_model(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_user(db, "admin_demo", "admin123", UserRole.ADMIN)
        active = _seed_model(db, active=True, version="active-v1")
        baseline = AIModel(
            model_name="kaggle-mobilenetv3-small-chest-xray",
            version="kaggle-v1",
            model_path="artifacts/models/best_model.pth",
            is_active=False,
        )
        db.add(baseline)
        db.commit()
        active_id = active.model_id
        baseline_id = baseline.model_id

    headers = _auth_header(client, "admin_demo", "admin123")
    active_response = client.delete(
        f"/api/v1/admin/models/{active_id}",
        headers=headers,
    )
    baseline_response = client.delete(
        f"/api/v1/admin/models/{baseline_id}",
        headers=headers,
    )

    assert active_response.status_code == 409
    assert baseline_response.status_code == 409
