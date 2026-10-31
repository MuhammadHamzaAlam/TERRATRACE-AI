# ML pipeline

## Model

`backend/ml/architecture/siamese_unet.py`

* **Encoder**: one torchvision ResNet18 instance applied to *both* images (shared weights, ImageNet initialisation).
  Five scales (strides 2, 4, 8, 16, 32; 64/64/128/256/512 channels).
* **Temporal comparison** at every scale: `concat[f_t1, f_t2, |f_t1 − f_t2|] → 1×1 conv → BN → ReLU`.
* **Decoder**: U-Net with skip connections from the fused features, 4 up-blocks (256/128/64/32 ch), bilinear upsampling,
  1-channel logit head → sigmoid probability → thresholded mask.
* 15.39 M trainable parameters.

## Data pipeline

* `ml/datasets/levir.py` — pair/mask validation, reproducible per-sample RNG (`seed, epoch, index`), random 256 px crops.
* `ml/preprocessing/transforms.py` — ImageNet normalisation; **paired** augmentation (flips, 90° rotations applied identically
  to both images and the mask, temporal swap with p=0.5, independent photometric jitter per date).
* Train / val / test come from the official LEVIR-CD split directories and are never mixed.

## Training

```bash
cd backend
python -m ml.training.train --data-root ../data/raw/LEVIR-CD --out-dir ../models/siamese_unet \
  --epochs 30 --batch-size 8 --crops-per-image 4 --lr 5e-4 --patience 8 [--cpu] [--resume]
```

AdamW (wd 1e-4) · BCE + Dice loss · cosine LR schedule · gradient clipping · early stopping on validation F1 ·
`best.pt` (best val F1) and `last.pt` (resumable) · `history.json`. Seeds are fixed (`--seed`). CPU and CUDA are supported
automatically. Per-epoch validation uses the top-left 256×256 crop of each validation image (fast proxy); the final
number is the full-image test evaluation below.

## Evaluation

```bash
python -m ml.evaluation.evaluate --checkpoint ../models/siamese_unet/best.pt --data-root ../data/raw/LEVIR-CD --split test
```

Runs tiled inference on the **full 1024×1024 test images**, accumulates TP/FP/FN/TN over all pixels (micro-averaged), and
writes `models/siamese_unet/eval/eval_test.json` plus before | after | ground-truth | prediction visualisations. The
backend marks a checkpoint `validated` only when this file exists. Until then every UI surface shows
*"Model evaluation pending — no validated checkpoint available."*

## Inference

`ml/inference/predictor.py` — `ChangePredictor(checkpoint).predict_proba(before, after)`; raises `ModelUnavailable`
if there is no checkpoint (analyses become `blocked`, nothing is fabricated).

## Limitations

* Trained on 0.5 m RGB imagery of US cities (LEVIR-CD, building changes only). Not validated on other sensors/resolutions.
* The checkpoint trained in this repository is a short CPU run (see README for exact epochs/results) — it is a working
  baseline, not a state-of-the-art model. Published LEVIR-CD F1 for stronger architectures trained for 100+ epochs on GPU
  is ≈ 0.90.
* ONNX export and multi-checkpoint comparison are not implemented.
