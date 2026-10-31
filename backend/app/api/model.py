from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import models as m
from app.database.session import SessionLocal, get_db
from app.jobs import runner
from app.schemas.api import TrainIn
from app.services import model_service

router = APIRouter(prefix="/model", tags=["model"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return model_service.model_status(db)


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    s = get_settings(); d = s.models_dir / "siamese_unet"
    ev = d / "eval" / "eval_test.json"
    hist = d / "history.json"
    vis = sorted(p.name for p in (d / "eval" / "predictions").glob("*.jpg")) if (d / "eval" / "predictions").exists() else []
    return {"test_metrics": json.loads(ev.read_text()) if ev.exists() else None,
            "training_history": json.loads(hist.read_text()) if hist.exists() else [],
            "prediction_visualizations": vis,
            "message": None if ev.exists() else "Model evaluation pending — no validated checkpoint available."}


@router.get("/visualization/{name}")
def visualization(name: str):
    from fastapi.responses import FileResponse
    p = get_settings().models_dir / "siamese_unet" / "eval" / "predictions" / Path(name).name
    if not p.exists(): raise HTTPException(404, "not found")
    return FileResponse(p)


@router.get("/dataset")
def dataset():
    from ml.datasets.levir import dataset_statistics
    s = get_settings()
    st = dataset_statistics(s.levir_root)
    st["source"] = "https://levir.buaa.edu.cn/datasets/ (Chen & Shi 2020, Remote Sensing 12(10):1662)"
    st["usage_note"] = "Dataset is for research use under the authors' terms and is NOT redistributed in this repository."
    return st


@router.get("/architecture")
def architecture():
    from ml.architecture.siamese_unet import SiameseUNet, count_parameters
    n = count_parameters(SiameseUNet(pretrained=False))
    return {"name": "Siamese U-Net", "encoder": "ResNet18 (shared weights across both dates, ImageNet init)", "parameters": n,
            "fusion": "concat[f_t1, f_t2, |f_t1 − f_t2|] → 1×1 conv at 5 scales", "decoder": "U-Net with skip connections (4 up-blocks)",
            "loss": "BCE + Dice", "optimizer": "AdamW + cosine LR", "input": "two RGB tiles 256×256 (tiled inference with Hann blending)"}


@router.get("/training")
def training(db: Session = Depends(get_db)):
    rows = db.query(m.TrainingRun).order_by(m.TrainingRun.created_at.desc()).limit(10).all()
    return [{"id": r.id, "status": r.status, "config": r.config, "history": r.history, "message": r.message} for r in rows]


@router.post("/training", status_code=202)
def start_training(body: TrainIn, db: Session = Depends(get_db)):
    if not body.confirm: raise HTTPException(422, "Training is long-running; send confirm=true to start")
    s = get_settings()
    if not (s.levir_root / "train").exists(): raise HTTPException(409, f"LEVIR-CD not found at {s.levir_root}. See docs/dataset.md")
    if db.query(m.TrainingRun).filter(m.TrainingRun.status.in_(["pending", "running"])).first():
        raise HTTPException(409, "A training run is already active")
    run = m.TrainingRun(config=body.model_dump(exclude={"confirm"}), status="pending"); db.add(run); db.commit()
    rid = run.id

    def job(update):
        from ml.training.train import train
        cfg = {"data_root": str(s.levir_root), "out_dir": str(s.models_dir / "siamese_unet"), "epochs": body.epochs, "batch_size": body.batch_size,
               "lr": body.lr, "weight_decay": 1e-4, "crop_size": 256, "crops_per_image": body.crops_per_image, "patience": 6, "seed": 42,
               "workers": 1, "pretrained": True, "cpu": False, "resume": False}
        with SessionLocal() as d:
            d.get(m.TrainingRun, rid).status = "running"; d.commit()

        def on_epoch(rec):
            with SessionLocal() as d:
                r = d.get(m.TrainingRun, rid); r.history = [*r.history, rec]; d.commit()
            update(rec["epoch"] / body.epochs, f"epoch {rec['epoch']}/{body.epochs} val F1 {rec['val_f1']:.3f}")
        try:
            res = train(cfg, on_epoch)
            with SessionLocal() as d:
                r = d.get(m.TrainingRun, rid); r.status = "completed"; r.message = "Training finished. Run evaluation to validate the checkpoint."; d.commit()
        except Exception as e:
            with SessionLocal() as d:
                r = d.get(m.TrainingRun, rid); r.status, r.message = "failed", str(e)[:500]; d.commit()
            raise
    return {"training_run_id": rid, "job_id": runner.submit("training", rid, job)}


@router.post("/evaluate", status_code=202)
def evaluate_model(db: Session = Depends(get_db)):
    s = get_settings(); d = s.models_dir / "siamese_unet"
    if not (d / "best.pt").exists(): raise HTTPException(409, "Model evaluation pending — no validated checkpoint available.")
    if not (s.levir_root / "test").exists(): raise HTTPException(409, "LEVIR-CD test split not found")

    def job(update):
        from ml.evaluation.evaluate import evaluate
        update(0.05, "evaluating on LEVIR-CD test split")
        evaluate(str(d / "best.pt"), str(s.levir_root), "test", 0.5, str(d / "eval"))
        with SessionLocal() as db2:
            model_service.sync_registry(db2)
    return {"job_id": runner.submit("evaluation", None, job)}
