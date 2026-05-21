from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.crud.ai_models import list_models  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        for model in list_models(db):
            active = "active" if model.is_active else "inactive"
            print(
                f"{model.model_id} | {model.model_name}:{model.version} | "
                f"{active} | f1={model.f1_score}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
