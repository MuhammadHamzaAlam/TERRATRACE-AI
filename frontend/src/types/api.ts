export type ReviewStatus = "pending" | "confirmed" | "rejected" | "needs_investigation";
export const REVIEW_LABELS: Record<ReviewStatus, string> = {
  pending: "Pending review", confirmed: "Confirmed change", rejected: "Rejected detection", needs_investigation: "Needs investigation",
};

export interface Project { id: string; name: string; description: string; created_at: string; counts: { observations: number; analyses: number; events: number; aois: number } }
export interface Observation {
  id: string; project_id: string; label: string; acquisition_date: string; source: string; original_filename: string;
  width: number; height: number; georeferenced: boolean; crs: string | null; bounds_wgs84: number[] | null; pixel_size_m: number | null;
  meta: { domain_compatibility?: { status: string; notes: string[] } };
}
export interface Analysis {
  id: string; project_id: string; status: "pending" | "running" | "completed" | "failed" | "blocked"; progress: number; status_message: string;
  before_observation_id: string; after_observation_id: string; before_date: string; after_date: string; georeferenced: boolean;
  image_size: [number, number]; model_version_id: string | null; config: Record<string, unknown>;
  alignment: { status?: string; notes?: string[]; global_shift_px?: number[] }; compatibility: { status?: string; notes?: string[]; gsd_m?: number | null };
  metrics: { n_events?: number; n_clusters?: number; changed_pct?: number; changed_pixels?: number; changed_area_m2?: number | null; mean_confidence?: number | null; georeferenced?: boolean };
  has_mask: boolean; created_at: string;
}
export interface EventRec {
  event_id: string; uid: string; analysis_id: string; project_id: string; cluster: string | null; area_px: number; area_m2: number | null; area_pct: number;
  confidence: number; priority_score: number; review_status: ReviewStatus; temporal_status: "new" | "recurring"; track_id: string | null;
  centroid_px: number[]; centroid_geo: number[] | null; bbox_px: number[]; before_date: string; after_date: string;
  conf_max?: number; conf_min?: number; geometry_geo?: GeoJSON.Geometry | null;
  priority_factors?: { score: number; factors: Record<string, number>; contributions: Record<string, number>; weights: Record<string, number> };
  history?: HistoryRec[]; track?: { id: string; first_observed: string; last_observed: string; n_observations: number; observations: { event_id: string; uid: string; analysis_id: string; after_date: string; confidence: number; review_status: string }[] };
}
export interface HistoryRec { id: number; previous_status: string; new_status: string; reviewer: string; notes: string; created_at: string; event_id?: string; analysis_id?: string }
export interface ClusterRec { cluster_id: string; uid: string; analysis_id: string; event_count: number; total_area_px: number; total_area_m2: number | null; centroid_geo: number[] | null; boundary_geo: GeoJSON.Geometry | null; mean_confidence: number; priority_score: number; params: Record<string, unknown> }
export interface Summary {
  analysis_id: string; n_events: number; n_clusters: number; changed_pct: number | null; changed_pixels: number | null; changed_area_m2: number | null;
  review_status_counts: Record<ReviewStatus, number>; confidence_distribution: { range: string; count: number }[]; mean_confidence: number | null;
  before_date: string; after_date: string; caveat: string; georeferenced: boolean;
}
export interface Timeline {
  observations: { id: string; label: string; date: string; source: string; georeferenced: boolean }[];
  analyses: { analysis_id: string; before_date: string; after_date: string; n_events: number; n_clusters: number; changed_pct: number | null; changed_area_m2: number | null }[];
  tracks: { total: number; recurring: number; single: number }; note: string;
}
export interface Comparison {
  analysis_a: Summary; analysis_b: Summary; delta: { n_events: number; changed_pct: number | null; changed_area_m2: number | null; n_clusters: number };
  new_in_b: string[]; persisting: string[]; not_detected_in_b: string[]; same_grid: boolean; caveat: string;
}
export interface ReportRec { id: string; project_id: string; analysis_id: string | null; kind: string; title: string; has_narrative: boolean; narrative_provider: string | null; created_at: string; narrative?: string | null }
export interface ModelStatus { status: string; architecture: string; checkpoint_present: boolean; validated: boolean; inference_available: boolean; message: string | null; metrics: null | { f1: number; iou: number; precision: number; recall: number; accuracy: number; n_images: number; confusion_matrix: Record<string, number> } }
export interface Overview {
  counts: Record<string, number>; model: ModelStatus; recent_reports: { id: string; title: string; created_at: string; project_id: string }[];
  recent_activity: { type: string; id: string; project_id: string; status: string; at: string }[];
  system: { database: string; satellite: { search_available: boolean; download_available: boolean; message: string | null }; llm: LLMSummary };
}
export interface LLMSummary { provider: string; ollama: { base_url: string; model: string | null }; grok: { api_key_configured: boolean; model: string | null } }
export interface ProviderInfo { available: boolean; message?: string; code?: string; models: { name: string }[]; selected_model: string | null; version?: string }
export interface Conversation { id: string; project_id: string | null; title: string; provider: string; model: string; created_at: string; messages?: { id: number; role: "user" | "assistant"; content: string; actions: UiAction[] }[] }

export type UiAction =
  | { type: "filter_events"; analysis_id: string; event_ids: string[]; filters: Record<string, unknown> }
  | { type: "open_event"; event_uid: string; event_id: string; analysis_id: string }
  | { type: "select_cluster"; analysis_id: string; cluster_id: string }
  | { type: "show_comparison"; analysis_a: string; analysis_b: string }
  | { type: "navigate_analysis"; analysis_id: string }
  | { type: "open_report"; report_id: string }
  | { type: "show_pending_review"; analysis_id: string }
  | { type: "highlight_events"; event_ids: string[] };
