from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.auth import UserPublic


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)
    role: str = Field(pattern="^(user|admin)$")


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=128)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    is_active: bool | None = None


class UserResponse(UserPublic):
    pass
