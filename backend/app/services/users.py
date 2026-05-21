from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.crud.users import (
    create_user,
    get_user,
    get_user_by_username,
    list_users,
    update_user,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.users import UserCreate, UserUpdate


class UserServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def authenticate(self, *, username: str, password: str) -> User:
        user = get_user_by_username(self.db, username=username)
        if user is None or not verify_password(password, user.password_hash):
            raise UserServiceError("Invalid username or password", status_code=401)
        if not user.is_active:
            raise UserServiceError("User account is inactive", status_code=403)
        return user

    def list_users(self) -> list[User]:
        return list_users(self.db)

    def get_user(self, user_id: uuid.UUID) -> User:
        user = get_user(self.db, user_id=user_id)
        if user is None:
            raise UserServiceError("User not found", status_code=404)
        return user

    def create_user(self, payload: UserCreate) -> User:
        if get_user_by_username(self.db, username=payload.username) is not None:
            raise UserServiceError("Username already exists", status_code=409)
        try:
            user = create_user(
                self.db,
                username=payload.username.strip(),
                password_hash=hash_password(payload.password),
                full_name=payload.full_name.strip(),
                role=UserRole(payload.role),
            )
            self.db.commit()
            self.db.refresh(user)
            return user
        except IntegrityError as exc:
            self.db.rollback()
            raise UserServiceError("Username already exists", status_code=409) from exc

    def update_user(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        user = self.get_user(user_id)
        password_hash = (
            hash_password(payload.password) if payload.password is not None else None
        )
        update_user(
            self.db,
            user=user,
            full_name=payload.full_name.strip()
            if payload.full_name is not None
            else None,
            role=UserRole(payload.role) if payload.role is not None else None,
            password_hash=password_hash,
            is_active=payload.is_active,
        )
        self.db.commit()
        self.db.refresh(user)
        return user
