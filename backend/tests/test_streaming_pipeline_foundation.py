from pathlib import Path
import sys

from PIL import Image
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.storage import MinIOImageStorage, get_image_storage  # noqa: E402
from app.tasks.celery_app import celery_app  # noqa: E402
import app.tasks.health  # noqa: E402,F401
import app.tasks.inference  # noqa: E402,F401


def test_celery_tasks_are_registered() -> None:
    assert "app.tasks.health.worker_health" in celery_app.tasks
    assert "app.tasks.inference.perform_inference" in celery_app.tasks


def test_image_storage_resolves_local_file(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (16, 16), (64, 96, 128)).save(image_path)

    assert get_image_storage().get_image_input(str(image_path)) == image_path


class FakeObjectResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class FakeMinIOClient:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put_object(
        self,
        bucket: str,
        object_key: str,
        data,
        *,
        length: int,
        content_type: str,
    ) -> None:
        self.objects[(bucket, object_key)] = data.read(length)

    def get_object(self, bucket: str, object_key: str) -> FakeObjectResponse:
        return FakeObjectResponse(self.objects[(bucket, object_key)])


def test_minio_storage_uploads_and_downloads_object_bytes() -> None:
    fake_client = FakeMinIOClient()
    storage = MinIOImageStorage(bucket="xray-images", client=fake_client)

    image_uri = storage.save_image_bytes(
        b"demo-image",
        image_hash="abcdef123456",
        file_format="png",
    )

    assert image_uri == "minio://xray-images/xray/ab/abcdef123456.png"
    assert fake_client.buckets == {"xray-images"}
    assert storage.get_image_input(image_uri) == b"demo-image"
