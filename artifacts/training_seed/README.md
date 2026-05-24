# Local Training Seed

Put local, doctor-labeled seed images here when you want fine-tuning to start
from a small labeled baseline dataset plus newly confirmed/corrected DB cases.

Expected folders:

```text
artifacts/training_seed/
  Atelectasis/
  Effusion/
  Infiltration/
  No_Finding/
```

`No Finding` is also accepted as a local folder alias, but `No_Finding` is the
canonical class name used by the MobileNetV3-Small retraining pipeline.

Training seed images help fine-tune the model, but they do not count toward
`RETRAIN_MIN_CONFIRMED_SAMPLES`. That threshold counts only new DB cases that a
doctor/admin has confirmed or corrected.

Do not commit real images or patient data. The image files in these folders are
ignored by Git.
