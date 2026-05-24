from __future__ import annotations

from collections.abc import Generator
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.database import Base
from app.ml.labels import DEMO_LABELS
from app.models.ai_model import AIModel
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.enums import ProcessingStatus
from app.models.patient import Patient
from app.models.xray_case import XRayCase
from app.models.xray_image import XRayImage
from app.schemas.analysis import PatientAnalyzeRequest
from app.services.analyze import AnalyzeService, AnalyzeServiceError, UploadedImageData
from app.services.storage import ImageStorage


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


def _image_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), (32, 96, 160))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _uploaded_image(content: bytes) -> UploadedImageData:
    return UploadedImageData(
        filename="sample.png",
        content_type="image/png",
        content=content,
    )


def _patient_request() -> PatientAnalyzeRequest:
    return PatientAnalyzeRequest(
        patient_code="DEMO-001",
        full_name="Demo Patient",
        gender="unknown",
        birth_year=1990,
        department="Radiology",
        note="demo upload",
    )


def _seed_active_model(db: Session) -> AIModel:
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


def _count(db: Session, model: type[object]) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


class FailingStorage(ImageStorage):
    def save_image_bytes(
        self,
        content: bytes,
        *,
        image_hash: str,
        file_format: str,
    ) -> str:
        raise AssertionError("cache hit must not save image bytes")


def test_cache_hit_returns_results_without_enqueue_or_new_records(
    db_session: Session,
) -> None:
    model = _seed_active_model(db_session)
    content = _image_bytes()
    image_hash = sha256(content).hexdigest()

    patient = Patient(
        patient_code="DEMO-001",
        full_name="Demo Patient",
        gender="unknown",
    )
    case = XRayCase(patient=patient, status=ProcessingStatus.COMPLETED)
    db_session.add(case)
    db_session.flush()
    db_session.add_all(
        [
            XRayImage(
                case_id=case.case_id,
                file_name="cached.png",
                image_path="/tmp/cached.png",
                image_hash=image_hash,
                file_format="png",
            ),
            AnalysisJob(
                case_id=case.case_id,
                model_id=model.model_id,
                status=ProcessingStatus.COMPLETED,
            ),
        ]
    )
    for label in DEMO_LABELS:
        db_session.add(
            AnalysisResult(
                case_id=case.case_id,
                model_id=model.model_id,
                label_name=label,
                probability=0.75,
                predicted_positive=True,
            )
        )
    db_session.commit()

    enqueued: list[str] = []
    service = AnalyzeService(
        db_session,
        storage=FailingStorage(),
        enqueue=lambda job_id: enqueued.append(job_id),
    )

    response = service.analyze_upload(_patient_request(), _uploaded_image(content))

    assert response.cache_hit is True
    assert response.status == ProcessingStatus.COMPLETED.value
    assert len(response.results) == len(DEMO_LABELS)
    assert enqueued == []
    assert _count(db_session, XRayCase) == 1
    assert _count(db_session, XRayImage) == 1
    assert _count(db_session, AnalysisJob) == 1


def test_cache_miss_creates_case_job_and_enqueues(
    db_session: Session,
    tmp_path: Path,
) -> None:
    model = _seed_active_model(db_session)
    content = _image_bytes()
    enqueued: list[str] = []
    storage = ImageStorage(base_dir=tmp_path)
    service = AnalyzeService(
        db_session,
        storage=storage,
        enqueue=lambda job_id: enqueued.append(job_id),
    )

    response = service.analyze_upload(_patient_request(), _uploaded_image(content))

    assert response.cache_hit is False
    assert response.status == ProcessingStatus.QUEUED.value
    assert response.case_id is not None
    assert response.job_id is not None
    assert response.model_id == model.model_id
    assert enqueued == [str(response.job_id)]
    assert _count(db_session, Patient) == 1
    assert _count(db_session, XRayCase) == 1
    assert _count(db_session, XRayImage) == 1
    assert _count(db_session, AnalysisJob) == 1
    assert _count(db_session, AnalysisResult) == 0

    saved_image = db_session.execute(select(XRayImage)).scalar_one()
    assert Path(saved_image.image_path).exists()


def test_cache_miss_auto_generates_patient_code(
    db_session: Session,
    tmp_path: Path,
) -> None:
    _seed_active_model(db_session)
    service = AnalyzeService(
        db_session,
        storage=ImageStorage(base_dir=tmp_path),
        enqueue=lambda job_id: None,
    )
    request = PatientAnalyzeRequest(
        full_name="Auto Patient",
        gender="unknown",
    )

    service.analyze_upload(request, _uploaded_image(_image_bytes()))

    patient = db_session.execute(select(Patient)).scalar_one()
    assert patient.patient_code.startswith("PAT-")


def test_duplicate_patient_code_is_clear_create_error(
    db_session: Session,
    tmp_path: Path,
) -> None:
    _seed_active_model(db_session)
    db_session.add(
        Patient(
            patient_code="DUP-001",
            full_name="Existing",
            gender="unknown",
        )
    )
    db_session.commit()
    service = AnalyzeService(
        db_session,
        storage=ImageStorage(base_dir=tmp_path),
        enqueue=lambda job_id: None,
    )

    with pytest.raises(AnalyzeServiceError) as exc_info:
        service.analyze_upload(
            PatientAnalyzeRequest(
                patient_code="DUP-001",
                full_name="Duplicate",
                gender="unknown",
            ),
            _uploaded_image(_image_bytes()),
        )

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.message


def test_invalid_image_content_is_validation_error(db_session: Session) -> None:
    service = AnalyzeService(db_session, enqueue=lambda job_id: None)

    with pytest.raises(AnalyzeServiceError) as exc_info:
        service.analyze_upload(
            _patient_request(),
            UploadedImageData(
                filename="broken.png",
                content_type="image/png",
                content=b"not a real image",
            ),
        )

    assert exc_info.value.status_code == 400
