"""Reproducible, *paired* preprocessing: identical spatial transforms are applied to both images and the mask."""
from __future__ import annotations

import numpy as np

# ImageNet statistics (the encoder is a torchvision ResNet18)
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def normalize(img_u8: np.ndarray) -> np.ndarray:
    """HxWx3 uint8 -> 3xHxW float32 normalized."""
    x = img_u8.astype(np.float32) / 255.0
    x = (x - MEAN) / STD
    return np.ascontiguousarray(x.transpose(2, 0, 1))


def paired_augment(a: np.ndarray, b: np.ndarray, m: np.ndarray, rng: np.random.Generator):
    """Random flips / 90-degree rotations, applied identically to (before, after, mask).
    Also swaps temporal order with p=0.5: building change (any direction) is labelled as change in LEVIR-CD."""
    if rng.random() < 0.5:
        a, b, m = a[:, ::-1], b[:, ::-1], m[:, ::-1]
    if rng.random() < 0.5:
        a, b, m = a[::-1], b[::-1], m[::-1]
    k = int(rng.integers(0, 4))
    if k:
        a, b, m = np.rot90(a, k), np.rot90(b, k), np.rot90(m, k)
    if rng.random() < 0.5:
        a, b = b, a
    # mild photometric jitter, applied independently per date (different dates differ radiometrically)
    def jitter(x):
        gain = 1.0 + rng.uniform(-0.15, 0.15)
        bias = rng.uniform(-12, 12)
        return np.clip(x.astype(np.float32) * gain + bias, 0, 255).astype(np.uint8)
    return jitter(a), jitter(b), m
