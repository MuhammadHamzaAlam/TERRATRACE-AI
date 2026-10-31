"""Tiled inference with overlap blending. Never fabricates output: raises if no checkpoint is loaded."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import torch

from ml.architecture.siamese_unet import SiameseUNet
from ml.preprocessing.transforms import normalize


class ModelUnavailable(RuntimeError):
    pass


class ChangePredictor:
    def __init__(self, checkpoint_path: str | Path, device: str | None = None):
        p = Path(checkpoint_path)
        if not p.exists():
            raise ModelUnavailable(f"Checkpoint not found: {p}")
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        ckpt = torch.load(p, map_location="cpu", weights_only=False)
        self.model = SiameseUNet(pretrained=False)
        self.model.load_state_dict(ckpt["model_state"])
        self.model.to(self.device).eval()
        self.meta = {k: v for k, v in ckpt.items() if k != "model_state"}

    @torch.no_grad()
    def predict_proba(self, before: np.ndarray, after: np.ndarray, tile: int = 256, overlap: int = 32,
                      batch_size: int = 4, progress: Callable[[float], None] | None = None) -> np.ndarray:
        """before/after: HxWx3 uint8 RGB of identical shape. Returns HxW float32 change probability."""
        if before.shape != after.shape:
            raise ValueError("before/after must have identical shape")
        h, w = before.shape[:2]
        step = tile - overlap
        ys = list(range(0, max(h - tile, 0) + 1, step)) or [0]
        xs = list(range(0, max(w - tile, 0) + 1, step)) or [0]
        if ys[-1] + tile < h: ys.append(h - tile)
        if xs[-1] + tile < w: xs.append(w - tile)
        pad_h, pad_w = max(tile - h, 0), max(tile - w, 0)
        if pad_h or pad_w:
            before = np.pad(before, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
            after = np.pad(after, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
        H, W = before.shape[:2]
        acc = np.zeros((H, W), np.float32); wsum = np.zeros((H, W), np.float32)
        win1 = np.hanning(tile).astype(np.float32).clip(1e-3)
        win = np.outer(win1, win1)
        coords = [(y, x) for y in ys for x in xs]
        for bi in range(0, len(coords), batch_size):
            chunk = coords[bi:bi + batch_size]
            a = torch.from_numpy(np.stack([normalize(before[y:y + tile, x:x + tile]) for y, x in chunk])).to(self.device)
            b = torch.from_numpy(np.stack([normalize(after[y:y + tile, x:x + tile]) for y, x in chunk])).to(self.device)
            p = torch.sigmoid(self.model(a, b))[:, 0].cpu().numpy()
            for (y, x), pi in zip(chunk, p):
                acc[y:y + tile, x:x + tile] += pi * win; wsum[y:y + tile, x:x + tile] += win
            if progress:
                progress(min(1.0, (bi + len(chunk)) / len(coords)))
        return (acc / np.maximum(wsum, 1e-6))[:h, :w]
