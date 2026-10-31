import json

import numpy as np
import pytest
from shapely.geometry import shape

from app.geospatial.clustering import cluster_events
from app.geospatial.events import GeoRef, extract_events, geodesic_area_m2
from app.geospatial.priority import score_event
from app.geospatial import raster
from tests.conftest import make_pair, write_geotiff, write_png


def test_pixel_geo_roundtrip_wgs84():
    g = GeoRef("EPSG:4326", [1e-5, 0, -97.0, 0, -1e-5, 33.0])
    lon, lat = g.px_to_lonlat(100, 200)
    assert lon == pytest.approx(-97.0 + 1e-3) and lat == pytest.approx(33.0 - 2e-3)
    x, y = g.lonlat_to_px(lon, lat)
    assert (x, y) == pytest.approx((100, 200), abs=1e-6)


def test_projected_crs_conversion_and_area():
    # UTM 14N, 0.5 m pixels: 100x100 px blob must be ~2500 m^2
    g = GeoRef("EPSG:32614", [0.5, 0, 500000.0, 0, -0.5, 3650000.0])
    prob = np.zeros((300, 300), np.float32); prob[50:150, 60:160] = 0.9
    evs, mask = extract_events(prob, 0.5, 20, g, morph_open=0)
    assert len(evs) == 1
    e = evs[0]
    assert e.area_px == 10000 and e.area_m2 == pytest.approx(2500, rel=0.01)
    poly = shape(e.geometry_geo)
    assert poly.is_valid and -180 <= e.centroid_geo[0] <= 180 and -90 <= e.centroid_geo[1] <= 90
    assert geodesic_area_m2(list(poly.exterior.coords)) == pytest.approx(2500, rel=0.05)  # polygon area agrees with pixel count


def test_extract_events_without_georef_has_no_geo():
    prob = np.zeros((100, 100), np.float32); prob[10:30, 10:30] = 0.8; prob[60:62, 60:62] = 0.9
    evs, _ = extract_events(prob, 0.5, 20, None, morph_open=0)
    assert len(evs) == 1 and evs[0].geometry_geo is None and evs[0].area_m2 is None and evs[0].centroid_geo is None
    assert evs[0].conf_mean == pytest.approx(0.8, abs=1e-5)


def test_clustering_pixel_and_geo():
    evs = [dict(centroid_px=[10, 10], centroid_geo=None, area_px=100, area_m2=None, conf_mean=0.9),
           dict(centroid_px=[20, 12], centroid_geo=None, area_px=50, area_m2=None, conf_mean=0.7),
           dict(centroid_px=[400, 400], centroid_geo=None, area_px=80, area_m2=None, conf_mean=0.8)]
    r = cluster_events(evs, eps=30, min_samples=2)
    assert r["labels"] == [0, 0, -1] and r["clusters"][0]["event_count"] == 2 and r["unit"] == "px"
    geo = [dict(centroid_px=[0, 0], centroid_geo=[-97.0, 33.0], area_px=1, area_m2=10, conf_mean=0.9),
           dict(centroid_px=[0, 0], centroid_geo=[-97.0003, 33.0], area_px=1, area_m2=20, conf_mean=0.9),  # ~28 m apart
           dict(centroid_px=[0, 0], centroid_geo=[-96.9, 33.0], area_px=1, area_m2=5, conf_mean=0.9)]
    r = cluster_events(geo, eps=50, min_samples=2)
    assert r["unit"] == "m" and r["labels"][:2] == [0, 0] and r["labels"][2] == -1
    assert r["clusters"][0]["total_area_m2"] == 30 and shape(r["clusters"][0]["boundary_geo"]).is_valid


def test_priority_is_explainable_and_bounded():
    r = score_event({"area_px": 500, "conf_mean": 0.9, "area_pct": 0.5}, 1000, 3, 4, 2)
    assert 0 <= r["score"] <= 100 and sum(r["contributions"].values()) == pytest.approx(r["score"], abs=0.01)
    assert set(r["factors"]) == {"area", "confidence", "concentration", "relative_change", "recurrence"}
    low = score_event({"area_px": 5, "conf_mean": 0.5, "area_pct": 0.0}, 1000, 0, 4, 1)
    assert low["score"] < r["score"]


def test_alignment_checks(tmp_path):
    from types import SimpleNamespace as NS
    def o(w, h, geo, bounds=None, crs=None, tf=None):
        return NS(width=w, height=h, georeferenced=geo, bounds_wgs84=bounds, crs=crs, transform=tf)
    assert raster.check_alignment(o(100, 100, False), o(100, 100, False))["status"] == "ok"
    assert raster.check_alignment(o(100, 100, False), o(120, 100, False))["status"] == "unsuitable"
    assert raster.check_alignment(o(100, 100, True, [0, 0, 1, 1], "EPSG:4326", [1] * 6), o(100, 100, False))["status"] == "unsuitable"
    far = raster.check_alignment(o(10, 10, True, [0, 0, 1, 1], "EPSG:4326", [1] * 6), o(10, 10, True, [5, 5, 6, 6], "EPSG:4326", [1] * 6))
    assert far["status"] == "unsuitable"


def test_domain_compatibility_levels():
    assert raster.domain_compatibility(0.5)["status"] == "compatible"
    assert raster.domain_compatibility(10.0)["status"] == "unvalidated"
    assert raster.domain_compatibility(None)["status"] == "unknown"


def test_inspect_and_sniff(tmp_path):
    a, _ = make_pair(128)
    png = write_png(tmp_path / "a.png", a)
    assert raster.inspect_raster(png).georeferenced is False
    tif = write_geotiff(tmp_path / "a.tif", a)
    info = raster.inspect_raster(tif)
    assert info.georeferenced and info.crs == "EPSG:4326" and info.pixel_size_m == pytest.approx(0.467, abs=0.01)
    bad = tmp_path / "bad.png"; bad.write_bytes(b"not an image at all")
    with pytest.raises(raster.RasterError):
        raster.inspect_raster(bad)


def test_phase_correlation_detects_shift():
    a, _ = make_pair(256)
    shifted = np.roll(a, 7, axis=1)
    dx, dy, _ = raster.registration_shift(a, shifted)
    assert abs(abs(dx) - 7) < 1.0 and abs(dy) < 1.0
