from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient


def get_patient(db: Session, *, patient_id: uuid.UUID) -> Patient | None:
    return db.get(Patient, patient_id)


def get_patient_by_code(db: Session, *, patient_code: str) -> Patient | None:
    return db.execute(
        select(Patient).where(Patient.patient_code == patient_code)
    ).scalar_one_or_none()


def create_patient(
    db: Session,
    *,
    patient_code: str,
    full_name: str,
    gender: str,
    birth_year: int | None,
    department: str | None,
) -> Patient:
    patient = Patient(
        patient_code=patient_code,
        full_name=full_name,
        gender=gender,
        birth_year=birth_year,
        department=department,
    )
    db.add(patient)
    db.flush()
    return patient
