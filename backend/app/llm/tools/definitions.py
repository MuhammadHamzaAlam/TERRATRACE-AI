from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import Point, shape

from app.database import models as m
from app.llm.tools.registry import ToolContext, ToolError, ToolResult, clean_text, tool
from app.services import queries

Direction = Literal["north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest"]
ReviewStatus = Literal["pending", "confirmed", "rejected", "needs_investigation"]
MAX_ROWS = 50


class NoArgs(BaseModel):
    pass


class AnalysisArg(BaseModel):
    analysis_id: str | None = Field(default=None, description="Analysis id (defaults to the active analysis)")


# ---------------- project tools ----------------
@tool("list_projects", "List monitoring projects (id, name, counts).", NoArgs)
def list_projects(ctx, a):
    rows = ctx.db.query(m.Project).order_by(m.Project.created_at.desc()).limit(MAX_ROWS).all()
    data = [{"project_id": p.id, "name": clean_text(p.name), "active": p.id == ctx.project_id} for p in rows]
    return ToolResult(data, f"Listed {len(data)} projects")


@tool("get_project_details", "Details of the active project.", NoArgs)
def get_project_details(ctx, a):
    p = ctx.project()
    n_obs = ctx.db.query(m.Observation).filter_by(project_id=p.id).count()
    n_an = ctx.db.query(m.Analysis).filter_by(project_id=p.id).count()
    return ToolResult({"project_id": p.id, "name": clean_text(p.name), "description": clean_text(p.description, 600),
                       "observations": n_obs, "analyses": n_an, "created_at": p.created_at.isoformat()},
                      f"Retrieved project {p.id}")


@tool("get_project_observations", "List observations (acquisition dates, source, georeferencing) of the active project.", NoArgs)
def get_project_observations(ctx, a):
    rows = ctx.db.query(m.Observation).filter_by(project_id=ctx.project_id).order_by(m.Observation.acquisition_date).all()
    data = [{"observation_id": o.id, "label": clean_text(o.label, 100), "date": o.acquisition_date.isoformat(), "source": o.source,
             "georeferenced": o.georeferenced, "size": [o.width, o.height], "pixel_size_m": o.pixel_size_m} for o in rows]
    return ToolResult(data, f"Retrieved {len(data)} observations")


# ---------------- analysis tools ----------------
@tool("list_analyses", "List analyses in the active project with status, dates and event counts.", NoArgs)
def list_analyses(ctx, a):
    rows = ctx.db.query(m.Analysis).filter_by(project_id=ctx.project_id).order_by(m.Analysis.created_at.desc()).limit(MAX_ROWS).all()
    data = [{"analysis_id": x.id, "status": x.status, "before_date": x.before_obs.acquisition_date.isoformat(),
             "after_date": x.after_obs.acquisition_date.isoformat(), "n_events": (x.metrics or {}).get("n_events")} for x in rows]
    return ToolResult(data, f"Listed {len(data)} analyses")


@tool("get_analysis_summary", "Summary statistics of one analysis (events, changed area/percent, review counts, confidence distribution).", AnalysisArg)
def get_analysis_summary(ctx, a):
    an = ctx.analysis(a.analysis_id)
    return ToolResult(queries.analysis_summary(ctx.db, an), f"Retrieved summary of Analysis {an.id}",
                      [{"type": "navigate_analysis", "analysis_id": an.id}])


class CompareArgs(BaseModel):
    analysis_a: str = Field(description="Reference (earlier) analysis id")
    analysis_b: str = Field(description="Comparison (later) analysis id")


@tool("compare_analyses", "Compare two analyses: event/area deltas, new, persisting and no-longer-detected events.", CompareArgs)
def compare_analyses(ctx, a):
    A, B = ctx.analysis(a.analysis_a), ctx.analysis(a.analysis_b)
    r = queries.compare_analyses(ctx.db, A, B)
    return ToolResult(r, f"Compared Analysis {A.id} ({A.after_obs.acquisition_date}) with {B.id} ({B.after_obs.acquisition_date})",
                      [{"type": "show_comparison", "analysis_a": A.id, "analysis_b": B.id}])


@tool("get_analysis_metrics", "Model, alignment and domain-compatibility metadata of an analysis, plus LEVIR-CD test metrics if validated.", AnalysisArg)
def get_analysis_metrics(ctx, a):
    an = ctx.analysis(a.analysis_id)
    mv = ctx.db.get(m.ModelVersion, an.model_version_id) if an.model_version_id else None
    return ToolResult({"analysis_id": an.id, "model_validated_on_levir_test": bool(mv and mv.validated),
                       "levir_test_metrics": ((mv.metrics or {}).get("test") if mv else None) or "Model evaluation pending — no validated checkpoint available.",
                       "alignment": an.alignment, "domain_compatibility": an.compatibility, "run_metrics": an.metrics},
                      f"Retrieved metrics for Analysis {an.id}")


# ---------------- event tools ----------------
class QueryEventsArgs(AnalysisArg):
    confidence_min: float | None = Field(default=None, ge=0, le=1, description="Minimum model confidence (0-1)")
    confidence_max: float | None = Field(default=None, ge=0, le=1)
    review_status: ReviewStatus | None = None
    cluster_id: str | None = Field(default=None, pattern=r"^CL-\d{3}$", description="e.g. CL-003")
    min_priority: float | None = Field(default=None, ge=0, le=100)
    direction: Direction | None = Field(default=None, description="Geographic half/quadrant of the analysed area; requires georeferenced data")
    temporal_status: Literal["new", "recurring"] | None = None
    sort_by: Literal["priority", "confidence", "area"] = "priority"
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


def _direction_bbox(an: m.Analysis, direction: str) -> list[float]:
    if not an.before_obs.georeferenced or not an.before_obs.bounds_wgs84:
        raise ToolError("Directional filtering is unavailable: this analysis is not georeferenced (image-relative coordinates only).")
    x0, y0, x1, y1 = an.before_obs.bounds_wgs84
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    bx0, bx1 = (mx, x1) if "east" in direction else (x0, mx) if "west" in direction else (x0, x1)
    by0, by1 = (my, y1) if "north" in direction else (y0, my) if "south" in direction else (y0, y1)
    return [bx0, by0, bx1, by1]


def _events(ctx, a: QueryEventsArgs, label: str):
    an = ctx.analysis(a.analysis_id)
    bbox = _direction_bbox(an, a.direction) if a.direction else None
    rows, total = queries.query_events(ctx.db, ctx.project_id, an.id, confidence_min=a.confidence_min, confidence_max=a.confidence_max,
                                       review_status=a.review_status, cluster=a.cluster_id, priority_min=a.min_priority,
                                       temporal_status=a.temporal_status, sort=a.sort_by, limit=a.limit, bbox_wgs84=bbox)
    evs = [queries.event_dict(e) for e in rows]
    filters = {k: v for k, v in {"confidence_min": a.confidence_min, "confidence_max": a.confidence_max, "review_status": a.review_status,
                                 "cluster": a.cluster_id, "min_priority": a.min_priority, "direction": a.direction,
                                 "temporal_status": a.temporal_status}.items() if v is not None}
    data = {"analysis_id": an.id, "total_matching": total, "returned": len(evs), "filters": filters, "events": evs}
    return ToolResult(data, f"Retrieved {total} candidate events from Analysis {an.id}" + (f" ({label})" if label else ""),
                      [{"type": "filter_events", "analysis_id": an.id, "event_ids": [e["event_id"] for e in evs], "filters": filters}])


@tool("query_events", "Query candidate change events with filters (confidence, review status, cluster, priority, direction). Returns real event ids.", QueryEventsArgs)
def query_events(ctx, a): return _events(ctx, a, "")


class HighConfArgs(AnalysisArg):
    threshold: float = Field(default=0.85, ge=0, le=1)
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


@tool("get_high_confidence_events", "Events with model confidence at or above a threshold (default 0.85).", HighConfArgs)
def get_high_confidence_events(ctx, a):
    return _events(ctx, QueryEventsArgs(analysis_id=a.analysis_id, confidence_min=a.threshold, sort_by="confidence", limit=a.limit), f"confidence ≥ {a.threshold}")


@tool("get_pending_review_events", "Events awaiting human review.", AnalysisArg)
def get_pending_review_events(ctx, a):
    r = _events(ctx, QueryEventsArgs(analysis_id=a.analysis_id, review_status="pending", limit=MAX_ROWS), "pending review")
    r.actions.append({"type": "show_pending_review", "analysis_id": r.data["analysis_id"]})
    return r


class EventArg(AnalysisArg):
    event_id: str = Field(pattern=r"^EVT-\d{3,}$", description="e.g. EVT-001")


def _event(ctx, a: EventArg) -> m.Event:
    an = ctx.analysis(a.analysis_id)
    e = ctx.db.get(m.Event, f"{an.id}:{a.event_id}")
    if not e or e.project_id != ctx.project_id: raise ToolError(f"Event {a.event_id} not found in Analysis {an.id}")
    return e


@tool("get_event_details", "Full record of one event: geometry, confidence, priority factors, cluster, review state, temporal track.", EventArg)
def get_event_details(ctx, a):
    e = _event(ctx, a)
    d = queries.event_dict(e, detail=True)
    d.pop("geometry_geo", None)  # large; not needed for explanation
    d["review_notes"] = [{"status": h.new_status, "reviewer": clean_text(h.reviewer, 60), "notes": clean_text(h.notes, 300), "at": h.created_at.isoformat()} for h in e.history]
    return ToolResult(d, f"Retrieved event {e.label} from Analysis {e.analysis_id}",
                      [{"type": "open_event", "event_uid": e.id, "event_id": e.label, "analysis_id": e.analysis_id}])


class ClusterArg(AnalysisArg):
    cluster_id: str = Field(pattern=r"^CL-\d{3}$")


@tool("get_events_by_cluster", "Events belonging to one spatial cluster.", ClusterArg)
def get_events_by_cluster(ctx, a):
    r = _events(ctx, QueryEventsArgs(analysis_id=a.analysis_id, cluster_id=a.cluster_id, limit=MAX_ROWS), a.cluster_id)
    r.actions.append({"type": "select_cluster", "analysis_id": r.data["analysis_id"], "cluster_id": a.cluster_id})
    return r


# ---------------- geospatial tools ----------------
@tool("get_cluster_statistics", "Per-cluster statistics (event count, area, centroid, mean confidence, priority).", AnalysisArg)
def get_cluster_statistics(ctx, a):
    an = ctx.analysis(a.analysis_id)
    cs = ctx.db.query(m.Cluster).filter_by(analysis_id=an.id).order_by(m.Cluster.label).all()
    data = [{k: v for k, v in queries.cluster_dict(c).items() if k != "boundary_geo"} for c in cs]
    top = max(data, key=lambda c: c["event_count"])["cluster_id"] if data else None
    return ToolResult({"analysis_id": an.id, "clusters": data, "cluster_with_most_events": top,
                       "unclustered_events": ctx.db.query(m.Event).filter_by(analysis_id=an.id, cluster_id=None).count()},
                      f"Retrieved {len(data)} clusters from Analysis {an.id}")


class AOIArgs(AnalysisArg):
    aoi_id: str | None = Field(default=None, description="Saved AOI id")
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4, description="minLon,minLat,maxLon,maxLat")
    direction: Direction | None = None


@tool("query_events_in_aoi", "Events inside a saved AOI, a lon/lat bounding box, or a compass half of the analysed area (georeferenced data only).", AOIArgs)
def query_events_in_aoi(ctx, a):
    an = ctx.analysis(a.analysis_id)
    if not an.before_obs.georeferenced:
        raise ToolError("Spatial/AOI queries are unavailable: this analysis is not georeferenced.")
    evs = ctx.db.query(m.Event).filter(m.Event.analysis_id == an.id, m.Event.centroid_geo.isnot(None)).all()
    if a.aoi_id:
        aoi = ctx.db.get(m.AOI, a.aoi_id)
        if not aoi or aoi.project_id != ctx.project_id: raise ToolError("AOI not found in the active project")
        g = shape(aoi.geometry); evs = [e for e in evs if g.contains(Point(*e.centroid_geo))]; where = f"AOI {aoi.name}"
    elif a.bbox:
        x0, y0, x1, y1 = a.bbox; evs = [e for e in evs if x0 <= e.centroid_geo[0] <= x1 and y0 <= e.centroid_geo[1] <= y1]; where = "bbox"
    elif a.direction:
        x0, y0, x1, y1 = _direction_bbox(an, a.direction); evs = [e for e in evs if x0 <= e.centroid_geo[0] <= x1 and y0 <= e.centroid_geo[1] <= y1]; where = f"{a.direction} part"
    else:
        raise ToolError("Provide aoi_id, bbox or direction")
    evs.sort(key=lambda e: -e.priority_score)
    data = {"analysis_id": an.id, "region": where, "n_events": len(evs), "total_area_m2": sum(e.area_m2 or 0 for e in evs),
            "events": [queries.event_dict(e) for e in evs[:MAX_ROWS]]}
    return ToolResult(data, f"Retrieved {len(evs)} events in {where} from Analysis {an.id}",
                      [{"type": "filter_events", "analysis_id": an.id, "event_ids": [e.label for e in evs[:MAX_ROWS]], "filters": {"region": where}}])


@tool("get_spatial_distribution", "Event counts in a 2x2 grid (NW/NE/SW/SE) of the analysed area, with the highest-concentration quadrant (georeferenced) or image quadrants (pixel).", AnalysisArg)
def get_spatial_distribution(ctx, a):
    an = ctx.analysis(a.analysis_id)
    evs = ctx.db.query(m.Event).filter_by(analysis_id=an.id).all()
    geo = an.before_obs.georeferenced
    if geo:
        x0, y0, x1, y1 = an.before_obs.bounds_wgs84; mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        key = lambda e: ("N" if e.centroid_geo[1] >= my else "S") + ("E" if e.centroid_geo[0] >= mx else "W")
    else:
        w, h = an.before_obs.width, an.before_obs.height
        key = lambda e: ("N" if e.centroid_px[1] < h / 2 else "S") + ("E" if e.centroid_px[0] >= w / 2 else "W")
    grid = {"NW": 0, "NE": 0, "SW": 0, "SE": 0}
    for e in evs: grid[key(e)] += 1
    best = max(grid, key=grid.get) if evs else None
    return ToolResult({"analysis_id": an.id, "coordinate_system": "geographic (north-up WGS84)" if geo else "image-relative (top of image = 'N'; not geographic)",
                       "quadrant_counts": grid, "highest_concentration": best}, f"Computed spatial distribution for Analysis {an.id}")


@tool("get_geographic_area_statistics", "Total and mean detected area (m²) and share of the image; geodesic areas when georeferenced.", AnalysisArg)
def get_geographic_area_statistics(ctx, a):
    an = ctx.analysis(a.analysis_id); mt = an.metrics or {}
    evs = ctx.db.query(m.Event).filter_by(analysis_id=an.id).all()
    return ToolResult({"analysis_id": an.id, "georeferenced": mt.get("georeferenced", False), "n_events": len(evs),
                       "total_area_m2": mt.get("changed_area_m2"), "mean_event_area_m2": (sum(e.area_m2 for e in evs) / len(evs)) if evs and mt.get("georeferenced") else None,
                       "total_area_px": mt.get("changed_pixels"), "changed_pct_of_image": mt.get("changed_pct"),
                       "largest_events": [queries.event_dict(e) for e in sorted(evs, key=lambda e: -e.area_px)[:5]]},
                      f"Retrieved area statistics for Analysis {an.id}")


# ---------------- temporal tools ----------------
class PeriodArgs(BaseModel):
    period_a_start: date
    period_a_end: date
    period_b_start: date
    period_b_end: date


def _find_analysis_by_after_date(ctx, start: date, end: date) -> m.Analysis | None:
    rows = (ctx.db.query(m.Analysis).join(m.Observation, m.Analysis.after_obs_id == m.Observation.id)
            .filter(m.Analysis.project_id == ctx.project_id, m.Analysis.status == "completed",
                    m.Observation.acquisition_date >= start, m.Observation.acquisition_date <= end)
            .order_by(m.Observation.acquisition_date.desc()).all())
    return rows[0] if rows else None


@tool("compare_observation_periods", "Compare detections between two date periods; selects the latest completed analysis whose 'after' observation falls in each period.", PeriodArgs)
def compare_observation_periods(ctx, a):
    A, B = _find_analysis_by_after_date(ctx, a.period_a_start, a.period_a_end), _find_analysis_by_after_date(ctx, a.period_b_start, a.period_b_end)
    if not A or not B:
        missing = "period A" if not A else "period B"
        raise ToolError(f"No completed analysis ends in {missing}; historical data for the requested comparison does not exist.")
    r = queries.compare_analyses(ctx.db, A, B)
    return ToolResult(r, f"Compared observations from {A.after_obs.acquisition_date} and {B.after_obs.acquisition_date}",
                      [{"type": "show_comparison", "analysis_a": A.id, "analysis_b": B.id}])


@tool("get_recurring_events", "Events whose location was detected in more than one analysis (recurring candidate regions).", AnalysisArg)
def get_recurring_events(ctx, a):
    r = _events(ctx, QueryEventsArgs(analysis_id=a.analysis_id, temporal_status="recurring", limit=MAX_ROWS), "recurring")
    return r


@tool("get_newly_detected_events", "Events at locations not detected in any earlier analysis.", AnalysisArg)
def get_newly_detected_events(ctx, a):
    return _events(ctx, QueryEventsArgs(analysis_id=a.analysis_id, temporal_status="new", limit=MAX_ROWS), "new")


@tool("get_event_history", "Observation history of an event's location across analyses (track), with confidences and review states.", EventArg)
def get_event_history(ctx, a):
    e = _event(ctx, a)
    if not e.track_id: return ToolResult({"event_id": e.label, "history": []}, f"No track for {e.label}")
    sib = ctx.db.query(m.Event).filter(m.Event.track_id == e.track_id, m.Event.project_id == ctx.project_id).order_by(m.Event.after_date).all()
    return ToolResult({"event_id": e.label, "track_id": e.track_id,
                       "history": [{"event_id": s.label, "analysis_id": s.analysis_id, "after_date": s.after_date.isoformat(), "confidence": round(s.conf_mean, 4),
                                    "review_status": s.review_status} for s in sib]}, f"Retrieved history of {e.label} ({len(sib)} observations)")


# ---------------- review tools (read-only) ----------------
@tool("get_review_status", "Review status counts for an analysis (pending/confirmed/rejected/needs_investigation).", AnalysisArg)
def get_review_status(ctx, a):
    an = ctx.analysis(a.analysis_id)
    return ToolResult(queries.analysis_summary(ctx.db, an)["review_status_counts"] | {"analysis_id": an.id}, f"Retrieved review status of Analysis {an.id}")


class HistArgs(AnalysisArg):
    event_id: str | None = Field(default=None, pattern=r"^EVT-\d{3,}$")
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


@tool("get_review_history", "Audit history of review decisions for an event or recent decisions in the analysis. Read-only.", HistArgs)
def get_review_history(ctx, a):
    an = ctx.analysis(a.analysis_id)
    q = ctx.db.query(m.EventHistory, m.Event).join(m.Event, m.Event.id == m.EventHistory.event_id).filter(m.Event.analysis_id == an.id)
    if a.event_id: q = q.filter(m.Event.label == a.event_id)
    rows = q.order_by(m.EventHistory.id.desc()).limit(a.limit).all()
    return ToolResult([{"event_id": e.label, "from": h.previous_status, "to": h.new_status, "reviewer": clean_text(h.reviewer, 60),
                        "notes": clean_text(h.notes, 300), "at": h.created_at.isoformat()} for h, e in rows], f"Retrieved {len(rows)} review records")


# ---------------- report tools ----------------
@tool("generate_analysis_report", "Create a deterministic report (PDF + data) for an analysis. Creates a new report record.", AnalysisArg, read_only=False)
def generate_analysis_report(ctx, a):
    from app.reporting import service
    an = ctx.analysis(a.analysis_id)
    if an.status != "completed": raise ToolError(f"Analysis {an.id} is {an.status}, not completed")
    r = service.create_report(ctx.db, "analysis", an)
    return ToolResult({"report_id": r.id, "title": r.title, "analysis_id": an.id, "pdf": f"/api/reports/{r.id}/pdf"}, f"Generated report {r.id} for Analysis {an.id}",
                      [{"type": "open_report", "report_id": r.id}])


@tool("generate_comparison_report", "Create a deterministic comparison report between two analyses.", CompareArgs, read_only=False)
def generate_comparison_report(ctx, a):
    from app.reporting import service
    A, B = ctx.analysis(a.analysis_a), ctx.analysis(a.analysis_b)
    if A.status != "completed" or B.status != "completed": raise ToolError("Both analyses must be completed")
    r = service.create_report(ctx.db, "comparison", A, B)
    return ToolResult({"report_id": r.id, "title": r.title, "pdf": f"/api/reports/{r.id}/pdf"}, f"Generated comparison report {r.id}", [{"type": "open_report", "report_id": r.id}])


class ReportArg(BaseModel):
    report_id: str = Field(pattern=r"^RPT-[A-Z0-9]{8}$")


@tool("get_report_details", "Structured data of an existing report in the active project.", ReportArg)
def get_report_details(ctx, a):
    r = ctx.db.get(m.Report, a.report_id)
    if not r or r.project_id != ctx.project_id: raise ToolError("Report not found in the active project")
    return ToolResult({"report_id": r.id, "title": r.title, "kind": r.kind, "created_at": r.created_at.isoformat(),
                       "statistics": r.data.get("calculated_statistics") or r.data.get("comparison", {}).get("delta"),
                       "has_ai_narrative": bool(r.narrative)}, f"Retrieved report {r.id}", [{"type": "open_report", "report_id": r.id}])
