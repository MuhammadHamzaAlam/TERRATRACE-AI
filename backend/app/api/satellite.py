from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_project_or_404
from app.core.config import get_settings
from app.database import models as m
from app.database.session import SessionLocal, get_db
from app.jobs import runner
from app.satellite import copernicus as cdse

router = APIRouter(prefix="/satellite", tags=["satellite"])


class SearchIn(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)
    start: date
    end: date
    max_cloud: float = Field(default=30, ge=0, le=100)
    top: int = Field(default=20, ge=1, le=100)


class ImportIn(BaseModel):
    product_id: str
    product_name: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    acquisition_date: date
    label: str = ""


@router.get("/status")
def status():
    return cdse.integration_status()


@router.post("/search")
def search(body: SearchIn):
    if body.end < body.start: raise HTTPException(422, "end must be after start")
    if (body.bbox[2] - body.bbox[0]) * (body.bbox[3] - body.bbox[1]) > 4.0: raise HTTPException(422, "AOI too large (max ~4 square degrees)")
    try:
        return {"scenes": cdse.search_scenes(body.bbox, body.start.isoformat(), body.end.isoformat(), body.max_cloud, body.top)}
    except cdse.SatelliteError as e:
        raise HTTPException(502, str(e))


@router.get("/scenes/{product_id}/quicklook")
def quicklook(product_id: str):
    if not product_id.replace("-", "").isalnum(): raise HTTPException(422, "bad id")
    try:
        return Response(cdse.quicklook(product_id), media_type="image/jpeg")
    except cdse.SatelliteError as e:
        raise HTTPException(404, str(e))


@router.post("/projects/{project_id}/import", status_code=202)
def import_scene(project_id: str, body: ImportIn, db: Session = Depends(get_db)):
    p = get_project_or_404(project_id, db)
    if not cdse.credentials_configured():
        raise HTTPException(409, "Downloads require CDSE_USERNAME and CDSE_PASSWORD. See docs/sentinel2-integration.md")
    s = get_settings()
    oid = m.new_id("OBS")

    def job(update):
        from app.geospatial import raster
        from app.services.pipeline import make_thumbnail
        d = s.storage_dir / "observations"; d.mkdir(parents=True, exist_ok=True)
        out = d / f"{oid}.tif"
        rep = cdse.download_and_prepare({"id": body.product_id, "name": body.product_name}, body.bbox, s.storage_dir / "tmp" / oid, out, lambda f, msg: update(f * 0.9, msg))
        info = raster.inspect_raster(out)
        prev = d / f"{oid}_preview.jpg"; make_thumbnail(out, prev)
        with SessionLocal() as db2:
            db2.add(m.Observation(id=oid, project_id=p.id, label=body.label or f"Sentinel-2 {body.acquisition_date}", acquisition_date=body.acquisition_date,
                                  source="sentinel2", file_path=str(out), preview_path=str(prev), original_filename=body.product_name[:300],
                                  width=info.width, height=info.height, band_count=info.band_count, georeferenced=True, crs=info.crs,
                                  transform=info.transform, bounds_wgs84=info.bounds_wgs84, pixel_size_m=info.pixel_size_m,
                                  meta={"processing": rep, "domain_compatibility": raster.domain_compatibility(info.pixel_size_m),
                                        "product_id": body.product_id}))
            db2.commit()
    return {"observation_id": oid, "job_id": runner.submit("satellite_import", oid, job)}
