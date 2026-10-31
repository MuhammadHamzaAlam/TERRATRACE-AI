"""Full-image test-set evaluation with tiled inference.  python -m ml.evaluation.evaluate --checkpoint models/siamese_unet/best.pt"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from ml.evaluation.metrics import ConfusionAccumulator
from ml.inference.predictor import ChangePredictor


def evaluate(checkpoint: str, data_root: str, split: str = "test", threshold: float = 0.5, out_dir: str | None = None,
             n_visuals: int = 6, max_images: int | None = None) -> dict:
    pred = ChangePredictor(checkpoint)
    d = Path(data_root) / split
    names = sorted(p.name for p in (d / "A").glob("*.png"))[:max_images]
    if not names:
        raise FileNotFoundError(f"no image pairs in {d}")
    acc = ConfusionAccumulator()
    out = Path(out_dir) if out_dir else None
    if out: (out / "predictions").mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(names):
        a = cv2.cvtColor(cv2.imread(str(d / "A" / n)), cv2.COLOR_BGR2RGB)
        b = cv2.cvtColor(cv2.imread(str(d / "B" / n)), cv2.COLOR_BGR2RGB)
        m = cv2.imread(str(d / "label" / n), cv2.IMREAD_GRAYSCALE) > 127
        p = pred.predict_proba(a, b)
        acc.update(torch.from_numpy(p), torch.from_numpy(m.astype(np.float32)), threshold)
        if out and i < n_visuals:
            pm = (p >= threshold)
            vis = np.concatenate([a, b, np.repeat((m * 255).astype(np.uint8)[..., None], 3, 2),
                                  np.repeat((pm * 255).astype(np.uint8)[..., None], 3, 2)], axis=1)
            cv2.imwrite(str(out / "predictions" / f"{Path(n).stem}_before_after_gt_pred.jpg"), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
    res = {"split": split, "n_images": len(names), "threshold": threshold, **acc.compute(), "checkpoint": checkpoint,
           "note": "Pixel-level micro-averaged metrics over full tiled images; LEVIR-CD domain only."}
    if out: (out / f"eval_{split}.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True); ap.add_argument("--data-root", default="data/raw/LEVIR-CD")
    ap.add_argument("--split", default="test"); ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--out-dir", default="models/siamese_unet/eval"); ap.add_argument("--max-images", type=int)
    a = ap.parse_args()
    print(json.dumps(evaluate(a.checkpoint, a.data_root, a.split, a.threshold, a.out_dir, max_images=a.max_images), indent=2))
