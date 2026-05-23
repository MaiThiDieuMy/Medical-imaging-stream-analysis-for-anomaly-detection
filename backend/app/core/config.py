from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Medical Imaging Stream Analysis API"
    app_version: str = "0.1.0"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"
    backend_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auth_secret_key: str = "demo-development-secret-change-me"
    access_token_expire_minutes: int = 720

    database_url: str = (
        "postgresql+psycopg://xray_demo:xray_demo_password"
        "@localhost:5432/xray_streaming"
    )
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    model_source: str = "demo"
    model_architecture: str = "mobilenet_v3_small"
    model_weights_path: str = ""
    model_device: str = "cpu"
    model_threshold: float = 0.5
    allow_demo_model: bool = True

    local_image_storage_dir: str = "artifacts/uploads"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio_demo_user"
    minio_secret_key: str = "minio_demo_password"
    minio_bucket: str = "xray-images"
    minio_secure: bool = False
    max_upload_size_bytes: int = 10 * 1024 * 1024
    allowed_image_extensions: str = ".png,.jpg,.jpeg"
    allowed_image_content_types: str = "image/png,image/jpeg,image/jpg"

    low_confidence_threshold: float = 0.7
    review_near_threshold_margin: float = 0.1
    retrain_min_confirmed_samples: int = 15
    auto_start_retraining_job: bool = False
    retrain_epochs: int = 3
    retrain_batch_size: int = 8
    retrain_learning_rate: float = 0.0001
    retrain_validation_split: float = 0.2
    retrain_replay_metadata_path: str = ""
    retrain_replay_samples_per_class: int = 30
    retrain_eval_manifest_path: str = ""
    retrain_unfreeze_last_blocks: int = 0
    auto_promote_retrained_model: bool = False
    promotion_max_recall_drop: float = 0.02
    retrain_output_dir: str = "artifacts/models/retrained"
    retrain_manifest_dir: str = "artifacts/retraining_manifests"
    retraining_manifest_dir: str = "artifacts/retraining_manifests"
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_ui_url: str = "http://localhost:5000"
    mlflow_experiment_name: str = "chest-xray-stream-analysis"
    mlflow_registered_model_name: str = "chest-xray-mobilenetv3-small"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
