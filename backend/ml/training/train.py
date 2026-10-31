"""Training entrypoint:  python -m ml.training.train --data-root data/raw/LEVIR-CD --epochs 30 ...

AdamW + BCE/Dice loss + cosine/plateau LR schedule + early stopping, resumable, seeded.
Writes: <out>/best.pt, <out>/last.pt, <out>/history.json
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from torch.utils.data import DataLoader

from ml.architecture.siamese_unet import SiameseUNet, count_parameters
from ml.datasets.levir import LevirCDDataset
from ml.evaluation.metrics import BCEDiceLoss, ConfusionAccumulator


def seed_everything(seed: int):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


@torch.no_grad()
def validate(model, loader, device, threshold=0.5):
    model.eval()
    acc = ConfusionAccumulator()
    for a, b, y in loader:
        p = torch.sigmoid(model(a.to(device), b.to(device))).cpu()
        acc.update(p, y, threshold)
    return acc.compute()


def train(cfg: dict, on_epoch: Callable[[dict], None] | None = None, should_stop: Callable[[], bool] | None = None) -> dict:
    seed_everything(cfg["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() and not cfg.get("cpu") else "cpu")
    out = Path(cfg["out_dir"]); out.mkdir(parents=True, exist_ok=True)
    tr = LevirCDDataset(cfg["data_root"], "train", cfg["crop_size"], augment=True, seed=cfg["seed"],
                        crops_per_image=cfg["crops_per_image"], max_samples=cfg.get("max_train_images"))
    va = LevirCDDataset(cfg["data_root"], "val", cfg["crop_size"], augment=False, max_samples=cfg.get("max_val_images"))
    tl = DataLoader(tr, batch_size=cfg["batch_size"], shuffle=True, num_workers=cfg["workers"], drop_last=True,
                    generator=torch.Generator().manual_seed(cfg["seed"]))
    vl = DataLoader(va, batch_size=cfg["batch_size"], num_workers=cfg["workers"])
    model = SiameseUNet(pretrained=cfg["pretrained"]).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=cfg["epochs"], eta_min=cfg["lr"] * 0.01)
    crit = BCEDiceLoss()
    history, best_f1, bad, start = [], -1.0, 0, 0
    if cfg.get("resume") and (out / "last.pt").exists():
        ck = torch.load(out / "last.pt", map_location="cpu", weights_only=False)
        model.load_state_dict(ck["model_state"]); opt.load_state_dict(ck["opt_state"]); sched.load_state_dict(ck["sched_state"])
        history, best_f1, bad, start = ck["history"], ck["best_f1"], ck["bad"], ck["epoch"] + 1
        print(f"resumed from epoch {start}")
    print(f"device={device} params={count_parameters(model):,} train_samples={len(tr)} val_samples={len(va)}")
    status = "trained"
    for epoch in range(start, cfg["epochs"]):
        if should_stop and should_stop():
            status = "stopped"; break
        t0 = time.time(); tr.set_epoch(epoch); model.train(); run = 0.0; n = 0
        for step, (a, b, y) in enumerate(tl):
            a, b, y = a.to(device), b.to(device), y.to(device)
            opt.zero_grad(set_to_none=True)
            loss = crit(model(a, b), y)
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
            run += loss.item(); n += 1
            if cfg.get("max_steps") and step + 1 >= cfg["max_steps"]:
                break
        sched.step()
        m = validate(model, vl, device)
        rec = {"epoch": epoch + 1, "train_loss": run / max(n, 1), "val_f1": m["f1"], "val_iou": m["iou"],
               "val_precision": m["precision"], "val_recall": m["recall"], "lr": opt.param_groups[0]["lr"],
               "seconds": round(time.time() - t0, 1)}
        history.append(rec); print(json.dumps(rec))
        state = {"model_state": model.state_dict(), "config": cfg, "epoch": epoch, "val_metrics": m, "arch": "SiameseUNet-ResNet18"}
        if m["f1"] > best_f1:
            best_f1, bad = m["f1"], 0
            torch.save(state, out / "best.pt")
        else:
            bad += 1
        torch.save({**state, "opt_state": opt.state_dict(), "sched_state": sched.state_dict(), "history": history,
                    "best_f1": best_f1, "bad": bad}, out / "last.pt")
        (out / "history.json").write_text(json.dumps(history, indent=2))
        if on_epoch: on_epoch(rec)
        if bad >= cfg["patience"]:
            print("early stopping"); break
    return {"status": status, "best_val_f1": best_f1, "history": history, "best_checkpoint": str(out / "best.pt")}


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", default="data/raw/LEVIR-CD")
    p.add_argument("--out-dir", default="models/siamese_unet")
    p.add_argument("--epochs", type=int, default=30); p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--lr", type=float, default=3e-4); p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--crop-size", type=int, default=256); p.add_argument("--crops-per-image", type=int, default=4)
    p.add_argument("--patience", type=int, default=8); p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=2); p.add_argument("--no-pretrained", dest="pretrained", action="store_false")
    p.add_argument("--cpu", action="store_true"); p.add_argument("--resume", action="store_true")
    p.add_argument("--max-train-images", type=int); p.add_argument("--max-val-images", type=int); p.add_argument("--max-steps", type=int)
    return vars(p.parse_args(argv))


if __name__ == "__main__":
    cfg = parse_args()
    cfg = {k.replace("-", "_"): v for k, v in cfg.items()}
    res = train(cfg)
    print(json.dumps({k: v for k, v in res.items() if k != "history"}))
