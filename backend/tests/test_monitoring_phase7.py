from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.ai_model import AIModel
from app.models.analysis_job import AnalysisJob
from app.models.case_review import CaseReview
from app.models.enums import ProcessingStatus, UserRole
from app.models.patient import Patient
from app.models.user import User
from app.models.xray_case import XRayCase


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


def test_health_available_at_root_and_api_prefix() -> None:
    with TestClient(app) as client:
        root_response = client.get("/health")
        api_response = client.get("/api/v1/health")

    assert root_response.status_code == 200
    assert api_response.status_code == 200
    assert root_response.json()["status"] == "ok"
    assert api_response.json()["status"] == "ok"


def test_backend_root_route_points_to_demo_entrypoints() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == (
        "Medical-imaging-stream-analysis-for-nomaly-detection"
    )
    assert payload["status"] == "ok"
    assert payload["docs_url"] == "/docs"
    assert payload["health_url"] == "/health"
    assert payload["metrics_url"] == "/metrics"
    assert payload["frontend_url"] == "http://localhost:5173"


def test_admin_monitoring_summary_reports_safe_counts(
    client_and_session_factory: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = client_and_session_factory
    with session_factory() as db:
        admin = User(
            username="admin_demo",
            password_hash=hash_password("admin123"),
            full_name="Demo Admin",
            role=UserRole.ADMIN,
        )
        model = AIModel(
            model_name="demo-chest-xray",
            version="demo-v1",
            model_path="demo://chest-xray/demo-v1",
            is_active=True,
            f1_score=0.70,
        )
        db.add_all([admin, model])
        db.flush()

        patient = Patient(
            patient_code="MON-001",
            full_name="Monitoring Demo",
            gender="unknown",
        )
        case_one = XRayCase(patient=patient, status=ProcessingStatus.QUEUED)
        case_two = XRayCase(patient=patient, status=ProcessingStatus.COMPLETED)
        db.add_all([case_one, case_two])
        db.flush()
        db.add_all(
            [
                AnalysisJob(
                    case_id=case_one.case_id,
                    model_id=model.model_id,
                    status=ProcessingStatus.QUEUED,
                ),
                AnalysisJob(
                    case_id=case_two.case_id,
                    model_id=model.model_id,
                    status=ProcessingStatus.COMPLETED,
                ),
                CaseReview(
                    case_id=case_one.case_id,
                    status="pending",
                    reason="demo pending review",
                ),
                CaseReview(
                    case_id=case_two.case_id,
                    status="confirmed",
                    reason="demo confirmed review",
                ),
            ]
        )
        db.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin_demo", "password": "admin123"},
    )
    token = login_response.json()["access_token"]
    response = client.get(
        "/api/v1/monitoring/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend_status"] == "ok"
    assert payload["database_reachable"] is True
    assert "celery_queue_length" in payload
    assert payload["active_model"]["version"] == "demo-v1"
    assert payload["total_cases"] == 2
    assert payload["total_jobs_by_status"]["queued"] == 1
    assert payload["total_jobs_by_status"]["completed"] == 1
    assert payload["pending_reviews"] == 1
    assert payload["training_ready_cases"] == 1
