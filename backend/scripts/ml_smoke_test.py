from pathlib import Path
import sys

from PIL import Image
import torch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ml.labels import DEMO_LABELS
from app.ml.inference import run_inference
from app.ml.preprocessing import DEFAULT_IMAGE_SIZE, preprocess_image


def build_demo_image() -> Image.Image:
    image = Image.new("RGB", (256, 256))
    pixels: list[tuple[int, int, int]] = []
    for y in range(256):
        for x in range(256):
            pixels.append((x, y, (x + y) // 2))
    image.putdata(pixels)
    return image


def main() -> None:
    image = build_demo_image()
    tensor = preprocess_image(image)
    assert tensor.shape == (1, 3, DEFAULT_IMAGE_SIZE, DEFAULT_IMAGE_SIZE)
    assert torch.isfinite(tensor).all()

    outputs = run_inference(image)
    assert len(outputs) == len(DEMO_LABELS)

    for output in outputs:
        assert output.label_name in DEMO_LABELS
        assert isinstance(output.probability, float)
        assert 0.0 <= output.probability <= 1.0
        assert isinstance(output.predicted_positive, bool)

    print("ML smoke test passed")
    for output in outputs:
        print(output.to_dict())


if __name__ == "__main__":
    main()
