"""Test fixtures. NOTE: the stub predictor and synthetic imagery are TEST DOUBLES for plumbing/geometry tests only;
they are never used by the application at runtime."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="tt_test_"))
os.environ.update(DATABASE_URL=f"sqlite:///{_TMP/'test.db'}", STORAGE_DIR=str(_TMP / "storage"), MODELS_DIR=str(_TMP / "models"),
                  REPORTS_DIR=str(_TMP / "reports"), LEVIR_ROOT=str(_TMP / "levir"), RATE_LIMIT_PER_MINUTE="100000",
                  OLLAMA_MODEL="test-model", OLLAMA_BASE_URL="http://127.0.0.1:9", XAI_API_KEY="", CDSE_USERNAME="", CDSE_PASSWORD="")

import cv2
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from app.database.session import Base, engine, SessionLocal
from app.jobs import runner
from app.main import app
from app.services import model_service


class SyncPool:
    def submit(self, fn):
        fn()


class StubPredictor:
    """Deterministic stand-in for the trained network: probability from grayscale difference."""
    meta = {"stub": True}

    def predict_proba(self, before, after, tile=256, overlap=32, batch_size=4, progress=None):
        d = np.abs(cv2.cvtColor(before, cv2.COLOR_RGB2GRAY).astype(np.float32) - cv2.cvtColor(after, cv2.COLOR_RGB2GRAY).astype(np.float32)) / 255
        p = np.clip(d * 4, 0, 1)
        if progress: progress(1.0)
        return cv2.GaussianBlur(p, (5, 5), 0)


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    monkeypatch.setattr(runner, "_pool", SyncPool())
    monkeypatch.setattr(model_service, "get_predictor", lambda: StubPredictor())
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make_base(size=512, seed=0):
    rng = np.random.default_rng(seed)
    base = cv2.GaussianBlur(rng.integers(60, 120, (size, size, 3), dtype=np.uint8), (0, 0), 6)
    return base


def make_pair(size=512, blocks=((100, 100, 40, 40), (120, 160, 30, 30), (380, 380, 50, 50)), seed=0):
    a = make_base(size, seed)
    b = a.copy()
    for x, y, w, h in blocks:
        b[y:y + h, x:x + w] = (230, 230, 235)
    return a, b


def write_png(path: Path, img):
    cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR)); return path


def write_geotiff(path: Path, img, west=-97.0, north=33.0, res_deg=5e-6, crs="EPSG:4326"):
    """Synthetic georeference for tests only."""
    h, w = img.shape[:2]
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=3, dtype="uint8", crs=crs,
                       transform=from_origin(west, north, res_deg, res_deg)) as ds:
        ds.write(img.transpose(2, 0, 1))
    return path


def upload(client, pid, path, date_str, label=""):
    with open(path, "rb") as f:
        r = client.post(f"/api/projects/{pid}/observations", data={"acquisition_date": date_str, "label": label},
                        files={"file": (Path(path).name, f, "application/octet-stream")})
    return r
