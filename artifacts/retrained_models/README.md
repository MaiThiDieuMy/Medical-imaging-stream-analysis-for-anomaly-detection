# Retrained model checkpoints

Retraining jobs write generated candidate checkpoints here during local or Docker demos.

Do not commit generated `.pth`, `.pt`, `.ckpt`, `.onnx`, or `.safetensors` files. The
directory is mounted into backend and Celery containers at `/app/artifacts/retrained_models`.
