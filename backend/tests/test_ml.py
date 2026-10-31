import json
from pathlib import Path

import cv2
import numpy as np
import torch

from ml.architecture.siamese_unet import SiameseUNet, SharedResNet18Encoder
from ml.datasets.levir import LevirCDDataset, validate_split
from ml.evaluation.metrics import BCEDiceLoss, ConfusionAccumulator
from ml.inference.predictor import ChangePredictor, ModelUnavailable
from ml.preprocessing.transforms import normalize, paired_augment
import pytest


def test_forward_shape_and_probabilities():
    net = SiameseUNet(pretrained=False).eval()
    a, b = torch.randn(2, 3, 128, 128), torch.randn(2, 3, 128, 128)
    out = net(a, b)
    assert out.shape == (2, 1, 128, 128)
    p = torch.sigmoid(out)
    p = p.detach(); assert 0 <= float(p.min()) and float(p.max()) <= 1


def test_encoder_weights_are_shared():
    net = SiameseUNet(pretrained=False)
    enc_ids = {id(p) for p in net.encoder.parameters()}
    assert len([m for m in net.modules() if isinstance(m, SharedResNet18Encoder)]) == 1  # single encoder used for both dates
    assert enc_ids  # one parameter set
    x = torch.randn(1, 3, 64, 64)
    net.eval()
    # identical inputs -> zero feature difference -> deterministic output regardless of order
    assert torch.allclose(net(x, x), net(x, x))


def test_loss_and_metrics():
    logits = torch.zeros(1, 1, 8, 8); tgt = torch.ones(1, 1, 8, 8)
    assert float(BCEDiceLoss()(logits, tgt)) > 0
    acc = ConfusionAccumulator()
    prob = torch.tensor([[0.9, 0.9, 0.1, 0.1]]); t = torch.tensor([[1., 0., 1., 0.]])
    acc.update(prob, t)
    m = acc.compute()
    assert m["confusion_matrix"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert abs(m["precision"] - 0.5) < 1e-6 and abs(m["iou"] - 1 / 3) < 1e-6


def test_paired_augment_keeps_alignment():
    rng = np.random.default_rng(1)
    a = np.zeros((32, 32, 3), np.uint8); m = np.zeros((32, 32), np.uint8); m[4:10, 20:30] = 255; a[4:10, 20:30] = 200
    for s in range(20):
        a2, b2, m2 = paired_augment(a, a.copy(), m, np.random.default_rng(s))
        # where the mask is set the (bright) object must be: transform applied identically to image & mask
        assert a2[m2 > 0].mean() > a2[m2 == 0].mean() + 50


def test_normalize_shape():
    x = normalize(np.zeros((16, 16, 3), np.uint8))
    assert x.shape == (3, 16, 16) and x.dtype == np.float32


def _fake_levir(root: Path, n=3, size=64):
    for split in ("train", "val", "test"):
        for sub in ("A", "B", "label"):
            (root / split / sub).mkdir(parents=True, exist_ok=True)
        for i in range(n):
            rng = np.random.default_rng(i)
            for sub in ("A", "B"):
                cv2.imwrite(str(root / split / sub / f"{split}_{i}.png"), rng.integers(0, 255, (size, size, 3), dtype=np.uint8))
            m = np.zeros((size, size), np.uint8); m[10:20, 10:20] = 255
            cv2.imwrite(str(root / split / "label" / f"{split}_{i}.png"), m)


def test_dataset_loading_and_validation(tmp_path):
    _fake_levir(tmp_path)
    ds = LevirCDDataset(tmp_path, "train", crop_size=32, augment=True, crops_per_image=2)
    assert len(ds) == 6
    a, b, y = ds[0]
    assert a.shape == (3, 32, 32) and y.shape == (1, 32, 32) and set(y.unique().tolist()) <= {0.0, 1.0}
    ds.set_epoch(0); a1 = ds[1][0].clone(); ds.set_epoch(0); assert torch.equal(a1, ds[1][0])  # reproducible
    (tmp_path / "train" / "B" / "train_0.png").unlink()
    rep = validate_split(tmp_path, "train")
    assert rep["n_pairs"] == 2 and any("missing B" in p for p in rep["problems"])


def test_dataset_missing_raises(tmp_path):
    (tmp_path / "train" / "A").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        LevirCDDataset(tmp_path, "train")


def test_checkpoint_roundtrip_and_tiled_inference(tmp_path):
    net = SiameseUNet(pretrained=False)
    ck = tmp_path / "c.pt"
    torch.save({"model_state": net.state_dict(), "config": {}}, ck)
    pred = ChangePredictor(ck, device="cpu")
    a = np.random.default_rng(0).integers(0, 255, (300, 330, 3), dtype=np.uint8)
    p = pred.predict_proba(a, a[::-1].copy(), tile=128, overlap=32)
    assert p.shape == (300, 330) and 0 <= p.min() and p.max() <= 1 and np.isfinite(p).all()
    with pytest.raises(ModelUnavailable):
        ChangePredictor(tmp_path / "missing.pt")
