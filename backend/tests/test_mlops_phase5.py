from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sys
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.ml.labels import DEMO_LABELS
from app.ml.types import InferenceOutput
from app.mlops.metrics import calculate_classification_metrics
from app.models.ai_model import AIModel
from app.models.analysis_result import AnalysisResult
from app.models.case_review import CaseReview
from app.models.confirmed_label import ConfirmedLabel
from app.models.enums import ProcessingStatus
from app.models.patient import Patient
from app.models.xray_case import XRayCase
from app.models.xray_image import XRayImage
from app.schemas.admin import AIModelCreate, CandidateModelCreate
from app.services.mlops import MLOpsService
from app.services.model_admin import ModelAdminService, ModelAdminServiceError
from app.services.reviews import (
    REVIEW_STATUS_CONFIRMED,
    REVIEW_STATUS_CORRECTED,
    REVIEW_STATUS_PENDING,
    ReviewService,
    ensure_pending_review_for_outputs,
)


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


def _create_model(
    db: Session,
    *,
    name: str = "demo-chest-xray",
    version: str = "v1",
    active: bool = False,
    f1_score: float | None = None,
) -> AIModel:
    model = AIModel(
        model_name=name,
        version=version,
        model_path=f"demo://{name}/{version}",
        accuracy=f1_score,
        f1_score=f1_score,
        precision_score=f1_score,
        recall_score=f1_score,
        is_active=active,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _create_case_with_results(
    db: Session,
    *,
    probabilities: tuple[float, float, float, float] = (0.42, 0.55, 0.49, 0.20),
) -> XRayCase:
    model = db.execute(
        select(AIModel).where(AIModel.is_active.is_(True))
    ).scalar_one_or_none()
    if model is None:
        model = _create_model(db, active=True, f1_score=0.60)
    patient = Patient(
        patient_code=f"DEMO-ML-{uuid.uuid4().hex[:8]}",
        full_name="Demo Patient",
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
    for label_name, probability in zip(DEMO_LABELS, probabilities, strict=True):
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


def _low_confidence_outputs() -> list[InferenceOutput]:
    return [
        InferenceOutput("No Finding", 0.42, False),
        InferenceOutput("Effusion", 0.55, True),
        InferenceOutput("Infiltration", 0.49, False),
        InferenceOutput("Atelectasis", 0.20, False),
    ]


def test_model_registration_and_active_switching(db_session: Session) -> None:
    service = ModelAdminService(db_session)
    first = service.create_model(
        AIModelCreate(
            model_name="demo-chest-xray",
            version="v1",
            model_path="demo://v1",
            f1_score=0.60,
            is_active=True,
        )
    )
    second = service.create_model(
        AIModelCreate(
            model_name="demo-chest-xray",
            version="v2",
            model_path="demo://v2",
            f1_score=0.70,
            is_active=False,
        )
    )

    activated = service.activate_model(second.model_id)

    db_session.refresh(first)
    assert activated.model_id == second.model_id
    assert activated.is_active is True
    assert first.is_active is False
    assert service.get_active_model().model_id == second.model_id


def test_duplicate_model_name_version_is_rejected(db_session: Session) -> None:
    service = ModelAdminService(db_session)
    payload = AIModelCreate(
        model_name="demo-chest-xray",
        version="v1",
        model_path="demo://v1",
    )
    service.create_model(payload)

    with pytest.raises(ModelAdminServiceError) as exc_info:
        service.create_model(payload)

    assert exc_info.value.status_code == 409


def test_low_confidence_review_creation_logic(db_session: Session) -> None:
    case = _create_case_with_results(db_session)

    review = ensure_pending_review_for_outputs(
        db_session,
        case_id=case.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()

    assert review is not None
    assert review.status == REVIEW_STATUS_PENDING
    assert "max_probability" in review.reason


def test_confirm_review_creates_confirmed_labels(db_session: Session) -> None:
    case = _create_case_with_results(db_session)
    review = ensure_pending_review_for_outputs(
        db_session,
        case_id=case.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()
    assert review is not None

    confirmed = ReviewService(db_session).confirm_review(review.review_id)

    assert confirmed.status == REVIEW_STATUS_CONFIRMED
    assert len(confirmed.confirmed_labels) == len(DEMO_LABELS)
    assert {
        label.label_name: label.confirmed_positive
        for label in confirmed.confirmed_labels
    } == {
        result.label_name: result.predicted_positive
        for result in db_session.scalars(select(AnalysisResult)).all()
    }


def test_corrected_review_creates_confirmed_labels(db_session: Session) -> None:
    case = _create_case_with_results(db_session)
    review = ensure_pending_review_for_outputs(
        db_session,
        case_id=case.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()
    assert review is not None
    corrections = {
        "No Finding": True,
        "Effusion": False,
        "Infiltration": False,
        "Atelectasis": False,
    }

    corrected = ReviewService(db_session).correct_review(
        review.review_id,
        labels=corrections,
    )

    assert corrected.status == REVIEW_STATUS_CORRECTED
    assert {
        label.label_name: label.confirmed_positive
        for label in corrected.confirmed_labels
    } == corrections


def test_pending_review_is_not_training_ready(db_session: Session) -> None:
    case = _create_case_with_results(db_session)
    review = ensure_pending_review_for_outputs(
        db_session,
        case_id=case.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()
    assert review is not None

    assert ReviewService(db_session).list_training_ready() == []
    assert db_session.scalars(select(ConfirmedLabel)).all() == []


def test_retraining_summary_counts_confirmed_and_corrected_only(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "retrain_min_confirmed_samples", 2)
    case_one = _create_case_with_results(db_session)
    review_one = ensure_pending_review_for_outputs(
        db_session,
        case_id=case_one.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()
    assert review_one is not None
    ReviewService(db_session).confirm_review(review_one.review_id)

    case_two = _create_case_with_results(db_session)
    review_two = ensure_pending_review_for_outputs(
        db_session,
        case_id=case_two.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()
    assert review_two is not None
    ReviewService(db_session).correct_review(
        review_two.review_id,
        labels={
            "No Finding": False,
            "Effusion": True,
            "Infiltration": False,
            "Atelectasis": False,
        },
    )

    case_three = _create_case_with_results(db_session)
    ensure_pending_review_for_outputs(
        db_session,
        case_id=case_three.case_id,
        outputs=_low_confidence_outputs(),
    )
    db_session.commit()

    summary = MLOpsService(db_session).retraining_summary()

    assert summary["confirmed_reviews"] == 1
    assert summary["corrected_reviews"] == 1
    assert summary["pending_reviews"] == 1
    assert summary["training_ready_cases"] == 2
    assert summary["should_trigger_retraining"] is True


def test_calculate_classification_metrics() -> None:
    metrics = calculate_classification_metrics(
        [True, False, True, False],
        [True, True, False, False],
    )

    assert metrics == {
        "accuracy": 0.5,
        "precision_score": 0.5,
        "recall_score": 0.5,
        "f1_score": 0.5,
    }


def test_promote_if_better_activates_candidate(db_session: Session) -> None:
    active = _create_model(db_session, version="v1", active=True, f1_score=0.60)
    service = ModelAdminService(db_session)
    candidate = service.register_candidate(
        CandidateModelCreate(
            model_name="demo-chest-xray",
            version="v2",
            model_path="demo://v2",
            accuracy=0.75,
            precision_score=0.75,
            recall_score=0.75,
            f1_score=0.75,
        )
    )

    response = service.promote_if_better(candidate.model_id)

    db_session.refresh(active)
    assert response.promoted is True
    assert response.promotion_metric == "f1_score"
    assert response.candidate_metric == 0.75
    assert response.active_metric == 0.60
    assert response.promotion_recommended is True
    assert response.active_model.model_id == candidate.model_id
    assert active.is_active is False
    assert service.get_active_model().model_id == candidate.model_id


def test_promotion_gate_respects_min_delta(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "model_promotion_metric", "f1_score")
    monkeypatch.setattr(settings, "model_promotion_min_delta", 0.05)
    _create_model(db_session, version="v1", active=True, f1_score=0.80)
    service = ModelAdminService(db_session)
    candidate = service.register_candidate(
        CandidateModelCreate(
            model_name="demo-chest-xray",
            version="v3",
            model_path="demo://v3",
            accuracy=0.82,
            precision_score=0.82,
            recall_score=0.82,
            f1_score=0.83,
        )
    )

    response = service.promote_if_better(candidate.model_id)

    assert response.promoted is False
    assert response.promotion_metric == "f1_score"
    assert response.candidate_metric == 0.83
    assert response.active_metric == 0.80
    assert response.promotion_recommended is False
    assert service.get_active_model().version == "v1"
