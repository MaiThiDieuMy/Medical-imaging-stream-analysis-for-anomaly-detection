from datetime import datetime, timezone

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.health.worker_health")
def worker_health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "celery_worker",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
