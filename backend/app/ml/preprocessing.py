from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from PIL import Image
import torch
from torchvision import transforms

from app.ml.types import ImageInput

DEFAULT_IMAGE_SIZE = 224
IMAGENET_MEAN: tuple[float, float, float] = (0.485, 0.456, 0.406)
IMAGENET_STD: tuple[float, float, float] = (0.229, 0.224, 0.225)


def load_image(image_input: ImageInput) -> Image.Image:
    if isinstance(image_input, Image.Image):
        image = image_input
    elif isinstance(image_input, bytes):
        image = Image.open(BytesIO(image_input))
    elif isinstance(image_input, (str, Path)):
        image = Image.open(image_input)
    else:
        image = Image.open(image_input)

    return image.convert("RGB")


def build_preprocessing_transform(
    image_size: int = DEFAULT_IMAGE_SIZE,
) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize(image_size),
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )


def preprocess_image(
    image_input: ImageInput,
    image_size: int = DEFAULT_IMAGE_SIZE,
    device: torch.device | str | None = None,
) -> torch.Tensor:
    image = load_image(image_input)
    transform = build_preprocessing_transform(image_size=image_size)
    tensor = transform(image).unsqueeze(0)

    target_device = torch.device(device or "cpu")
    tensor = tensor.to(target_device)

    if tensor.shape != (1, 3, image_size, image_size):
        raise ValueError(f"Unexpected preprocessed tensor shape: {tuple(tensor.shape)}")
    if not torch.isfinite(tensor).all():
        raise ValueError("Preprocessed image tensor contains non-finite values")

    return tensor
