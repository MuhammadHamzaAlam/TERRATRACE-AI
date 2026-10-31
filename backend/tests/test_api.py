"""Integration tests through the real FastAPI app + SQLite + real pipeline (stub predictor replaces the neural network)."""
import json

import pytest

from tests.conftest import make_pair, upload, write_geotiff, write_png


def _project(client, name="Test AOI"):
    r = client.post("/api/projects", json={"name": name, "description": "d"}); assert r.status_code == 201
    return r.json()["id"]


def _two_obs_png(client, tmp_path, pid, d1="2025-01-10", d2="2025-06-10", **kw):
    a, b = make_pair(**kw)
    o1 = upload(client, pid, write_png(tmp_path / "a.png", a), d1).json()
    o2 = upload(client, pid, write_png(tmp_path / "b.png", b), d2).json()
    return o1, o2


def _run(client, pid, o1, o2, **cfg):
    r = client.post(f"/api/projects/{pid}/analyses", json={"before_observation_id": o1["id"], "after_observation_id": o2["id"], **cfg})
    assert r.status_code == 201, r.text
    return client.get(f"/api/analyses/{r.json()['id']}").json()


def test_full_workflow_pixel_mode(client, tmp_path):
    pid = _project(client)
    o1, o2 = _two_obs_png(client, tmp_path, pid)
    assert o1["georeferenced"] is False
    an = _run(client, pid, o1, o2)
    assert an["status"] == "completed", an["status_message"]
    assert an["metrics"]["n_events"] >= 3 and an["has_mask"]
    ev = client.get(f"/api/projects/{pid}/events", params={"analysis_id": an["id"]}).json()
    assert ev["total"] == an["metrics"]["n_events"]
    e0 = ev["events"][0]
    assert e0["centroid_geo"] is None and e0["area_m2"] is None and e0["review_status"] == "pending"   # no invented geography
    assert client.get(f"/api/analyses/{an['id']}/geojson").status_code == 409
    assert client.get(f"/api/analyses/{an['id']}/export/geojson").status_code == 409
    csv = client.get(f"/api/analyses/{an['id']}/export/csv"); assert csv.status_code == 200 and "event_id" in csv.text
    for kind in ("before", "after", "mask", "overlay"):
        assert client.get(f"/api/analyses/{an['id']}/image/{kind}").status_code == 200
    for kind in ("before", "after", "mask"):
        assert client.get(f"/api/events/{e0['uid']}/crop/{kind}").headers["content-type"] == "image/png"
    # review + audit trail
    r = client.post(f"/api/events/{e0['uid']}/review", json={"status": "confirmed", "notes": "clear new roof"}, headers={"X-Reviewer": "analyst1"})
    assert r.status_code == 200
    d = client.get(f"/api/events/{e0['uid']}").json()
    assert d["review_status"] == "confirmed" and d["history"][0]["previous_status"] == "pending" and d["history"][0]["reviewer"] == "analyst1"
    assert client.post(f"/api/events/{e0['uid']}/review", json={"status": "bogus"}).status_code == 422
    assert client.post(f"/api/events/{e0['uid']}/review", json={"status": "confirmed"}).status_code == 422  # unchanged, no note
    # report: deterministic PDF
    rep = client.post(f"/api/projects/{pid}/reports", json={"kind": "analysis", "analysis_id": an["id"]})
    assert rep.status_code == 201
    pdf = client.get(f"/api/reports/{rep.json()['id']}/pdf"); assert pdf.content[:4] == b"%PDF"
    assert client.get(f"/api/reports/{rep.json()['id']}").json()["data"]["human_verification"]["confirmed_event_ids"] == [e0["event_id"]]
    # overview reads DB values
    ov = client.get("/api/overview").json()
    assert ov["counts"]["projects"] == 1 and ov["counts"]["events"] == an["metrics"]["n_events"] and ov["counts"]["events_confirmed"] == 1


def test_georeferenced_workflow_and_exports(client, tmp_path):
    pid = _project(client)
    a, b = make_pair(512)
    o1 = upload(client, pid, write_geotiff(tmp_path / "a.tif", a), "2025-01-01").json()
    o2 = upload(client, pid, write_geotiff(tmp_path / "b.tif", b), "2025-03-01").json()
    assert o1["georeferenced"] and o1["bounds_wgs84"]
    an = _run(client, pid, o1, o2)
    assert an["status"] == "completed" and an["metrics"]["georeferenced"] and an["metrics"]["changed_area_m2"] > 0
    gj = client.get(f"/api/analyses/{an['id']}/export/geojson").json()
    from shapely.geometry import shape
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == an["metrics"]["n_events"]
    for f in gj["features"]:
        assert shape(f["geometry"]).is_valid
    ev = client.get(f"/api/projects/{pid}/events", params={"analysis_id": an["id"]}).json()["events"]
    assert all(-97.01 < e["centroid_geo"][0] < -96.99 and 32.99 < e["centroid_geo"][1] < 33.01 for e in ev)
    # AOI filtering
    aoi = client.post(f"/api/projects/{pid}/aois", json={"name": "west half", "geometry": {"type": "Polygon", "coordinates": [[[-97.0, 33.0], [-96.9988, 33.0], [-96.9988, 32.99, ], [-97.0, 32.99], [-97.0, 33.0]]]}}).json()
    inside = client.get(f"/api/aois/{aoi['id']}/events").json()
    assert 0 < inside["n_events"] <= len(ev)
    assert client.post(f"/api/projects/{pid}/aois", json={"name": "bad", "geometry": {"type": "Point", "coordinates": [0, 0]}}).status_code == 422
    # clusters expose geometry
    cl = client.get(f"/api/projects/{pid}/clusters", params={"analysis_id": an["id"]}).json()
    assert cl and cl[0]["boundary_geo"]


def test_multidate_tracking_and_comparison(client, tmp_path):
    pid = _project(client)
    a, _ = make_pair(512)
    _, b1 = make_pair(512, blocks=((100, 100, 40, 40), (380, 380, 50, 50)))
    _, b2 = make_pair(512, blocks=((100, 100, 40, 40), (380, 380, 50, 50), (250, 60, 45, 45)))  # one extra later
    obs = [upload(client, pid, write_geotiff(tmp_path / f"{i}.tif", img), d).json() for i, (img, d) in enumerate([(a, "2025-01-01"), (b1, "2025-03-01"), (b2, "2025-06-01")])]
    a1 = _run(client, pid, obs[0], obs[1])    # first -> March
    a2 = _run(client, pid, obs[0], obs[2])    # first -> June (cumulative)
    ev1 = client.get(f"/api/projects/{pid}/events", params={"analysis_id": a1["id"]}).json()["events"]
    ev2 = client.get(f"/api/projects/{pid}/events", params={"analysis_id": a2["id"]}).json()["events"]
    assert len(ev1) == 2 and len(ev2) == 3
    assert {e["temporal_status"] for e in ev1} == {"new"}
    assert sorted(e["temporal_status"] for e in ev2) == ["new", "recurring", "recurring"]
    assert len({e["track_id"] for e in ev1 + ev2}) == 3
    cmp_ = client.get(f"/api/analyses/{a1['id']}/compare/{a2['id']}").json()
    assert cmp_["delta"]["n_events"] == 1 and len(cmp_["new_in_b"]) == 1 and len(cmp_["persisting"]) == 2 and cmp_["not_detected_in_b"] == []
    rev = client.get(f"/api/analyses/{a2['id']}/compare/{a1['id']}").json()
    assert len(rev["not_detected_in_b"]) == 1       # events that no longer appear
    d = client.get(f"/api/events/{[e for e in ev2 if e['temporal_status']=='recurring'][0]['uid']}").json()
    assert d["track"]["n_observations"] == 2 and len(d["track"]["observations"]) == 2
    tl = client.get(f"/api/projects/{pid}/timeline").json()
    assert len(tl["observations"]) == 3 and tl["tracks"] == {"total": 3, "recurring": 2, "single": 1}
    # comparison report
    r = client.post(f"/api/projects/{pid}/reports", json={"kind": "comparison", "analysis_id": a1["id"], "compare_analysis_id": a2["id"]})
    assert r.status_code == 201 and client.get(f"/api/reports/{r.json()['id']}/pdf").content[:4] == b"%PDF"


def test_missing_history_is_not_invented(client, tmp_path):
    pid = _project(client)
    tl = client.get(f"/api/projects/{pid}/timeline").json()
    assert tl["observations"] == [] and tl["analyses"] == [] and tl["tracks"]["total"] == 0


def test_upload_validation(client, tmp_path):
    import os
    d = os.environ["STORAGE_DIR"] + "/observations"
    count = lambda: len(os.listdir(d)) if os.path.exists(d) else 0
    pid = _project(client)
    before = count()
    bad = tmp_path / "x.png"; bad.write_bytes(b"GIF89a not png")
    assert upload(client, pid, bad, "2025-01-01").status_code == 422          # content sniffing, not extension
    txt = tmp_path / "x.txt"; txt.write_text("hi")
    assert upload(client, pid, txt, "2025-01-01").status_code == 415
    a, _ = make_pair(128)
    assert upload(client, pid, write_png(tmp_path / "ok.png", a), "2999-01-01").status_code == 422   # future date
    assert count() == before                                                   # rejected uploads leave no files behind


def test_blocked_conditions(client, tmp_path):
    pid = _project(client)
    a, b = make_pair(256)
    o1 = upload(client, pid, write_png(tmp_path / "a.png", a), "2025-01-01").json()
    o2 = upload(client, pid, write_png(tmp_path / "b.png", make_pair(300)[1]), "2025-02-01").json()
    assert _run(client, pid, o1, o2)["status"] == "blocked"                      # unaligned sizes, no georef
    o3 = upload(client, pid, write_png(tmp_path / "c.png", b), "2024-01-01").json()
    assert _run(client, pid, o1, o3)["status"] == "blocked"                      # after earlier than before
    assert client.post(f"/api/projects/{pid}/analyses", json={"before_observation_id": o1["id"], "after_observation_id": o1["id"]}).status_code == 422


def test_model_unavailable_state(client, tmp_path, monkeypatch):
    from ml.inference.predictor import ModelUnavailable
    from app.services import model_service
    def boom(): raise ModelUnavailable("No model checkpoint available.")
    monkeypatch.setattr(model_service, "get_predictor", boom)
    pid = _project(client); o1, o2 = _two_obs_png(client, tmp_path, pid)
    an = _run(client, pid, o1, o2)
    assert an["status"] == "blocked" and "checkpoint" in an["status_message"]
    st = client.get("/api/model/status").json()
    assert st["status"] == "not_initialized" and "pending" in st["message"]


def test_project_crud_and_guarded_delete(client):
    pid = _project(client, "Alpha")
    assert client.patch(f"/api/projects/{pid}", json={"name": "Beta"}).json()["name"] == "Beta"
    assert client.delete(f"/api/projects/{pid}", params={"confirm_name": "wrong"}).status_code == 400
    assert client.delete(f"/api/projects/{pid}", params={"confirm_name": "Beta"}).status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.post("/api/projects", json={"name": ""}).status_code == 422


def test_bulk_review_requires_confirmation(client, tmp_path):
    pid = _project(client); o1, o2 = _two_obs_png(client, tmp_path, pid); an = _run(client, pid, o1, o2)
    uids = [e["uid"] for e in client.get(f"/api/projects/{pid}/events", params={"analysis_id": an["id"]}).json()["events"]]
    body = {"event_ids": uids, "status": "rejected", "notes": "bulk"}
    assert client.post(f"/api/projects/{pid}/events/bulk-review", json=body).status_code == 422
    assert client.post(f"/api/projects/{pid}/events/bulk-review", json={**body, "confirm": True}).json()["updated"] == len(uids)
    hist = client.get(f"/api/projects/{pid}/review-history").json()
    assert len(hist) == len(uids)
    other = _project(client, "Other")
    assert client.post(f"/api/projects/{other}/events/bulk-review", json={**body, "confirm": True}).status_code == 422  # cross-project ids rejected


def test_satellite_status_without_credentials(client):
    s = client.get("/api/satellite/status").json()
    assert s["download_available"] is False and "CDSE_USERNAME" in s["message"]
    pid = _project(client)
    r = client.post(f"/api/satellite/projects/{pid}/import", json={"product_id": "x", "product_name": "y", "bbox": [0, 0, 1, 1], "acquisition_date": "2025-01-01"})
    assert r.status_code == 409
