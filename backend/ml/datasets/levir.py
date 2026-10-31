"""LEVIR-CD dataset loader.

Expected layout (the layout of the official release, after unzipping the train/val/test archives):
    <root>/{train,val,test}/{A,B,label}/*.png      (1024x1024, A=earlier, B=later, label in {0,255})
Alternatively the pre-cropped 256x256 layout from common mirrors (same folder names) is supported.
Official source: https://levir.buaa.edu.cn/datasets/ (paper: Chen & Shi, Remote Sensing 2020, 12(10):1662).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from ml.preprocessing.transforms import normalize, paired_augment

SPLITS = ("train", "val", "test")


def validate_split(root: Path, split: str) -> dict:
    """Validate pairing and masks for a split. Returns a report; raises nothing."""
    d = Path(root) / split
    report = {"split": split, "exists": d.exists(), "n_pairs": 0, "problems": []}
    if not d.exists():
        return report
    names = sorted(p.name for p in (d / "A").glob("*.png")) if (d / "A").exists() else []
    for n in names:
        if not (d / "B" / n).exists():
            report["problems"].append(f"{n}: missing B image")
        elif not (d / "label" / n).exists():
            report["problems"].append(f"{n}: missing label")
        else:
            report["n_pairs"] += 1
    return report


def dataset_statistics(root: Path) -> dict:
    stats = {"root": str(root), "available": Path(root).exists(), "splits": {}}
    for s in SPLITS:
        rep = validate_split(root, s)
        entry = {"n_pairs": rep["n_pairs"], "problems": rep["problems"][:10]}
        if rep["n_pairs"]:
            d = Path(root) / s / "label"
            pos = tot = 0
            for p in sorted(d.glob("*.png"))[:200]:
                m = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
                if m is None:
                    continue
                pos += int((m > 127).sum()); tot += m.size
            entry["changed_pixel_fraction_sampled"] = pos / max(tot, 1)
        stats["splits"][s] = entry
    return stats


class LevirCDDataset(Dataset):
    def __init__(self, root: str | Path, split: str, crop_size: int = 256, augment: bool = False,
                 seed: int = 42, crops_per_image: int = 1, max_samples: int | None = None):
        assert split in SPLITS
        self.dir = Path(root) / split
        self.names = sorted(p.name for p in (self.dir / "A").glob("*.png"))
        if max_samples:
            self.names = self.names[:max_samples]
        if not self.names:
            raise FileNotFoundError(f"No LEVIR-CD image pairs found in {self.dir}")
        self.crop = crop_size
        self.augment = augment
        self.seed = seed
        self.crops_per_image = crops_per_image if augment else 1
        self._epoch = 0

    def set_epoch(self, e: int):
        self._epoch = e

    def __len__(self):
        return len(self.names) * self.crops_per_image

    def _read(self, sub: str, name: str, gray=False):
        p = str(self.dir / sub / name)
        img = cv2.imread(p, cv2.IMREAD_GRAYSCALE if gray else cv2.IMREAD_COLOR)
        if img is None:
            raise IOError(f"Unreadable image: {p}")
        return img if gray else cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def __getitem__(self, i):
        name = self.names[i % len(self.names)]
        a, b, m = self._read("A", name), self._read("B", name), self._read("label", name, gray=True)
        if not (a.shape[:2] == b.shape[:2] == m.shape[:2]):
            raise ValueError(f"Shape mismatch for {name}: {a.shape} {b.shape} {m.shape}")
        rng = np.random.default_rng((self.seed, self._epoch if self.augment else 0, i))
        h, w = m.shape
        if self.augment and (h > self.crop and w > self.crop):
            y, x = int(rng.integers(0, h - self.crop + 1)), int(rng.integers(0, w - self.crop + 1))
            a, b, m = a[y:y + self.crop, x:x + self.crop], b[y:y + self.crop, x:x + self.crop], m[y:y + self.crop, x:x + self.crop]
        elif not self.augment and (h != self.crop or w != self.crop) and h >= self.crop and w >= self.crop:
            # deterministic centre-free evaluation: top-left crop keeps evaluation reproducible & cheap
            a, b, m = a[:self.crop, :self.crop], b[:self.crop, :self.crop], m[:self.crop, :self.crop]
        if self.augment:
            a, b, m = paired_augment(a, b, m, rng)
        target = (np.ascontiguousarray(m) > 127).astype(np.float32)[None]
        return torch.from_numpy(normalize(np.ascontiguousarray(a))), torch.from_numpy(normalize(np.ascontiguousarray(b))), torch.from_numpy(target)
