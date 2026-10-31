"""Explainable analytical priority score (0-100). NOT a threat score: it ranks candidate events for analyst review order."""
from __future__ import annotations

import math

DEFAULT_WEIGHTS = {"area": 0.30, "confidence": 0.30, "concentration": 0.20, "relative_change": 0.10, "recurrence": 0.10}

EXPLANATION = (
    "Analytical priority = 100 x sum(weight_i x factor_i), each factor scaled to [0,1]. "
    "area: log-scaled event area relative to the largest event in the analysis. "
    "confidence: mean model probability inside the event (model confidence, not factual certainty). "
    "concentration: size of the spatial cluster the event belongs to relative to the largest cluster (0 if unclustered). "
    "relative_change: event share of the image, saturating at 2%. "
    "recurrence: 0 for first detection; rises to 1 as the same location is detected in more analyses (saturates at 4). "
    "The score orders events for human review; it makes no claim about intent or significance."
)


def score_event(ev: dict, max_area: float, cluster_size: int, max_cluster: int, n_observations: int, weights: dict | None = None) -> dict:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    tot = sum(w.values()) or 1.0
    w = {k: v / tot for k, v in w.items()}
    f = {
        "area": math.log1p(ev["area_px"]) / math.log1p(max(max_area, 1.0)),
        "confidence": float(ev["conf_mean"]),
        "concentration": (cluster_size / max_cluster) if (cluster_size and max_cluster) else 0.0,
        "relative_change": min(1.0, ev["area_pct"] / 2.0),
        "recurrence": min(1.0, max(0, n_observations - 1) / 3.0),
    }
    contrib = {k: round(100 * w[k] * f[k], 3) for k in f}
    return {"score": round(sum(contrib.values()), 2), "factors": {k: round(v, 4) for k, v in f.items()},
            "contributions": contrib, "weights": w}
