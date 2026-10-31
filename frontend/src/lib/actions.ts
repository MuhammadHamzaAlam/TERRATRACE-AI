import type { ReviewStatus, UiAction } from "../types/api";

/** The assistant's structured UI actions are untrusted input: validate against a strict allowlist and schema before applying. */
const ID = /^EVT-\d{3,}$/;
const CL = /^CL-\d{3}$/;
const isStr = (v: unknown): v is string => typeof v === "string" && v.length > 0 && v.length < 80;
const STATUSES: ReviewStatus[] = ["pending", "confirmed", "rejected", "needs_investigation"];

export function validateAction(a: unknown): UiAction | null {
  if (!a || typeof a !== "object") return null;
  const o = a as Record<string, unknown>;
  switch (o.type) {
    case "filter_events": {
      if (!isStr(o.analysis_id) || !Array.isArray(o.event_ids) || !o.event_ids.every((i) => typeof i === "string" && ID.test(i))) return null;
      const f = (o.filters && typeof o.filters === "object" ? o.filters : {}) as Record<string, unknown>;
      const clean: Record<string, unknown> = {};
      if (typeof f.confidence_min === "number" && f.confidence_min >= 0 && f.confidence_min <= 1) clean.confidence_min = f.confidence_min;
      if (typeof f.review_status === "string" && STATUSES.includes(f.review_status as ReviewStatus)) clean.review_status = f.review_status;
      if (typeof f.cluster === "string" && CL.test(f.cluster)) clean.cluster = f.cluster;
      if (typeof f.direction === "string") clean.direction = f.direction.slice(0, 20);
      if (typeof f.temporal_status === "string") clean.temporal_status = f.temporal_status.slice(0, 20);
      return { type: "filter_events", analysis_id: o.analysis_id, event_ids: o.event_ids as string[], filters: clean };
    }
    case "open_event":
      return isStr(o.event_uid) && typeof o.event_id === "string" && ID.test(o.event_id) && isStr(o.analysis_id)
        ? { type: "open_event", event_uid: o.event_uid, event_id: o.event_id, analysis_id: o.analysis_id } : null;
    case "select_cluster":
      return isStr(o.analysis_id) && typeof o.cluster_id === "string" && CL.test(o.cluster_id) ? { type: "select_cluster", analysis_id: o.analysis_id, cluster_id: o.cluster_id } : null;
    case "show_comparison":
      return isStr(o.analysis_a) && isStr(o.analysis_b) ? { type: "show_comparison", analysis_a: o.analysis_a, analysis_b: o.analysis_b } : null;
    case "navigate_analysis":
      return isStr(o.analysis_id) ? { type: "navigate_analysis", analysis_id: o.analysis_id } : null;
    case "open_report":
      return typeof o.report_id === "string" && /^RPT-[A-Z0-9]{8}$/.test(o.report_id) ? { type: "open_report", report_id: o.report_id } : null;
    case "show_pending_review":
      return isStr(o.analysis_id) ? { type: "show_pending_review", analysis_id: o.analysis_id } : null;
    case "highlight_events":
      return Array.isArray(o.event_ids) && o.event_ids.every((i) => typeof i === "string" && ID.test(i)) ? { type: "highlight_events", event_ids: o.event_ids as string[] } : null;
    default:
      return null; // unknown action types (including anything resembling code execution) are dropped
  }
}
