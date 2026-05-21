from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.services.mlops import MLOpsService  # noqa: E402
from app.services.model_admin import ModelAdminService  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        model_service = ModelAdminService(db)
        active_model = model_service.get_active_model()
        print(
            "active_model="
            f"{active_model.model_name}:{active_model.version} "
            f"id={active_model.model_id}"
        )
        print(MLOpsService(db).retraining_summary())
    finally:
        db.close()


if __name__ == "__main__":
    main()
