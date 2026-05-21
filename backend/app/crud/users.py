from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


def get_user(db: Session, *, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_user_by_username(db: Session, *, username: str) -> User | None:
    return db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()


def create_user(
    db: Session,
    *,
    username: str,
    password_hash: str,
    full_name: str,
    role: UserRole,
) -> User:
    user = User(
        username=username,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def update_user(
    db: Session,
    *,
    user: User,
    full_name: str | None = None,
    role: UserRole | None = None,
    password_hash: str | None = None,
    is_active: bool | None = None,
) -> User:
    if full_name is not None:
        user.full_name = full_name
    if role is not None:
        user.role = role
    if password_hash is not None:
        user.password_hash = password_hash
    if is_active is not None:
        user.is_active = is_active
    db.flush()
    return user
