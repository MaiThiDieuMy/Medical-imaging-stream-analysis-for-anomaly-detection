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
        lines = [
            "# HELP analyze_requests_total Total analyze service requests.",
            "# TYPE analyze_requests_total counter",
            f"analyze_requests_total {counters.get('analyze_requests_total', 0)}",
            "# HELP analyze_cache_hits_total Total analyze cache hits.",
            "# TYPE analyze_cache_hits_total counter",
            f"analyze_cache_hits_total {counters.get('analyze_cache_hits_total', 0)}",
            "# HELP analyze_cache_misses_total Total analyze cache misses.",
            "# TYPE analyze_cache_misses_total counter",
            f"analyze_cache_misses_total {counters.get('analyze_cache_misses_total', 0)}",
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
