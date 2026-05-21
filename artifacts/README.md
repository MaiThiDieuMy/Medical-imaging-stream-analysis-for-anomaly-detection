# Local ML Artifacts

This directory is reserved for local development artifacts that must not be
committed to Git.

- Put local model checkpoints under `artifacts/models/`.
- Put local sample images under `artifacts/sample_images/`.
- Generated retraining manifests are written under `artifacts/retraining_manifests/`.
- Keep only the README files tracked.

Do not commit real patient data, datasets, model weights, generated manifests,
or generated MLflow artifacts.
