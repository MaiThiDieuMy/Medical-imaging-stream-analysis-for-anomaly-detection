from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.crud.patients import get_patient
from app.models.enums import UserRole
from app.models.patient import Patient
from app.models.user import User
from app.models.xray_case import XRayCase
from app.schemas.cases import PatientUpdate


class PatientServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PatientService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def update_patient(
        self,
        patient_id: uuid.UUID,
        payload: PatientUpdate,
        user: User,
    ) -> Patient:
        patient = get_patient(self.db, patient_id=patient_id)
        if patient is None:
            raise PatientServiceError("Patient not found", status_code=404)
        if user.role != UserRole.ADMIN and not self._user_can_access_patient(
            patient_id,
            user.user_id,
        ):
            raise PatientServiceError("Patient not found", status_code=404)

        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(patient, field, value)
        self.db.commit()
        self.db.refresh(patient)
        return patient

    def _user_can_access_patient(
        self,
        patient_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        return bool(
            self.db.scalar(
                select(
                    exists().where(
                        XRayCase.patient_id == patient_id,
                        XRayCase.uploaded_by_id == user_id,
                    )
                )
            )
        )
