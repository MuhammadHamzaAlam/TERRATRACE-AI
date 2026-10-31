from __future__ import annotations

import json
import shutil
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from shapely.geometry import shape
from sqlalchemy.orm import Session

from app.api.deps import get_project_or_404
from app.core.config import get_settings
from app.database import models as m
from app.database.session import get_db
from app.geospatial import raster
from app.schemas.api import AOIIn, ProjectIn, ProjectPatch
from app.services import queries
from app.services.pipeline import make_thumbnail

router = APIRouter(tags=["projects"])


def project_dict(p: m.Project, db: Session) -> dict:
    return {"id": p.id, "name": p.name, "description": p.description, "owner": p.owner, "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
            "counts": {"observations": db.query(m.Observation).filter_by(project_id=p.id).count(),
                       "analyses": db.query(m.Analysis).filter_by(project_id=p.id).count(),
                       "events": db.query(m.Event).filter_by(project_id=p.id).count(),
                       "aois": db.query(m.AOI).filter_by(project_id=p.id).count()}}


def obs_dict(o: m.Observation) -> dict:
    return {"id": o.id, "project_id": o.project_id, "label": o.label, "acquisition_date": o.acquisition_date.isoformat(),
            "source": o.source, "original_filename": o.original_filename, "width": o.width, "height": o.height,
            "band_count": o.band_count, "georeferenced": o.georeferenced, "crs": o.crs, "bounds_wgs84": o.bounds_wgs84,
            "pixel_size_m": o.pixel_size_m, "meta": o.meta, "created_at": o.created_at.isoformat()}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db)):
    p = m.Project(name=body.name.strip(), description=body.description)
    db.add(p); db.commit()
    return project_dict(p, db)


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    return [project_dict(p, db) for p in db.query(m.Project).order_by(m.Project.created_at.desc()).all()]


@router.get("/projects/{project_id}")
def get_project(p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return project_dict(p, db)


@router.patch("/projects/{project_id}")
def update_project(body: ProjectPatch, p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    if body.name is not None: p.name = body.name.strip()
    if body.description is not None: p.description = body.description
    db.commit()
    return project_dict(p, db)


@router.delete("/projects/{project_id}")
def delete_project(confirm_name: str, p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    """Destructive: requires the exact project name as confirmation. Removes DB rows and stored files."""
    if confirm_name != p.name:
        raise HTTPException(400, "confirm_name must equal the project name")
    s = get_settings()
    for o in p.observations:
        for f in (o.file_path, o.preview_path):
            if f: Path(f).unlink(missing_ok=True)
    for a in p.analyses:
        shutil.rmtree(s.storage_dir / "analyses" / a.id, ignore_errors=True)
    db.delete(p); db.commit()
    return {"deleted": p.id}


@router.get("/projects/{project_id}/timeline")
def project_timeline(p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return queries.timeline(db, p.id)


# ---------- observations ----------
@router.post("/projects/{project_id}/observations", status_code=201)
async def upload_observation(acquisition_date: date = Form(...), label: str = Form(""), file: UploadFile = File(...),
                             p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    s = get_settings()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in raster.ALLOWED_EXT:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(raster.ALLOWED_EXT))}")
    if acquisition_date > date.today():
        raise HTTPException(422, "acquisition_date cannot be in the future")
    oid = m.new_id("OBS")
    dest_dir = s.storage_dir / "observations"; dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{oid}{ext}"  # unique, server-generated filename: client name is never used as a path
    size, limit = 0, s.max_upload_mb * 1024 * 1024
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close(); dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {s.max_upload_mb} MB limit")
            out.write(chunk)
    try:
        info = raster.inspect_raster(dest)
        prev = dest_dir / f"{oid}_preview.jpg"
        make_thumbnail(dest, prev)
    except raster.RasterError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not process image: {e}")
    o = m.Observation(id=oid, project_id=p.id, label=label.strip()[:200] or acquisition_date.isoformat(), acquisition_date=acquisition_date,
                      file_path=str(dest), preview_path=str(prev), original_filename=(file.filename or "")[:300], width=info.width,
                      height=info.height, band_count=info.band_count, georeferenced=info.georeferenced, crs=info.crs,
                      transform=info.transform, bounds_wgs84=info.bounds_wgs84, pixel_size_m=info.pixel_size_m,
                      meta={**info.meta, "domain_compatibility": raster.domain_compatibility(info.pixel_size_m)})
    db.add(o); db.commit()
    return obs_dict(o)


@router.get("/projects/{project_id}/observations")
def list_observations(p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return [obs_dict(o) for o in db.query(m.Observation).filter_by(project_id=p.id).order_by(m.Observation.acquisition_date).all()]


@router.get("/observations/{obs_id}")
def get_observation(obs_id: str, db: Session = Depends(get_db)):
    o = db.get(m.Observation, obs_id)
    if not o: raise HTTPException(404, "Observation not found")
    return obs_dict(o)


@router.get("/observations/{obs_id}/preview")
def observation_preview(obs_id: str, db: Session = Depends(get_db)):
    o = db.get(m.Observation, obs_id)
    if not o or not o.preview_path or not Path(o.preview_path).exists(): raise HTTPException(404, "Preview not found")
    return FileResponse(o.preview_path, media_type="image/jpeg")


# ---------- AOIs ----------
@router.post("/projects/{project_id}/aois", status_code=201)
def create_aoi(body: AOIIn, p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    a = m.AOI(project_id=p.id, name=body.name.strip(), geometry=body.geometry)
    db.add(a); db.commit()
    return {"id": a.id, "name": a.name, "geometry": a.geometry}


@router.post("/projects/{project_id}/aois/upload", status_code=201)
async def upload_aoi_geojson(file: UploadFile = File(...), p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024: raise HTTPException(413, "GeoJSON larger than 2 MB")
    try:
        gj = json.loads(raw)
    except Exception:
        raise HTTPException(422, "File is not valid JSON")
    feats = gj.get("features") if gj.get("type") == "FeatureCollection" else [gj] if gj.get("type") == "Feature" else [{"properties": {}, "geometry": gj}]
    created = []
    for i, f in enumerate(feats[:50]):
        try:
            body = AOIIn(name=(f.get("properties") or {}).get("name") or f"{(file.filename or 'AOI')[:60]} #{i + 1}", geometry=f["geometry"])
        except Exception as e:
            raise HTTPException(422, f"Feature {i}: {e}")
        a = m.AOI(project_id=p.id, name=body.name, geometry=body.geometry); db.add(a); created.append(a)
    db.commit()
    return [{"id": a.id, "name": a.name, "geometry": a.geometry} for a in created]


@router.get("/projects/{project_id}/aois")
def list_aois(p: m.Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    return [{"id": a.id, "name": a.name, "geometry": a.geometry} for a in p.aois]


@router.delete("/aois/{aoi_id}")
def delete_aoi(aoi_id: str, db: Session = Depends(get_db)):
    a = db.get(m.AOI, aoi_id)
    if not a: raise HTTPException(404, "AOI not found")
    db.delete(a); db.commit()
    return {"deleted": aoi_id}


@router.get("/aois/{aoi_id}/events")
def events_in_aoi(aoi_id: str, db: Session = Depends(get_db)):
    a = db.get(m.AOI, aoi_id)
    if not a: raise HTTPException(404, "AOI not found")
    return aoi_events(db, a)


def aoi_events(db: Session, a: m.AOI, analysis_id: str | None = None) -> dict:
    from shapely.geometry import Point
    g = shape(a.geometry)
    q = db.query(m.Event).filter(m.Event.project_id == a.project_id, m.Event.centroid_geo.isnot(None))
    if analysis_id: q = q.filter(m.Event.analysis_id == analysis_id)
    inside = [e for e in q.all() if g.contains(Point(*e.centroid_geo))]
    return {"aoi_id": a.id, "name": a.name, "n_events": len(inside), "total_area_m2": sum(e.area_m2 or 0 for e in inside),
            "events": [queries.event_dict(e) for e in inside]}
