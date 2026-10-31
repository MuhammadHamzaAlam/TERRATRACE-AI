"""Model registry: reconciles checkpoints on disk with ModelVersion rows and reports an honest status."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import models as m

_cache: dict[str, object] = {}
_lock = threading.Lock()
STATUSES = ["not_initialized", "training", "trained", "evaluated", "available", "failed"]


def _paths():
    s = get_settings()
    d = s.models_dir / "siamese_unet"
    return d, d / "best.pt", d / "eval" / "eval_test.json"


def sync_registry(db: Session) -> m.ModelVersion | None:
    """Create/update the ModelVersion for models/siamese_unet/best.pt. `validated` = test-set evaluation exists."""
    d, ckpt, evalp = _paths()
    if not ckpt.exists():
        return None
    mv = db.query(m.ModelVersion).filter(m.ModelVersion.checkpoint_path == str(ckpt)).first()
    mtime = int(ckpt.stat().st_mtime)
    if mv is None:
        mv = m.ModelVersion(name=f"siamese-unet-resnet18-{mtime}", checkpoint_path=str(ckpt))
        db.add(mv)
    metrics = {}
    if evalp.exists():
        metrics = json.loads(evalp.read_text())
    hist = d / "history.json"
    mv.metrics = {"test": metrics or None, "epochs_trained": len(json.loads(hist.read_text())) if hist.exists() else None}
    mv.validated = bool(metrics)
    mv.status = "available" if metrics else "trained"
    try:
        import torch
        ck = torch.load(ckpt, map_location="cpu", weights_only=False)
        mv.config = ck.get("config", {})
    except Exception:
        pass
    db.commit()
    return mv


def model_status(db: Session) -> dict:
    d, ckpt, evalp = _paths()
    active = db.query(m.TrainingRun).filter(m.TrainingRun.status.in_(["pending", "running"])).first()
    last_failed = db.query(m.TrainingRun).order_by(m.TrainingRun.created_at.desc()).first()
    mv = sync_registry(db)
    if active:
        status = "training"
    elif mv is None:
        status = "failed" if (last_failed and last_failed.status == "failed") else "not_initialized"
    else:
        status = "available" if mv.validated else "trained"
    out = {
        "status": status, "architecture": "Siamese U-Net, shared ResNet18 encoder (ImageNet init)",
        "checkpoint_present": ckpt.exists(), "validated": bool(mv and mv.validated),
        "model_version_id": mv.id if mv else None,
        "inference_available": mv is not None,
        "message": None,
    }
    if mv is None:
        out["message"] = "Model evaluation pending — no validated checkpoint available."
    elif not mv.validated:
        out["message"] = "Checkpoint present but not evaluated on the LEVIR-CD test split; metrics pending."
    out["metrics"] = (mv.metrics or {}).get("test") if mv else None
    return out


def get_predictor():
    from ml.inference.predictor import ChangePredictor, ModelUnavailable
    _, ckpt, _ = _paths()
    if not ckpt.exists():
        raise ModelUnavailable("No model checkpoint available. Train one (see docs/ml-pipeline.md).")
    key = f"{ckpt}:{ckpt.stat().st_mtime_ns}"
    with _lock:
        if _cache.get("key") != key:
            _cache["key"], _cache["pred"] = key, ChangePredictor(ckpt)
        return _cache["pred"]
