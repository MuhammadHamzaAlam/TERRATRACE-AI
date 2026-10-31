"""Deterministic reporting (Layer A) — built only from stored records; no LLM involved. Optional narrative is Layer B."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import models as m
from app.services import queries

LIMITATIONS = [
    "Detections are model predictions (candidate change events), not confirmed real-world changes.",
    "Model confidence is the mean predicted probability inside an event; it is not a measure of factual certainty.",
    "The model was trained on LEVIR-CD (0.5 m RGB imagery, building changes). Performance on other sensors, resolutions or "
    "change types (vegetation, roads, vehicles, flooding) is not validated.",
    "Analytical priority scores order events for human review; they do not indicate threat, intent or significance.",
    "Only events a human analyst has marked 'Confirmed change' are human-verified findings.",
]


def build_analysis_data(db: Session, an: m.Analysis) -> dict:
    s = queries.analysis_summary(db, an)
    evs = db.query(m.Event).filter(m.Event.analysis_id == an.id).order_by(m.Event.priority_score.desc()).all()
    cls = db.query(m.Cluster).filter(m.Cluster.analysis_id == an.id).order_by(m.Cluster.label).all()
    mv = db.get(m.ModelVersion, an.model_version_id) if an.model_version_id else None
    project = db.get(m.Project, an.project_id)
    prio_bins = [{"range": f"{lo}-{hi}", "count": sum(1 for e in evs if lo <= e.priority_score < hi)} for lo, hi in ((0, 25), (25, 50), (50, 75), (75, 100.01))]
    return {
        "project": {"id": project.id, "name": project.name, "description": project.description},
        "analysis": s,
        "observations": [{"role": "before", "id": an.before_obs.id, "date": an.before_obs.acquisition_date.isoformat(), "source": an.before_obs.source,
                          "file": an.before_obs.original_filename},
                         {"role": "after", "id": an.after_obs.id, "date": an.after_obs.acquisition_date.isoformat(), "source": an.after_obs.source,
                          "file": an.after_obs.original_filename}],
        "area_of_interest": an.before_obs.bounds_wgs84 if an.before_obs.georeferenced else None,
        "georeferenced": an.before_obs.georeferenced,
        "calculated_statistics": {"n_events": len(evs), "changed_pct": s["changed_pct"], "changed_pixels": s["changed_pixels"],
                                  "changed_area_m2": s["changed_area_m2"], "confidence_distribution": s["confidence_distribution"],
                                  "priority_distribution": prio_bins},
        "clusters": [queries.cluster_dict(c) for c in cls],
        "top_events": [queries.event_dict(e) for e in evs[:10]],
        "human_verification": {"counts": s["review_status_counts"],
                               "confirmed_event_ids": [e.label for e in evs if e.review_status == "confirmed"]},
        "model": {"id": mv.id if mv else None, "architecture": mv.architecture if mv else None, "dataset": "LEVIR-CD",
                  "validated_on_test": bool(mv and mv.validated), "test_metrics": (mv.metrics or {}).get("test") if mv else None},
        "methodology": ["Siamese U-Net (shared ResNet18 encoder) predicts per-pixel change probability on tiled images.",
                        f"Probability >= {(an.config or {}).get('threshold', 0.5)} is thresholded; connected components >= "
                        f"{(an.config or {}).get('min_event_pixels', 20)} px become candidate events.",
                        "DBSCAN groups spatially related events; priority = weighted, explainable factor sum (see priority_factors).",
                        "Events are associated across analyses by polygon overlap / centroid proximity."],
        "alignment": an.alignment, "domain_compatibility": an.compatibility,
        "data_source": f"{an.before_obs.source} / {an.after_obs.source}", "limitations": LIMITATIONS,
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "provenance": {"model_predictions": "events, confidence, masks", "calculated_statistics": "areas, counts, distributions, priority",
                       "human_verified": "review status 'confirmed' only", "ai_generated_narrative": "narrative field (optional)"},
    }


def build_comparison_data(db: Session, a: m.Analysis, b: m.Analysis) -> dict:
    cmp_ = queries.compare_analyses(db, a, b)
    return {"project": {"id": a.project_id, "name": db.get(m.Project, a.project_id).name}, "comparison": cmp_,
            "limitations": LIMITATIONS, "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "provenance": {"calculated_statistics": "all numbers are computed from stored analyses", "ai_generated_narrative": "optional"}}


def create_report(db: Session, kind: str, analysis: m.Analysis, other: m.Analysis | None = None, narrative: str | None = None,
                  narrative_provider: str | None = None) -> m.Report:
    if kind == "comparison":
        assert other is not None
        data = build_comparison_data(db, analysis, other)
        title = f"Comparison: {analysis.before_obs.acquisition_date}→{analysis.after_obs.acquisition_date} vs {other.before_obs.acquisition_date}→{other.after_obs.acquisition_date}"
    else:
        data = build_analysis_data(db, analysis)
        title = f"Analysis report {analysis.id}: {analysis.before_obs.acquisition_date} → {analysis.after_obs.acquisition_date}"
    r = m.Report(project_id=analysis.project_id, analysis_id=analysis.id, kind=kind, title=title, data=data,
                 narrative=narrative, narrative_provider=narrative_provider)
    db.add(r); db.flush()
    from app.reporting.pdf import render_pdf
    out = get_settings().reports_dir / f"{r.id}.pdf"
    render_pdf(r, out)
    r.pdf_path = str(out)
    db.commit()
    return r
