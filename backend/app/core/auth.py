from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.crud.users import get_user
from app.models.enums import UserRole
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
        subject = payload.get("sub")
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    user = get_user(db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authenticated user not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


def require_doctor_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {UserRole.USER, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Doctor or admin role required")
    return current_user
