from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserPublic
from app.services.users import UserService, UserServiceError

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_error_to_http(exc: UserServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = UserService(db).authenticate(
            username=payload.username,
            password=payload.password,
        )
    except UserServiceError as exc:
        raise _user_error_to_http(exc) from exc
    token = create_access_token(subject=str(user.user_id), role=user.role.value)
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return current_user


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "ok"}
