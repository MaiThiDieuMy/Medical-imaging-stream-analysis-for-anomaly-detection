from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.crud.ai_models import ensure_demo_active_model  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        model, created = ensure_demo_active_model(db)
        action = "created" if created else "using"
        print(
            f"{action} active model: "
            f"id={model.model_id} name={model.model_name} version={model.version}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
