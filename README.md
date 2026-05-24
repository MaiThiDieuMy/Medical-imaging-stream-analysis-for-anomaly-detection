# Medical Imaging Stream Analysis for Anomaly Detection

Development-ready chest X-ray streaming inference system with a lightweight MLOps review loop. The project supports a hospital-style workflow where Doctor/KTV users upload a chest X-ray, request AI analysis, track asynchronous processing, review results, and where Admin users manage models, users, reviews, and monitoring.

This is a development and presentation demo. The local model is not clinically certified.

## Main Features

- Login with Doctor/KTV and Admin roles.
- Role-specific dashboards and navigation for clinical and admin workflows.
- Chest X-ray upload with patient metadata and image preview.
- Cache check by `image_hash + active model` before saving duplicate images or creating jobs.
- Asynchronous inference with Celery and Redis.
- Four X-ray classes: No Finding, Effusion, Infiltration, Atelectasis.
- Local real-model mode uses the Kaggle MobileNetV3-Small checkpoint at `artifacts/models/best_model.pth`.
- One `AnalysisResult` row per label.
- Admin model management with candidate registration and promotion by `f1_score`.
- MLflow Tracking and Model Registry integration for local checkpoint registration.
- Review workflow for uncertain cases and manual confirmation/correction for any completed case.
- Raw AI predictions, including high-confidence predictions, never become training-ready until doctor/admin confirmation.
- Confirmed/corrected labels only become training-ready after doctor/admin review evidence is stored.
- Stored-image retrieval, case history/detail, and browser-printable HTML reports.
- Retraining manifest export from confirmed/corrected labels only.
- Operations monitoring with Prometheus, Grafana, Loki/Promtail logs, cAdvisor,
  Flower, RedisInsight, Redis exporter, and PostgreSQL exporter.
- Soft archive/deactivate actions for cases, users, and model metadata. Historical analysis results are not hard-deleted.

## Architecture Summary

The central table is `xray_cases`. Each case links patient metadata, the uploaded image, an asynchronous analysis job, AI results, and optional review records.

Analyze flow:

1. Doctor/KTV logs in and uploads image metadata.
2. Backend validates metadata/file and computes `image_hash`.
3. Backend loads the active `AIModel`.
4. Backend checks cache by `image_hash + active model_id`.
5. Cache hit returns existing results immediately.
6. Cache miss saves/updates patient, uploads the image to MinIO, creates `XRayCase`, `XRayImage`, `AnalysisJob`, and enqueues Celery.
7. Worker downloads the image from MinIO, loads the active model, runs inference, saves four label results, updates job/case status, and creates review records for uncertain cases.

## Tech Stack

- Backend: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- Queue: Celery, Redis
- Database: PostgreSQL
- Storage: MinIO object storage for uploaded X-ray images
- ML: PyTorch/TorchVision inference with MobileNetV3-Small local checkpoint support
- MLOps foundation: MLflow tracking/registry APIs, admin model registry APIs, review/retraining buffer APIs
- Frontend: React + Vite + TypeScript
- Deployment: Docker Compose

## Folder Structure

```text
backend/
  app/api/          FastAPI routes
  app/core/         config, database, auth/security
  app/models/       SQLAlchemy models
  app/schemas/      Pydantic schemas
  app/crud/         database operations
  app/services/     business logic
  app/tasks/        Celery tasks
  app/ml/           preprocessing, model loading, inference
  app/mlops/        metric helpers
  app/monitoring/   lightweight counters
  scripts/          seed and smoke scripts
infra/
  prometheus/       scrape config and alert rules
  grafana/          Prometheus/Loki datasource and dashboard provisioning
  loki/             local Loki config for Docker logs
  promtail/         Docker log scraping config
frontend/
  src/api/          typed API client
  src/pages/        app screens
  src/components/   shared UI
  src/types/        TypeScript API types
docs/
  SYSTEM_DESIGN.md
  WORKFLOW.md
  DEMO_GUIDE.md
artifacts/
  models/           local weights placeholder, ignored except README
  sample_images/    local demo images placeholder, ignored except README
  training_seed/    local labeled seed images, ignored except README
  retraining_manifests/ generated manifests, ignored except README
  evaluation_set/   local fixed evaluation images, ignored except README
```

## Demo Accounts

Seed these accounts with `backend/scripts/seed_demo_users.py`:

- Admin: `admin_demo` / `admin123`
- Doctor/KTV: `doctor_demo` / `doctor123`

These are demo credentials only. Do not put real credentials in `.env`.

## Run With Docker

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed_demo_users.py
docker compose exec backend python scripts/seed_demo_model.py
```

The default Docker Compose ML config expects the local checkpoint at:

```text
artifacts/models/best_model.pth
```

This file is mounted into backend and Celery containers at `/app/artifacts/models/best_model.pth`. It is ignored by Git and is not copied into the Docker image. Retrained candidate checkpoints are written under `artifacts/retrained_models/` and stay ignored by Git.

Local labeled data folders are mounted into backend/Celery containers:

```text
artifacts/training_seed/Atelectasis/
artifacts/training_seed/Effusion/
artifacts/training_seed/Infiltration/
artifacts/training_seed/No_Finding/

artifacts/evaluation_set/Atelectasis/
artifacts/evaluation_set/Effusion/
artifacts/evaluation_set/Infiltration/
artifacts/evaluation_set/No_Finding/
```

`training_seed` is used for fine-tuning together with new doctor/admin confirmed
or corrected DB cases, but it does not count toward retraining threshold `N`.
`evaluation_set` is used only for evaluation, never training. Do not commit image
data or model weights.

## URLs

- Frontend: http://localhost:5173
- Backend API server root: http://localhost:8000
- Backend Swagger: http://localhost:8000/docs
- Backend health: http://localhost:8000/health
- API v1 health: http://localhost:8000/api/v1/health
- MinIO console: http://localhost:9001
- MLflow: http://localhost:5000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Loki: http://localhost:3100
- cAdvisor: http://localhost:8080
- Flower: http://localhost:5555
- RedisInsight: http://localhost:5540

The backend is an API server, not the web frontend. Use the frontend URL for the application UI and the Swagger URL for API exploration.

MLflow is accessed from the browser at `http://localhost:5000`. Backend and Celery containers must keep using `MLFLOW_TRACKING_URI=http://mlflow:5000`. If MLflow shows `Invalid Host header - possible DNS rebinding attack detected`, add the host/IP/domain to `MLFLOW_ALLOWED_HOSTS` in `.env` and restart MLflow:

```bash
docker compose up -d --build mlflow
```

Local demo hosts:

```env
MLFLOW_ALLOWED_HOSTS=localhost,localhost:*,127.0.0.1,127.0.0.1:*,mlflow,mlflow:*,0.0.0.0,0.0.0.0:*
```

For LAN or domain access, append values such as `192.168.1.10,192.168.1.10:*` or `mlflow.example.com,mlflow.example.com:*`. Do not use a global `*` wildcard in production unless you understand the DNS rebinding risk.

Grafana demo login:

- Username: `admin`
- Password: `admin123`

Prometheus query examples:

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

## Walkthrough Workflow

1. Open the frontend and log in as `doctor_demo`.
2. Choose a local PNG/JPG chest X-ray image.
3. Confirm the image preview, file name, size, and MIME type are shown.
4. Click `Phân tích AI`.
5. Watch status move through queued/processing/completed.
6. Confirm four labels are displayed.
7. Upload the same image again and verify the cache hit message: `Kết quả được lấy từ cache, không tạo job mới.`
8. Log out and log in as `admin_demo`.
9. Open model management, register a candidate model, then promote if better.
10. Open review/MLOps, confirm or correct pending reviews.
11. Open case history/detail, stored image, and HTML report export.
12. Confirm the completed case result or correct the single true label before treating it as training-ready.
13. Open retraining summary, export a manifest if labels have been confirmed/corrected, trigger retraining when the threshold is reached, and view monitoring/Grafana.
13. Open Monitoring as Admin and use the infrastructure/log links for Prometheus, Grafana, Loki, Flower, RedisInsight, cAdvisor, MinIO, and MLflow.

## Product UI Workflow

Doctor/KTV users see the clinical workflow only:

- `Dashboard`: personal case counts, recent cases, pending review shortcut.
- `Phân tích ảnh`: upload and preview image, enter patient metadata, run AI analysis.
- `Lịch sử ca chụp`: view owned cases, stored image, prediction results, and HTML report.
- `Ca cần duyệt`: confirm or correct low-confidence labels before they become training-ready.
- Completed case detail/result screens can also confirm or correct high-confidence AI results; raw predictions are not counted for retraining.

Admin users see operational tools:

- `Dashboard`: system totals, active model, pending reviews, training-ready counts.
- `Quản lý người dùng`: create/update users and deactivate accounts instead of deleting them.
- `Quản lý mô hình`: register candidate metadata, activate/promote models, archive inactive model metadata.
- `Duyệt/gán nhãn lại`: review uncertain cases and manage retraining-ready labels.
- `Tất cả ca chụp`: inspect cases and archive cases without deleting images or results.
- `Monitoring`: backend, Redis, job/review metrics, Prometheus, Grafana, Loki, Flower, RedisInsight, and cAdvisor links.

Label correction note: doctors/admins can update a confirmed or corrected label and note. The current schema stores the latest `confirmed_labels`, `reviewed_by`, `reviewed_at`, and note; full historical audit versions for every label edit are a future enhancement.

Archive/deactivate behavior:

- Archived cases are hidden from the main case list, but their database rows, images, jobs, and analysis results remain stored.
- Inactive users cannot log in and existing tokens are rejected by authenticated endpoints.
- Active models cannot be archived. Activate another model first, then archive inactive metadata if needed.

## Testing Commands

```bash
python -m pytest backend/tests -v
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run typecheck
docker compose exec backend python scripts/celery_smoke_test.py
curl http://localhost:8000/metrics
```

Retraining confirmation and trigger checks:

```bash
# Replace TOKEN and CASE_ID with values from login/analyze or Swagger.
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/cases/CASE_ID/review-status
curl -X POST -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/cases/CASE_ID/confirm-result
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/admin/mlops/retraining/summary
curl -X POST -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/admin/mlops/retraining/start
```

Retraining threshold `N` is controlled by `RETRAIN_MIN_CONFIRMED_SAMPLES` in `.env`.
`N` counts only new DB cases whose labels were confirmed or corrected by a
doctor/admin. Local images under `artifacts/training_seed` help fine-tune the
model but never satisfy the threshold by themselves.
For pipeline testing you can set `N=1`, restart backend and Celery, confirm one case,
then start fine-tuning manually or let the system create a job automatically when
`RETRAIN_AUTO_START=true`:

```bash
docker compose up -d --build backend celery_worker
docker compose exec backend python scripts/retraining_smoke_test.py
docker compose exec backend python scripts/retraining_smoke_test.py --start
docker compose exec backend python scripts/inspect_training_data.py
```

Test `N=2` and `N=5` similarly by setting `RETRAIN_MIN_CONFIRMED_SAMPLES=2`
or `RETRAIN_MIN_CONFIRMED_SAMPLES=5`, restarting `backend` and `celery_worker`,
then confirming/correcting at least that many completed cases. Tiny sample counts
only test the pipeline and are not clinically meaningful.

Local training seed data should be placed locally under:

```text
artifacts/training_seed/Atelectasis/
artifacts/training_seed/Effusion/
artifacts/training_seed/Infiltration/
artifacts/training_seed/No_Finding/
```

Use the same class order as the MobileNetV3-Small model:
`Atelectasis`, `Effusion`, `Infiltration`, `No_Finding`.
`No Finding` is accepted as a folder alias, but `No_Finding` is canonical.
Suggested counts:

- Pipeline test: 5-10 images/class seed, 5 images/class eval.
- Demo: 50-100 images/class seed, 20-50 images/class eval.
- Stronger evaluation: 200+ images/class seed, 100+ images/class eval.

Fixed evaluation data should be placed locally under:

```text
artifacts/evaluation_set/Atelectasis/
artifacts/evaluation_set/Effusion/
artifacts/evaluation_set/Infiltration/
artifacts/evaluation_set/No_Finding/
```

`EVALUATION_SET_DIR` points to `/app/artifacts/evaluation_set` in Docker. These
images are ignored by Git. If the evaluation set is missing or empty, retraining
falls back to a validation split only for pipeline testing and stores a warning in
the retraining job. Fine-tuning logs params, metrics, manifest, checkpoint, class
metadata, and `evaluation_source` to MLflow at http://localhost:5000. The retrained
candidate is stored as inactive `ai_models` metadata; activate it only after Admin
review using `promote-if-better` or the Admin Models page.

Promotion uses `MODEL_PROMOTION_METRIC=f1_score` and
`MODEL_PROMOTION_MIN_DELTA=0.0` by default. `MODEL_AUTO_PROMOTE=false` keeps
retrained models as inactive candidates until Admin explicitly promotes them.
Evidently AI can be added later for data drift, prediction drift, and performance
monitoring when ground truth becomes available. MLflow remains responsible for
training runs and model registry, and Evidently does not replace fixed evaluation
metrics or the promotion gate.

Manual real-model local inference:

```bash
python backend/scripts/check_model_checkpoint.py --model-path artifacts/models/best_model.pth --architecture mobilenet_v3_small --task-type multi_class
python backend/scripts/run_local_inference.py --image artifacts/sample_images/your_image.png --model-path artifacts/models/best_model.pth --architecture mobilenet_v3_small --task-type multi_class
```

Register the local checkpoint to MLflow and create inactive `ai_models` metadata:

```bash
docker compose exec backend python scripts/register_best_model_to_mlflow.py
```

The script logs params, the four approved metrics, `best_model.pth`, a small metadata JSON, and creates a Model Registry version under `chest-xray-mobilenetv3-small`. Pass real evaluation metrics when available:

```bash
docker compose exec backend python scripts/register_best_model_to_mlflow.py --accuracy 0.90 --precision-score 0.88 --recall-score 0.87 --f1-score 0.875
```

Admin UI workflow:

1. Log in as Admin.
2. Open `Quản lý mô hình`.
3. Use `Đăng ký model lên MLflow` with `/app/artifacts/models/best_model.pth`.
4. Open MLflow UI at http://localhost:5000 to inspect the run and registered model version.
5. Promote or activate the resulting `ai_models` record only after reviewing metrics.

Windows PowerShell final check:

```powershell
.\scripts\final_check.ps1
```

## Troubleshooting

- If login fails, run `docker compose exec backend python scripts/seed_demo_users.py`.
- If analyze says no active model, run `docker compose exec backend python scripts/seed_demo_model.py`.
- If image upload or worker download fails, check MinIO is running and `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, and `MINIO_BUCKET` are configured.
- If real-model inference fails, confirm `artifacts/models/best_model.pth` exists locally and Docker Compose mounted `./artifacts/models:/app/artifacts/models`.
- If MLflow registration fails, confirm MLflow is running at http://localhost:5000 and Docker backend uses `MLFLOW_TRACKING_URI=http://mlflow:5000`.
- If MLflow shows `Invalid Host header - possible DNS rebinding attack detected`, update `MLFLOW_ALLOWED_HOSTS` in `.env` with the browser host, then run `docker compose up -d --build mlflow`.
- If jobs stay queued, open Flower at http://localhost:5555 and check `docker compose logs -f celery_worker`.
- If Redis queue state is unclear, open RedisInsight at http://localhost:5540.
- If Grafana is empty, log in with `admin` / `admin123`, open the `Medical Imaging Demo` folder, and confirm Prometheus can scrape `http://backend:8000/metrics` from Docker Compose.
- If logs are missing in Grafana, check Loki at http://localhost:3100/ready and Promtail logs with `docker compose logs -f promtail`.
- If Prometheus alerts or targets are missing, open http://localhost:9090/targets and confirm backend, cAdvisor, Redis exporter, PostgreSQL exporter, Loki, and Promtail are up.
- If an older Grafana volume still uses a previous password, reset it with `docker compose exec grafana grafana cli admin reset-admin-password admin123`.
- If the backend cannot connect to the database, run `docker compose ps` and verify PostgreSQL is healthy.
- If frontend API calls fail, check `VITE_API_BASE_URL` and CORS origins.
- If Docker ML dependency installation is slow, confirm the backend image uses CPU torch requirements.

## Security And Limitations

- Demo JWT auth is intentionally simple and not production-grade.
- Demo credentials are for local development only.
- Do not commit `.env`, real credentials, model weights, datasets, real patient data, MinIO/PostgreSQL/Redis volumes, or MLflow artifacts.
- Do not commit `AGENTS.md`, `.agents/`, `.codex_tasks/`, or local Codex context files.

## Known Limitations

- The HTML report is browser-printable; PDF generation is not server-side yet.
- DICOM is not supported yet.
- The local MobileNetV3-Small checkpoint is a project model for demo/development and is not clinically certified.
- Retraining only uses cases with stored confirmation evidence in `confirmed_labels`; raw AI predictions are excluded even when high-confidence.
- Grafana includes demo dashboards and Loki log views; this is still a local development observability stack, not a production SRE setup.
