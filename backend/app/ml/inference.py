import torch

from app.core.config import settings
from app.ml.labels import NUM_DEMO_LABELS
from app.ml.model_loader import load_model
from app.ml.preprocessing import preprocess_image
from app.ml.types import (
    PREDICTION_MODE_MULTICLASS,
    PREDICTION_MODE_MULTILABEL,
    ImageInput,
    InferenceOutput,
    LoadedModel,
)

DEFAULT_POSITIVE_THRESHOLD = 0.5


def run_inference(
    image_input: ImageInput,
    loaded_model: LoadedModel | None = None,
    threshold: float | None = None,
) -> list[InferenceOutput]:
    positive_threshold = settings.model_threshold if threshold is None else threshold
    if not 0.0 <= positive_threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")

    model_bundle = loaded_model or load_model(device="cpu")
    image_tensor = preprocess_image(image_input, device=model_bundle.device)

    with torch.inference_mode():
        logits = model_bundle.model(image_tensor)
        logits = logits.squeeze(0)
        if model_bundle.prediction_mode == PREDICTION_MODE_MULTICLASS:
            probabilities_tensor = torch.softmax(logits, dim=0)
        elif model_bundle.prediction_mode == PREDICTION_MODE_MULTILABEL:
            probabilities_tensor = torch.sigmoid(logits)
        else:
            raise ValueError(
                f"Unsupported prediction mode: {model_bundle.prediction_mode}"
            )
        probabilities = probabilities_tensor.detach().cpu().tolist()

    if len(probabilities) != NUM_DEMO_LABELS:
        raise ValueError(
            f"Expected {NUM_DEMO_LABELS} probabilities, got {len(probabilities)}"
        )

    predicted_index = (
        int(torch.tensor(probabilities).argmax().item())
        if model_bundle.prediction_mode == PREDICTION_MODE_MULTICLASS
        else None
    )
    outputs: list[InferenceOutput] = []
    for index, (label_name, probability) in enumerate(
        zip(
            model_bundle.label_names,
            probabilities,
            strict=True,
        )
    ):
        probability_float = float(probability)
        if not 0.0 <= probability_float <= 1.0:
            raise ValueError(f"Invalid probability for {label_name}: {probability_float}")
        if model_bundle.prediction_mode == PREDICTION_MODE_MULTICLASS:
            predicted_positive = index == predicted_index
        else:
            predicted_positive = probability_float >= positive_threshold
        outputs.append(
            InferenceOutput(
                label_name=label_name,
                probability=probability_float,
                predicted_positive=predicted_positive,
            )
        )

    return outputs
