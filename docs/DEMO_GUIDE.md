# Demo Guide

Use this guide for a final presentation or report walkthrough. The system is a development/presentation environment, not a clinically certified product.

## 1. Start Services

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed_demo_users.py
docker compose exec backend python scripts/seed_demo_model.py
```

Open:

- Frontend: http://localhost:5173
- Backend API server root: http://localhost:8000
- Backend Swagger: http://localhost:8000/docs
- MLflow: http://localhost:5000
- MinIO console: http://localhost:9001
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Loki: http://localhost:3100
- cAdvisor: http://localhost:8080
- Flower: http://localhost:5555
- RedisInsight: http://localhost:5540

The backend is an API server, not the frontend UI. Use the frontend URL for the hospital workflow and Swagger for direct API checks.

MLflow UI opens in the browser at `http://localhost:5000`. Backend and Celery keep using the internal Docker URL `MLFLOW_TRACKING_URI=http://mlflow:5000`. If MLflow shows `Invalid Host header - possible DNS rebinding attack detected`, add the browser host/IP/domain to `MLFLOW_ALLOWED_HOSTS` in `.env`, then restart only MLflow:

```bash
docker compose up -d --build mlflow
```

Local demo value:

```env
MLFLOW_ALLOWED_HOSTS=localhost,localhost:*,127.0.0.1,127.0.0.1:*,mlflow,mlflow:*,0.0.0.0,0.0.0.0:*
```

For LAN or domain access, append entries such as `192.168.1.10,192.168.1.10:*` or `mlflow.example.com,mlflow.example.com:*`. Avoid a global `*` wildcard in production because it weakens MLflow host-header protection.

Development/demo credentials:

- Doctor/KTV: `doctor_demo` / `doctor123`
- Admin: `admin_demo` / `admin123`
- Grafana: `admin` / `admin123`

## 2. Doctor/KTV Workflow

1. Log in as `doctor_demo`.
2. Open `Dashboard` and point out personal case counts, recent cases, and review shortcuts.
3. Open `Phân tích ảnh`.
4. Select a local PNG/JPG image. Do not commit this image to Git.
5. Confirm the image preview, file name, file size, and MIME type are visible.
6. Enter patient metadata for the walkthrough.
7. Click `Phân tích AI`.
8. Explain that the backend validates the file, computes `image_hash`, and checks cache before uploading to MinIO or creating a job.
9. On cache miss, show queued/processing/completed status.
10. Show four labels: No Finding, Effusion, Infiltration, Atelectasis.
11. Confirm the AI result or correct the single true label if this case should enter the retraining buffer.
12. Open `Lịch sử ca chụp`, view stored image, case detail, and click `Xuất báo cáo`.

What to say:

> AI analysis is triggered only after the user clicks Analyze. Cache lookup happens before saving duplicate images or creating a Celery job.

> Raw AI predictions are never training labels by themselves. High-confidence and low-confidence cases both require doctor/admin confirmation or correction before retraining.

## 3. Cache Hit Proof

1. Upload the exact same image again with the same active model.
2. Show the cache-hit message: `Kết quả được lấy từ cache, không tạo job mới.`
3. Explain that cache hit does not upload a duplicate image to MinIO, create a new case/job, enqueue Celery, or run inference again.

What to say:

> The cache key is image_hash plus active model. This prevents repeated processing for the same image/model pair.

## 4. Admin Model And MLflow Workflow

1. Log out.
2. Log in as `admin_demo`.
3. Open `Dashboard` and show total cases, users, active model, pending reviews, and training-ready samples.
4. Open `Quản lý người dùng`.
5. Create or update a user and show that accounts are deactivated, not hard-deleted.
6. Open `Quản lý mô hình`.
7. Register `best_model.pth` to MLflow with `Đăng ký model lên MLflow`.
8. Open MLflow at http://localhost:5000 and show the run, checkpoint artifact, metadata JSON, and registered model version.
9. Register a metadata-only candidate model if needed.
10. Click `Promote` or `Kích hoạt` when appropriate.
11. Archive an inactive model to show metadata cleanup without deleting weights from disk.

CLI equivalent:

```bash
docker compose exec backend python scripts/register_best_model_to_mlflow.py
```

Use real evaluation metrics when available:

```bash
docker compose exec backend python scripts/register_best_model_to_mlflow.py --accuracy 0.90 --precision-score 0.88 --recall-score 0.87 --f1-score 0.875
```

What to say:

> MLflow now stores the tracking run and registered model version. The database keeps the active model metadata and approved metrics only.

## 5. Review And Retraining Summary

1. Open `Duyệt/gán nhãn lại`.
2. Show pending reviews if available.
3. Confirm AI labels or correct the four labels.
4. Explain that pending reviews and raw high-confidence AI predictions are not training-ready.
5. Show retraining summary and training-ready case counts.
6. Export retraining manifest and explain that only confirmed/corrected labels with stored confirmation evidence are included.
7. Trigger retraining only after the configured confirmed-sample threshold is reached.

Threshold `N` is configured with `RETRAIN_MIN_CONFIRMED_SAMPLES` in `.env`.
`N` counts only new DB cases confirmed/corrected by doctor/admin. Local
`training_seed` images are used to support fine-tuning, but they do not count
toward `N`.
For pipeline testing, set `RETRAIN_MIN_CONFIRMED_SAMPLES=1`, restart backend and
Celery, confirm one completed case, then start fine-tuning from the Admin MLOps page
or with:

```bash
docker compose exec backend python scripts/retraining_smoke_test.py
docker compose exec backend python scripts/retraining_smoke_test.py --start
docker compose exec backend python scripts/inspect_training_data.py
```

Use `N=2`, `N=5`, or `N=10` for progressively larger demos. To test auto job
creation, set `RETRAIN_AUTO_START=true`, restart `backend` and `celery_worker`,
then confirm/correct enough completed cases. Very small values are for pipeline
validation only, not clinically meaningful training. Retrained checkpoints are saved
under `artifacts/retrained_models/`, ignored by Git, and logged to MLflow at
http://localhost:5000. Admin must review the inactive candidate model before activating
or promoting it.

Local training seed:

```text
artifacts/training_seed/Atelectasis/
artifacts/training_seed/Effusion/
artifacts/training_seed/Infiltration/
artifacts/training_seed/No_Finding/
```

Fixed evaluation set:

```text
artifacts/evaluation_set/Atelectasis/
artifacts/evaluation_set/Effusion/
artifacts/evaluation_set/Infiltration/
artifacts/evaluation_set/No_Finding/
```

Recommended local counts:

- Pipeline test: 5-10 images/class seed, 5 images/class eval.
- Demo: 50-100 images/class seed, 20-50 images/class eval.
- Stronger evaluation: 200+ images/class seed, 100+ images/class eval.

Do not commit seed or evaluation images. If the evaluation folder is missing or empty, the system
falls back to a validation split only to validate the pipeline and shows a warning.
MLflow logs `evaluation_source` so the demo can distinguish fixed evaluation from
pipeline-only fallback evaluation.
`MODEL_AUTO_PROMOTE=false` by default, so retrained models remain inactive
candidates until Admin explicitly promotes them.

What to say:

> AI predictions are not used as training labels until a doctor/admin confirms or corrects them, regardless of confidence.

## 6. Case Detail And Archive Safety

1. Open `Tất cả ca chụp` as Admin.
2. Search/filter by patient code or status if needed.
3. Click `Xem` to inspect image, patient metadata, job status, prediction results, and review status.
4. Click `Xuất báo cáo` to open the browser-printable HTML report.
5. Click `Lưu trữ` on a case that is no longer needed in the main list.
6. Explain that archive is soft: images, jobs, and analysis results remain in the database/storage.

## 7. Monitoring

1. Open `Monitoring` as Admin.
2. Show backend status, DB reachability, Redis broker status, Celery queue length, active model, job counts, review counts, and request/cache counters.
3. Open Grafana at http://localhost:3000 and Prometheus at http://localhost:9090.
4. Explain Prometheus scrapes backend `/metrics`, cAdvisor, Redis exporter, PostgreSQL exporter, Loki, and Promtail.
5. In Grafana, open the `Medical Imaging Demo` folder and show the System Overview, Application Overview, Celery And Redis, Logs Overview, and PostgreSQL And MinIO dashboards.
6. Open Flower at http://localhost:5555 for Celery task visibility and RedisInsight at http://localhost:5540 for Redis inspection.
7. In Prometheus, useful queries are:

```promql
analyze_requests_total
analyze_cache_hits_total
analyze_cache_misses_total
analysis_jobs_total
case_reviews_total
celery_queue_length
model_active_info
minio_storage_errors_total
up{job="redis-exporter"}
up{job="postgres-exporter"}
```

## 8. Final Validation

Run:

```powershell
.\scripts\final_check.ps1
```

If Docker services are not running, start them first with:

```bash
docker compose up -d --build
```

## 9. Report Notes

Mention these limitations clearly:

- The local model is for development/presentation and is not clinically certified.
- Uploaded images are stored in MinIO using stable object keys.
- Case report export is HTML suitable for browser print/save-as-PDF.
- DICOM is not supported yet.
- Manual MLflow registration only logs an existing checkpoint; the retraining task is the path that fine-tunes and logs a new candidate checkpoint.
- Retraining only uses cases with stored confirmation evidence in `confirmed_labels`; raw AI predictions are excluded even when high-confidence.
- Evidently AI is a future option for drift/performance monitoring after ground truth is available. It does not replace MLflow runs, fixed evaluation metrics, or the promotion gate.
- Do not commit real patient data, sample images, model weights, or `.env`.
