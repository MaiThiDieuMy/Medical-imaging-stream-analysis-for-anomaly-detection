from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.services.mlops import MLOpsService


def main() -> None:
    db = SessionLocal()
    try:
        result = MLOpsService(db).export_manifest()
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
