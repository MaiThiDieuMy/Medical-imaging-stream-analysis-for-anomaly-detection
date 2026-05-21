from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.ml.types import ImageInput


class ImageStorage:
    """Local filesystem storage used by unit tests and as a dev fallback."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or settings.local_image_storage_dir)

    def get_image_input(self, image_path: str) -> ImageInput:
        return self.get_image_bytes(image_path) if _is_object_uri(image_path) else self._local_path(image_path)

    def get_image_bytes(self, image_path: str) -> bytes:
        path = self._local_path(image_path)
        return path.read_bytes()

    def save_image_bytes(
        self,
        content: bytes,
        *,
        image_hash: str,
        file_format: str,
    ) -> str:
        normalized_format = _normalize_file_format(file_format)
        if not image_hash:
            raise ValueError("image_hash is required")

        partition = image_hash[:2]
        target_dir = self.base_dir / partition
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / f"{image_hash}.{normalized_format}"
        if not target_path.exists():
            target_path.write_bytes(content)

        return str(target_path)

    @staticmethod
    def _local_path(image_path: str) -> Path:
        if not image_path:
            raise ValueError("image_path is required")

        parsed = urlparse(image_path)
        if parsed.scheme in ("s3", "minio"):
            raise ValueError("Object storage URI requires MinIOImageStorage")
        if parsed.scheme == "file":
            candidate = Path(parsed.path)
        else:
            candidate = Path(image_path)

        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if not candidate.exists():
            raise FileNotFoundError(f"Image file not found: {candidate}")
        if not candidate.is_file():
            raise ValueError(f"Image path is not a file: {candidate}")
        return candidate


class MinIOImageStorage(ImageStorage):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
        client: Any | None = None,
    ) -> None:
        super().__init__()
        self.bucket = bucket or settings.minio_bucket
        self._client = client
        self._client_config = {
            "endpoint": endpoint or settings.minio_endpoint,
            "access_key": access_key or settings.minio_access_key,
            "secret_key": secret_key or settings.minio_secret_key,
            "secure": settings.minio_secure if secure is None else secure,
        }

    @property
    def client(self) -> Any:
        if self._client is None:
            from minio import Minio

            self._client = Minio(**self._client_config)
        return self._client

    def get_image_input(self, image_path: str) -> ImageInput:
        if _is_object_uri(image_path):
            return self.get_image_bytes(image_path)
        return super().get_image_input(image_path)

    def get_image_bytes(self, image_path: str) -> bytes:
        if not _is_object_uri(image_path):
            return super().get_image_bytes(image_path)

        bucket, object_key = self._parse_object_uri(image_path)
        response = self.client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            release_conn = getattr(response, "release_conn", None)
            if callable(release_conn):
                release_conn()

    def save_image_bytes(
        self,
        content: bytes,
        *,
        image_hash: str,
        file_format: str,
    ) -> str:
        normalized_format = _normalize_file_format(file_format)
        if not image_hash:
            raise ValueError("image_hash is required")

        self.ensure_bucket()
        object_key = f"xray/{image_hash[:2]}/{image_hash}.{normalized_format}"
        self.client.put_object(
            self.bucket,
            object_key,
            BytesIO(content),
            length=len(content),
            content_type=_content_type_for_format(normalized_format),
        )
        return f"minio://{self.bucket}/{object_key}"

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    @staticmethod
    def _parse_object_uri(image_path: str) -> tuple[str, str]:
        parsed = urlparse(image_path)
        if parsed.scheme not in ("s3", "minio"):
            raise ValueError(f"Unsupported object storage URI: {image_path}")
        bucket = parsed.netloc
        object_key = parsed.path.lstrip("/")
        if not bucket or not object_key:
            raise ValueError(f"Invalid object storage URI: {image_path}")
        return bucket, object_key


def get_image_storage() -> ImageStorage:
    return MinIOImageStorage()


def _normalize_file_format(file_format: str) -> str:
    normalized_format = file_format.strip().lower().lstrip(".")
    if not normalized_format:
        raise ValueError("file_format is required")
    return "jpg" if normalized_format == "jpeg" else normalized_format


def _content_type_for_format(file_format: str) -> str:
    return "image/png" if file_format == "png" else "image/jpeg"


def _is_object_uri(image_path: str) -> bool:
    return urlparse(image_path).scheme in ("s3", "minio")
