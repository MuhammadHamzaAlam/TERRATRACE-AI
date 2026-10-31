#!/usr/bin/env python
"""Create a REAL demo project from the bundled NAIP sample (data/samples/naip_leander) through the running backend API.

Requires: backend running (default http://localhost:8000) and a model checkpoint (see docs/ml-pipeline.md).
Creates one project with three dated observations (2018, 2020, 2022 — real NAIP acquisition dates) and runs
consecutive analyses plus first-vs-latest, so temporal monitoring and tracking have real data to work on.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000/api")
    ap.add_argument("--sample", default=str(ROOT / "data/samples/naip_leander"))
    a = ap.parse_args()
    sample = Path(a.sample)
    src = json.loads((sample / "SOURCE.json").read_text())
    c = httpx.Client(base_url=a.api, timeout=120)
    st = c.get("/model/status").json()
    if not st["inference_available"]:
        sys.exit("No model checkpoint available — analyses would be blocked. Train one first (docs/ml-pipeline.md).")
    p = c.post("/projects", json={"name": "Leander TX — NAIP demo", "description": "Real USDA NAIP aerial imagery (public domain), 0.6 m, 640 m window. New construction between 2018 and 2022."}).json()
    obs = []
    for it in sorted(src["items"], key=lambda x: x["acquired"]):
        with open(sample / it["file"], "rb") as f:
            r = c.post(f"/projects/{p['id']}/observations", data={"acquisition_date": it["acquired"], "label": f"NAIP {it['year']}"}, files={"file": (it["file"], f)})
        r.raise_for_status(); obs.append(r.json()); print("uploaded", it["file"], it["acquired"])
    pairs = [(0, 1), (1, 2), (0, 2)]
    ids = []
    for i, j in pairs:
        r = c.post(f"/projects/{p['id']}/analyses", json={"before_observation_id": obs[i]["id"], "after_observation_id": obs[j]["id"]}); r.raise_for_status(); ids.append(r.json()["id"])
    for aid in ids:
        while True:
            s = c.get(f"/analyses/{aid}").json()
            if s["status"] in ("completed", "failed", "blocked"): break
            time.sleep(2)
        print(aid, s["status"], s["metrics"].get("n_events"), "events", s["status_message"] if s["status"] != "completed" else "")
    print("project:", p["id"])


if __name__ == "__main__":
    main()
