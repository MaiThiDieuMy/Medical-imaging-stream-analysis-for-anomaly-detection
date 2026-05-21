from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.ai_models import get_active_model
from app.models.analysis_job import AnalysisJob
from app.models.case_review import CaseReview
from app.models.enums import ProcessingStatus
from app.models.xray_case import XRayCase
from app.monitoring.metrics import snapshot
from app.schemas.monitoring import MonitoringActiveModel
from app.services.reviews import REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED


class MonitoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self) -> dict[str, object]:
        database_reachable = self._database_reachable()
        active_model = None
        total_cases = 0
        total_jobs_by_status = {
            status.value: 0
            for status in ProcessingStatus
        }
        reviews_by_status = {
            "pending": 0,
            REVIEW_STATUS_CONFIRMED: 0,
            REVIEW_STATUS_CORRECTED: 0,
            "rejected": 0,
        }

        if database_reachable:
            active = get_active_model(self.db)
            if active is not None:
                active_model = MonitoringActiveModel.model_validate(
                    active,
                    from_attributes=True,
                )
            total_cases = self.db.scalar(select(func.count()).select_from(XRayCase)) or 0
            total_jobs_by_status.update(self._count_jobs_by_status())
            reviews_by_status.update(self._count_reviews_by_status())

        training_ready_cases = (
            reviews_by_status[REVIEW_STATUS_CONFIRMED]
            + reviews_by_status[REVIEW_STATUS_CORRECTED]
        )

        return {
            "backend_status": "ok",
            "database_reachable": database_reachable,
            "redis_broker_status": self._redis_broker_status(),
            "celery_queue_length": self._celery_queue_length(),
            "active_model": active_model,
            "total_cases": total_cases,
            "total_jobs_by_status": total_jobs_by_status,
            "reviews_by_status": reviews_by_status,
            "pending_reviews": reviews_by_status["pending"],
            "training_ready_cases": training_ready_cases,
            "metrics": snapshot(),
        }

    def prometheus_text(self) -> str:
        counters = snapshot()
        database_reachable = self._database_reachable()
        job_counts = self._count_jobs_by_status() if database_reachable else {}
        review_counts = self._count_reviews_by_status() if database_reachable else {}
        active_model = get_active_model(self.db) if database_reachable else None
        celery_queue_length = self._celery_queue_length()
        completed_jobs = max(
            counters.get("inference_jobs_completed_total", 0),
            job_counts.get(ProcessingStatus.COMPLETED.value, 0),
        )
        failed_jobs = max(
            counters.get("inference_jobs_failed_total", 0),
            job_counts.get(ProcessingStatus.FAILED.value, 0),
        )
        lines = [
            "# HELP backend_info Static backend application information.",
            "# TYPE backend_info gauge",
            (
                'backend_info{app_name="'
                f'{self._label_value(settings.app_name)}",app_version="'
                f'{self._label_value(settings.app_version)}",app_env="'
                f'{self._label_value(settings.app_env)}"}} 1'
            ),
            "# HELP analyze_requests_total Total analyze service requests.",
            "# TYPE analyze_requests_total counter",
            f"analyze_requests_total {counters.get('analyze_requests_total', 0)}",
            "# HELP analyze_cache_hits_total Total analyze cache hits.",
            "# TYPE analyze_cache_hits_total counter",
            f"analyze_cache_hits_total {counters.get('analyze_cache_hits_total', 0)}",
            "# HELP analyze_cache_misses_total Total analyze cache misses.",
            "# TYPE analyze_cache_misses_total counter",
            f"analyze_cache_misses_total {counters.get('analyze_cache_misses_total', 0)}",
            "# HELP inference_jobs_completed_total Completed inference jobs observed by the system.",
            "# TYPE inference_jobs_completed_total counter",
            f"inference_jobs_completed_total {completed_jobs}",
            "# HELP inference_jobs_failed_total Failed inference jobs observed by the system.",
            "# TYPE inference_jobs_failed_total counter",
            f"inference_jobs_failed_total {failed_jobs}",
            "# HELP minio_storage_errors_total MinIO storage errors observed by the backend.",
            "# TYPE minio_storage_errors_total counter",
            f"minio_storage_errors_total {counters.get('minio_storage_errors_total', 0)}",
            "# HELP mlflow_registration_total MLflow registration attempts observed by the backend.",
            "# TYPE mlflow_registration_total counter",
            f"mlflow_registration_total {counters.get('mlflow_registration_total', 0)}",
            "# HELP celery_queue_length Current Redis list length for the default Celery queue.",
            "# TYPE celery_queue_length gauge",
            f"celery_queue_length {celery_queue_length if celery_queue_length is not None else -1}",
            "# HELP analysis_jobs_total Analysis jobs by status.",
            "# TYPE analysis_jobs_total gauge",
        ]
        for status in sorted({item.value for item in ProcessingStatus} | set(job_counts)):
            lines.append(
                f'analysis_jobs_total{{status="{status}"}} {job_counts.get(status, 0)}'
            )
        lines.extend(
            [
                "# HELP case_reviews_total Case reviews by status.",
                "# TYPE case_reviews_total gauge",
            ]
        )
        for status in sorted(
            {"pending", REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CORRECTED, "rejected"}
            | set(review_counts)
        ):
            lines.append(
                f'case_reviews_total{{status="{status}"}} {review_counts.get(status, 0)}'
            )
        lines.extend(
            [
                "# HELP model_active_info Active AI model metadata.",
                "# TYPE model_active_info gauge",
            ]
        )
        if active_model is not None:
            lines.append(
                'model_active_info{model_id="'
                f'{self._label_value(str(active_model.model_id))}",model_name="'
                f'{self._label_value(active_model.model_name)}",version="'
                f'{self._label_value(active_model.version)}"}} 1'
            )
        else:
            lines.append('model_active_info{model_id="",model_name="",version=""} 0')
        lines.append("")
        return "\n".join(lines)

    def _database_reachable(self) -> bool:
        try:
            self.db.execute(text("SELECT 1")).scalar_one()
            return True
        except Exception:
            self.db.rollback()
            return False

    def _count_jobs_by_status(self) -> dict[str, int]:
        rows = self.db.execute(
            select(AnalysisJob.status, func.count()).group_by(AnalysisJob.status)
        ).all()
        return {
            status.value if hasattr(status, "value") else str(status): count
            for status, count in rows
        }

    def _count_reviews_by_status(self) -> dict[str, int]:
        rows = self.db.execute(
            select(CaseReview.status, func.count()).group_by(CaseReview.status)
        ).all()
        return {status: count for status, count in rows}

    @staticmethod
    def _redis_broker_status() -> str:
        try:
            from redis import Redis

            client = Redis.from_url(
                settings.celery_broker_url,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            return "ok" if client.ping() else "unreachable"
        except ImportError:
            return "redis-client-unavailable"
        except Exception:
            return "unreachable"

    @staticmethod
    def _celery_queue_length() -> int | None:
        try:
            from redis import Redis

            client = Redis.from_url(
                settings.celery_broker_url,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            return int(client.llen("celery"))
        except Exception:
            return None

    @staticmethod
    def _label_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
