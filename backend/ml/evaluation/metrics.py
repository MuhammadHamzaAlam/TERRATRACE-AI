from __future__ import annotations

import numpy as np
import torch


class ConfusionAccumulator:
    """Accumulates pixel-level confusion counts over a dataset (micro-averaged metrics)."""

    def __init__(self):
        self.tp = self.fp = self.fn = self.tn = 0

    def update(self, prob: torch.Tensor, target: torch.Tensor, threshold: float = 0.5):
        pred = (prob >= threshold).bool()
        t = target.bool()
        self.tp += int((pred & t).sum())
        self.fp += int((pred & ~t).sum())
        self.fn += int((~pred & t).sum())
        self.tn += int((~pred & ~t).sum())

    def compute(self) -> dict:
        tp, fp, fn, tn = self.tp, self.fp, self.fn, self.tn
        eps = 1e-9
        precision = tp / (tp + fp + eps)
        recall = tp / (tp + fn + eps)
        return {
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall + eps),
            "iou": tp / (tp + fp + fn + eps),
            "accuracy": (tp + tn) / (tp + tn + fp + fn + eps),
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        }


def dice_loss(logits: torch.Tensor, target: torch.Tensor, eps: float = 1.0) -> torch.Tensor:
    p = torch.sigmoid(logits).flatten(1)
    t = target.flatten(1)
    inter = (p * t).sum(1)
    return (1 - (2 * inter + eps) / (p.sum(1) + t.sum(1) + eps)).mean()


class BCEDiceLoss(torch.nn.Module):
    def __init__(self, pos_weight: float | None = None):
        super().__init__()
        self.pos_weight = None if pos_weight is None else torch.tensor([pos_weight])

    def forward(self, logits, target):
        pw = self.pos_weight.to(logits.device) if self.pos_weight is not None else None
        bce = torch.nn.functional.binary_cross_entropy_with_logits(logits, target, pos_weight=pw)
        return bce + dice_loss(logits, target)
