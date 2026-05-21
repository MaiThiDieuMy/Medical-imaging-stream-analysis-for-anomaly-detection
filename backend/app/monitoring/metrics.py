from __future__ import annotations

from collections import Counter
from threading import Lock

_counters: Counter[str] = Counter()
_lock = Lock()


def record_request(*, path: str, method: str, status_code: int) -> None:
    with _lock:
        _counters["requests_total"] += 1
        _counters[f"requests_status_{status_code}"] += 1
        _counters[f"requests_method_{method.upper()}"] += 1
        if path.startswith("/api/v1/analyze"):
            _counters["analyze_http_requests_total"] += 1


def record_analyze_result(*, cache_hit: bool) -> None:
    with _lock:
        _counters["analyze_requests_total"] += 1
        if cache_hit:
            _counters["analyze_cache_hits_total"] += 1
            _counters["cache_hit_total"] += 1
        else:
            _counters["analyze_cache_misses_total"] += 1
            _counters["cache_miss_total"] += 1


def record_inference_job_completed() -> None:
    with _lock:
        _counters["inference_jobs_completed_total"] += 1


def record_inference_job_failed() -> None:
    with _lock:
        _counters["inference_jobs_failed_total"] += 1


def record_minio_storage_error(*, operation: str) -> None:
    normalized_operation = operation.strip().lower().replace("-", "_") or "unknown"
    with _lock:
        _counters["minio_storage_errors_total"] += 1
        _counters[f"minio_storage_errors_{normalized_operation}_total"] += 1


def record_mlflow_registration(*, status: str) -> None:
    normalized_status = status.strip().lower().replace("-", "_") or "unknown"
    with _lock:
        _counters["mlflow_registration_total"] += 1
        _counters[f"mlflow_registration_{normalized_status}_total"] += 1


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)
