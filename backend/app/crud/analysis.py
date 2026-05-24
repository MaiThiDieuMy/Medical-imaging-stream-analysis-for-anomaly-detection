from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.crud.patients import create_patient, get_patient_by_code
from app.models.ai_model import AIModel
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.enums import ProcessingStatus
from app.models.patient import Patient
from app.models.xray_case import XRayCase
from app.models.xray_image import XRayImage


def get_or_update_patient(
    db: Session,
    *,
    patient_code: str,
    full_name: str,
    gender: str,
    birth_year: int | None,
    department: str | None,
) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.patient_code == patient_code)
    ).scalar_one_or_none()

    if patient is None:
        patient = Patient(
            patient_code=patient_code,
            full_name=full_name,
            gender=gender,
            birth_year=birth_year,
            department=department,
        )
        db.add(patient)
        return patient

    patient.full_name = full_name
    patient.gender = gender
    patient.birth_year = birth_year
    patient.department = department
    return patient


def create_patient_for_analysis(
    db: Session,
    *,
    patient_code: str | None,
    full_name: str,
    gender: str,
    birth_year: int | None,
    department: str | None,
) -> Patient:
    if patient_code:
        if get_patient_by_code(db, patient_code=patient_code) is not None:
            raise ValueError(f"Patient ID '{patient_code}' already exists")
        return create_patient(
            db,
            patient_code=patient_code,
            full_name=full_name,
            gender=gender,
            birth_year=birth_year,
            department=department,
        )

    for _ in range(10):
        generated_code = f"PAT-{uuid.uuid4().hex[:10].upper()}"
        try:
            return create_patient(
                db,
                patient_code=generated_code,
                full_name=full_name,
                gender=gender,
                birth_year=birth_year,
                department=department,
            )
        except IntegrityError:
            db.rollback()

    raise ValueError("Could not generate a unique Patient ID")


def get_cached_case_with_results(
    db: Session,
    *,
    image_hash: str,
    model_id: uuid.UUID,
) -> tuple[XRayCase, list[AnalysisResult]] | None:
    statement = (
        select(XRayCase)
        .join(XRayImage)
        .join(AnalysisResult, AnalysisResult.case_id == XRayCase.case_id)
        .where(
            XRayImage.image_hash == image_hash,
            AnalysisResult.model_id == model_id,
        )
        .order_by(XRayCase.created_at.desc())
        .options(
            selectinload(XRayCase.analysis_results),
            selectinload(XRayCase.analysis_job),
            selectinload(XRayCase.image),
        )
    )
    case = db.execute(statement).unique().scalars().first()
    if case is None:
        return None

    results = [
        result for result in case.analysis_results if result.model_id == model_id
    ]
    if not results:
        return None

    return case, sorted(results, key=lambda item: item.label_name)


def create_queued_analysis(
    db: Session,
    *,
    patient: Patient,
    model: AIModel,
    image_path: str,
    image_hash: str,
    file_name: str,
    file_format: str,
    note: str | None,
    uploaded_by_id: uuid.UUID | None = None,
) -> tuple[XRayCase, XRayImage, AnalysisJob]:
    case = XRayCase(
        patient=patient,
        uploaded_by_id=uploaded_by_id,
        status=ProcessingStatus.QUEUED,
        note=note,
    )
    db.add(case)
    db.flush()

    image = XRayImage(
        case_id=case.case_id,
        file_name=file_name,
        image_path=image_path,
        image_hash=image_hash,
        file_format=file_format,
    )
    job = AnalysisJob(
        case_id=case.case_id,
        model_id=model.model_id,
        status=ProcessingStatus.QUEUED,
    )
    db.add_all([image, job])
    db.flush()

    return case, image, job


def get_case_with_job(
    db: Session,
    *,
    case_id: uuid.UUID,
) -> XRayCase | None:
    return db.execute(
        select(XRayCase)
        .where(XRayCase.case_id == case_id)
        .options(selectinload(XRayCase.analysis_job))
    ).scalar_one_or_none()


def get_job_with_model(
    db: Session,
    *,
    job_id: uuid.UUID,
) -> AnalysisJob | None:
    return db.execute(
        select(AnalysisJob)
        .where(AnalysisJob.job_id == job_id)
        .options(selectinload(AnalysisJob.model))
    ).scalar_one_or_none()


def get_case_with_results(
    db: Session,
    *,
    case_id: uuid.UUID,
) -> XRayCase | None:
    return db.execute(
        select(XRayCase)
        .where(XRayCase.case_id == case_id)
        .options(
            selectinload(XRayCase.analysis_results).selectinload(
                AnalysisResult.model
            ),
            selectinload(XRayCase.analysis_job).selectinload(AnalysisJob.model),
        )
    ).scalar_one_or_none()
