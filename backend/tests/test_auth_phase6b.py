from __future__ import annotations

from collections.abc import Generator
from io import BytesIO
from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient
from PIL import Image
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
from app.ml.labels import DEMO_LABELS
from app.ml.types import InferenceOutput
from app.models.ai_model import AIModel
from app.models.analysis_result import AnalysisResult
from app.models.enums import ProcessingStatus, UserRole
from app.models.patient import Patient
from app.models.user import User
from app.models.xray_case import XRayCase
from app.schemas.analysis import PatientAnalyzeRequest
from app.services.analyze import AnalyzeService, UploadedImageData
from app.services.reviews import ReviewService, ensure_pending_review_for_outputs
from app.services.storage import ImageStorage


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
    *,
    username: str,
    password: str,
    role: UserRole,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=f"{username} User",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_active_model(db: Session) -> AIModel:
    model = AIModel(
        model_name="demo-chest-xray",
        version="demo-v1",
        model_path="demo://chest-xray/demo-v1",
        is_active=True,
        f1_score=0.70,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _auth_header(client: TestClient, *, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _image_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), (80, 120, 180))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _patient_request() -> PatientAnalyzeRequest:
    return PatientAnalyzeRequest(
        patient_code="AUTH-001",
        full_name="Auth Demo Patient",
        gender="unknown",
        birth_year=1980,
        department="Radiology",
        note="phase 6b audit",
    )


def _low_confidence_outputs() -> list[InferenceOutput]:
    return [
        InferenceOutput("No Finding", 0.42, False),
        InferenceOutput("Effusion", 0.55, True),
        InferenceOutput("Infiltration", 0.49, False),
        InferenceOutput("Atelectasis", 0.20, False),
    ]


def _create_case_with_results(db: Session) -> XRayCase:
    model = _seed_active_model(db)
    patient = Patient(
        patient_code=f"AUTH-REVIEW-{uuid.uuid4().hex[:8]}",
        full_name="Review Patient",
        gender="unknown",
    )
    case = XRayCase(patient=patient, status=ProcessingStatus.COMPLETED)
    db.add(case)
    db.flush()
    for label_name, probability in zip(
        DEMO_LABELS,
        (0.42, 0.55, 0.49, 0.20),
        strict=True,
    ):
        db.add(
            AnalysisResult(
                case_id=case.case_id,
                model_id=model.model_id,
                label_name=label_name,
                probability=probability,
                predicted_positive=probability >= 0.5,
            )
        )
    db.commit()
    db.refresh(case)
    return case


def test_login_success(client_and_session_factory: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_user(
            db,
            username="doctor_demo",
            password="doctor123",
            role=UserRole.USER,
        )

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor_demo", "password": "doctor123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["username"] == "doctor_demo"
    assert payload["user"]["role"] == "user"


def test_login_wrong_password(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_user(
            db,
            username="doctor_demo",
            password="doctor123",
            role=UserRole.USER,
        )

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor_demo", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_admin_can_access_admin_model_endpoint(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_user(
            db,
            username="admin_demo",
            password="admin123",
            role=UserRole.ADMIN,
        )

    response = client.get(
        "/api/v1/admin/models",
        headers=_auth_header(client, username="admin_demo", password="admin123"),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_doctor_cannot_access_admin_model_endpoint(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        _seed_user(
            db,
            username="doctor_demo",
            password="doctor123",
            role=UserRole.USER,
        )

    response = client.get(
        "/api/v1/admin/models",
        headers=_auth_header(client, username="doctor_demo", password="doctor123"),
    )

    assert response.status_code == 403


def test_analyze_attaches_uploaded_by_user(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    _, session_factory = client_and_session_factory
    with session_factory() as db:
        user = _seed_user(
            db,
            username="doctor_demo",
            password="doctor123",
            role=UserRole.USER,
        )
        _seed_active_model(db)
        enqueued: list[str] = []
        service = AnalyzeService(
            db,
            storage=ImageStorage(base_dir=tmp_path),
            enqueue=lambda job_id: enqueued.append(job_id),
        )

        response = service.analyze_upload(
            _patient_request(),
            UploadedImageData(
                filename="auth-demo.png",
                content_type="image/png",
                content=_image_bytes(),
            ),
            uploaded_by_id=user.user_id,
        )

        case = db.get(XRayCase, response.case_id)
        assert case is not None
        assert case.uploaded_by_id == user.user_id
        assert enqueued == [str(response.job_id)]


def test_confirm_review_sets_reviewed_by(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, session_factory = client_and_session_factory
    with session_factory() as db:
        user = _seed_user(
            db,
            username="doctor_demo",
            password="doctor123",
            role=UserRole.USER,
        )
        case = _create_case_with_results(db)
        review = ensure_pending_review_for_outputs(
            db,
            case_id=case.case_id,
            outputs=_low_confidence_outputs(),
        )
        db.commit()
        assert review is not None

        confirmed = ReviewService(db).confirm_review(
            review.review_id,
            reviewed_by=user.user_id,
        )

        assert confirmed.reviewed_by_id == user.user_id
        assert confirmed.reviewed_at is not None
