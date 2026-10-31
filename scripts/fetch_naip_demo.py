#!/usr/bin/env python
"""Download a small, REAL georeferenced demo pair from USDA NAIP (public domain) via the Microsoft Planetary Computer STAC API.

NAIP is aerial RGB imagery at 0.6 m (2018+), close to the LEVIR-CD domain, so results on it are meaningful (though still
not formally validated by us). No account is needed; a short-lived read token is requested from the public SAS endpoint.

usage: python scripts/fetch_naip_demo.py --lon -97.6 --lat 30.45 --size-m 640 --years 2018 2022 --out data/samples/naip_demo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/naip"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lon", type=float, required=True); ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--size-m", type=float, default=640); ap.add_argument("--years", type=int, nargs="+", default=[2018, 2022])
    ap.add_argument("--out", default="data/samples/naip_demo")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    d = 1e-5 * a.size_m / 1.11
    bbox = [a.lon - d, a.lat - d, a.lon + d, a.lat + d]
    items = httpx.post(STAC, json={"collections": ["naip"], "bbox": bbox, "limit": 50}, timeout=40).json()["features"]
    token = httpx.get(SAS, timeout=30).json()["token"]
    meta = []
    for y in a.years:
        cand = [i for i in items if i["properties"]["datetime"].startswith(str(y))]
        if not cand:
            raise SystemExit(f"No NAIP item for {y} at this location. Available: {sorted({i['properties']['datetime'][:4] for i in items})}")
        it = cand[0]
        href = it["assets"]["image"]["href"] + "?" + token
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
            with rasterio.open(href) as ds:
                x, yy = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform(a.lon, a.lat)
                half = a.size_m / 2
                win = from_bounds(x - half, yy - half, x + half, yy + half, ds.transform).round_offsets().round_lengths()
                data = ds.read([1, 2, 3], window=win)
                prof = dict(driver="GTiff", height=data.shape[1], width=data.shape[2], count=3, dtype="uint8", crs=ds.crs,
                            transform=ds.window_transform(win), compress="jpeg", photometric="ycbcr", jpeg_quality=90)
        p = out / f"naip_{y}.tif"
        with rasterio.open(p, "w", **prof) as dst:
            dst.write(data)
        meta.append({"year": y, "item": it["id"], "acquired": it["properties"]["datetime"][:10], "gsd_m": it["properties"].get("gsd"), "file": p.name, "size": [data.shape[2], data.shape[1]]})
        print("wrote", p, data.shape)
    (out / "SOURCE.json").write_text(json.dumps({"source": "USDA NAIP via Microsoft Planetary Computer STAC", "license": "Public domain (USDA FSA)", "center_lonlat": [a.lon, a.lat], "size_m": a.size_m, "items": meta}, indent=2))


if __name__ == "__main__":
    main()
