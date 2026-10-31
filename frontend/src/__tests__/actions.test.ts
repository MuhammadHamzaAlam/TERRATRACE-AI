import { describe, expect, it } from "vitest";
import { validateAction } from "../lib/actions";

describe("validateAction (assistant UI-action allowlist)", () => {
  it("accepts well-formed filter_events and strips unknown filter keys", () => {
    const a = validateAction({ type: "filter_events", analysis_id: "A-1", event_ids: ["EVT-001", "EVT-004"], filters: { confidence_min: 0.85, evil: "<script>", review_status: "pending" } });
    expect(a).toEqual({ type: "filter_events", analysis_id: "A-1", event_ids: ["EVT-001", "EVT-004"], filters: { confidence_min: 0.85, review_status: "pending" } });
  });
  it("rejects unknown / code-execution style actions", () => {
    expect(validateAction({ type: "run_js", code: "alert(1)" })).toBeNull();
    expect(validateAction({ type: "navigate", url: "javascript:alert(1)" })).toBeNull();
    expect(validateAction(null)).toBeNull();
    expect(validateAction("open_event")).toBeNull();
  });
  it("rejects malformed ids and out-of-range values", () => {
    expect(validateAction({ type: "filter_events", analysis_id: "A", event_ids: ["EVT-1; DROP"], filters: {} })).toBeNull();
    expect(validateAction({ type: "open_event", event_uid: "x", event_id: "not-an-id", analysis_id: "A" })).toBeNull();
    expect(validateAction({ type: "select_cluster", analysis_id: "A", cluster_id: "CL-1" })).toBeNull();
    expect(validateAction({ type: "open_report", report_id: "../../etc/passwd" })).toBeNull();
    const f = validateAction({ type: "filter_events", analysis_id: "A", event_ids: [], filters: { confidence_min: 7 } });
    expect(f && "filters" in f && f.filters).toEqual({});
  });
  it("accepts the remaining allowlisted action types", () => {
    expect(validateAction({ type: "show_comparison", analysis_a: "A-1", analysis_b: "A-2" })).not.toBeNull();
    expect(validateAction({ type: "navigate_analysis", analysis_id: "A-1" })).not.toBeNull();
    expect(validateAction({ type: "open_report", report_id: "RPT-ABCD1234" })).not.toBeNull();
    expect(validateAction({ type: "show_pending_review", analysis_id: "A-1" })).not.toBeNull();
    expect(validateAction({ type: "highlight_events", event_ids: ["EVT-002"] })).not.toBeNull();
    expect(validateAction({ type: "select_cluster", analysis_id: "A-1", cluster_id: "CL-003" })).not.toBeNull();
  });
});
