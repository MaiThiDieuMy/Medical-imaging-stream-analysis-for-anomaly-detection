from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.crud.users import create_user, get_user_by_username, update_user
from app.models.enums import UserRole

DEMO_USERS = [
    {
        "username": "admin_demo",
        "password": "admin123",
        "full_name": "Demo Admin",
        "role": UserRole.ADMIN,
    },
    {
        "username": "doctor_demo",
        "password": "doctor123",
        "full_name": "Demo Doctor",
        "role": UserRole.USER,
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        for demo_user in DEMO_USERS:
            user = get_user_by_username(db, username=demo_user["username"])
            password_hash = hash_password(demo_user["password"])
            if user is None:
                user = create_user(
                    db,
                    username=demo_user["username"],
                    password_hash=password_hash,
                    full_name=demo_user["full_name"],
                    role=demo_user["role"],
                )
                action = "created"
            else:
                update_user(
                    db,
                    user=user,
                    password_hash=password_hash,
                    full_name=demo_user["full_name"],
                    role=demo_user["role"],
                )
                action = "updated"
            print(
                f"{action}: {user.username} / {demo_user['password']} "
                f"({user.role.value})"
            )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
