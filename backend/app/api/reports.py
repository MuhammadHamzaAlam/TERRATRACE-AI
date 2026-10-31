from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404, get_project_or_404
from app.database import models as m
from app.database.session import get_db
from app.reporting import exports, service
from app.schemas.api import ReportIn

router = APIRouter(tags=["reports"])


def report_dict(r: m.Report, full: bool = False) -> dict:
    d = {"id": r.id, "project_id": r.project_id, "analysis_id": r.analysis_id, "kind": r.kind, "title": r.title,
         "has_narrative": bool(r.narrative), "narrative_provider": r.narrative_provider, "created_at": r.created_at.isoformat()}
    if full: d.update(data=r.data, narrative=r.narrative)
    return d


@router.post("/projects/{project_id}/reports", status_code=201)
async def generate_report(project_id: str, body: ReportIn, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    if not body.analysis_id: raise HTTPException(422, "analysis_id required")
    an = get_analysis_or_404(db, body.analysis_id)
    if an.project_id != project_id: raise HTTPException(403, "Analysis belongs to a different project")
    if an.status != "completed": raise HTTPException(409, f"Analysis is '{an.status}', not completed")
    other = None
    if body.kind == "comparison":
        if not body.compare_analysis_id: raise HTTPException(422, "compare_analysis_id required")
        other = get_analysis_or_404(db, body.compare_analysis_id)
        if other.project_id != project_id or other.status != "completed": raise HTTPException(409, "Comparison analysis unavailable")
    narrative = provider = None
    if body.with_narrative:
        from app.llm.orchestration.narrative import generate_narrative
        data = service.build_comparison_data(db, an, other) if other else service.build_analysis_data(db, an)
        narrative, provider = await generate_narrative(data, body.kind)  # None if no provider reachable
    r = service.create_report(db, body.kind, an, other, narrative, provider)
    return report_dict(r)


@router.get("/projects/{project_id}/reports")
def list_reports(project_id: str, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    return [report_dict(r) for r in db.query(m.Report).filter_by(project_id=project_id).order_by(m.Report.created_at.desc()).all()]


@router.get("/reports")
def all_reports(limit: int = 20, db: Session = Depends(get_db)):
    return [report_dict(r) for r in db.query(m.Report).order_by(m.Report.created_at.desc()).limit(limit).all()]


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    r = db.get(m.Report, report_id)
    if not r: raise HTTPException(404, "Report not found")
    return report_dict(r, full=True)


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: str, db: Session = Depends(get_db)):
    r = db.get(m.Report, report_id)
    if not r or not r.pdf_path or not Path(r.pdf_path).exists(): raise HTTPException(404, "PDF not found")
    return FileResponse(r.pdf_path, media_type="application/pdf", filename=f"{r.id}.pdf")


@router.get("/analyses/{analysis_id}/export/csv")
def export_csv(analysis_id: str, db: Session = Depends(get_db)):
    get_analysis_or_404(db, analysis_id)
    return Response(exports.events_csv(db, analysis_id), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{analysis_id}_events.csv"'})


@router.get("/analyses/{analysis_id}/export/geojson")
def export_geojson(analysis_id: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id)
    if not a.before_obs.georeferenced:
        raise HTTPException(409, "GeoJSON export unavailable: analysis has no georeferencing")
    return JSONResponse(exports.events_geojson(db, analysis_id), media_type="application/geo+json",
                        headers={"Content-Disposition": f'attachment; filename="{analysis_id}_events.geojson"'})
