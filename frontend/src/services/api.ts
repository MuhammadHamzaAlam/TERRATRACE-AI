import type {
  Analysis, ClusterRec, Comparison, Conversation, EventRec, HistoryRec, ModelStatus, Observation, Overview, Project, ProviderInfo,
  ReportRec, ReviewStatus, Summary, Timeline,
} from "../types/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";
export const reviewer = { get: () => localStorage.getItem("tt_reviewer") ?? "local-analyst", set: (v: string) => localStorage.setItem("tt_reviewer", v) };

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Reviewer": reviewer.get(), ...(init.headers as Record<string, string> | undefined) };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try { res = await fetch(`${BASE}${path}`, { ...init, headers }); }
  catch { throw new ApiError(0, "Cannot reach the TerraTrace backend. Is it running?"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
const post = <T,>(p: string, body?: unknown) => req<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const qs = (o: Record<string, unknown>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString(); return s ? `?${s}` : "";
};

export const api = {
  health: () => req<{ status: string }>("/health"),
  overview: () => req<Overview>("/overview"),
  projects: {
    list: () => req<Project[]>("/projects"),
    get: (id: string) => req<Project>(`/projects/${id}`),
    create: (b: { name: string; description: string }) => post<Project>("/projects", b),
    update: (id: string, b: Partial<{ name: string; description: string }>) => req<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
    remove: (id: string, confirmName: string) => req<{ deleted: string }>(`/projects/${id}${qs({ confirm_name: confirmName })}`, { method: "DELETE" }),
    timeline: (id: string) => req<Timeline>(`/projects/${id}/timeline`),
    observations: (id: string) => req<Observation[]>(`/projects/${id}/observations`),
    uploadObservation: (id: string, file: File, date: string, label: string) => {
      const f = new FormData(); f.append("file", file); f.append("acquisition_date", date); f.append("label", label);
      return req<Observation>(`/projects/${id}/observations`, { method: "POST", body: f });
    },
    aois: (id: string) => req<{ id: string; name: string; geometry: GeoJSON.Geometry }[]>(`/projects/${id}/aois`),
    uploadAoi: (id: string, file: File) => { const f = new FormData(); f.append("file", file); return req<unknown[]>(`/projects/${id}/aois/upload`, { method: "POST", body: f }); },
  },
  analyses: {
    list: (pid: string) => req<Analysis[]>(`/projects/${pid}/analyses`),
    get: (id: string) => req<Analysis>(`/analyses/${id}`),
    create: (pid: string, b: Record<string, unknown>) => post<Analysis & { job_id: string | null }>(`/projects/${pid}/analyses`, b),
    summary: (id: string) => req<Summary>(`/analyses/${id}/summary`),
    compare: (a: string, b: string) => req<Comparison>(`/analyses/${a}/compare/${b}`),
    imageUrl: (id: string, kind: "before" | "after" | "mask" | "overlay") => `${BASE}/analyses/${id}/image/${kind}`,
    exportUrl: (id: string, kind: "csv" | "geojson") => `${BASE}/analyses/${id}/export/${kind}`,
    geojson: (id: string) => req<GeoJSON.FeatureCollection>(`/analyses/${id}/geojson`),
  },
  events: {
    list: (pid: string, f: Record<string, unknown>) => req<{ total: number; events: EventRec[] }>(`/projects/${pid}/events${qs(f)}`),
    get: (uid: string) => req<EventRec>(`/events/${encodeURIComponent(uid)}`),
    cropUrl: (uid: string, kind: "before" | "after" | "mask") => `${BASE}/events/${encodeURIComponent(uid)}/crop/${kind}`,
    review: (uid: string, status: ReviewStatus, notes: string) => post<{ event: EventRec }>(`/events/${encodeURIComponent(uid)}/review`, { status, notes }),
    bulk: (pid: string, ids: string[], status: ReviewStatus, notes: string) => post<{ updated: number }>(`/projects/${pid}/events/bulk-review`, { event_ids: ids, status, notes, confirm: true }),
    history: (pid: string) => req<HistoryRec[]>(`/projects/${pid}/review-history`),
    clusters: (pid: string, analysisId?: string) => req<ClusterRec[]>(`/projects/${pid}/clusters${qs({ analysis_id: analysisId })}`),
  },
  reports: {
    list: (pid: string) => req<ReportRec[]>(`/projects/${pid}/reports`),
    get: (id: string) => req<ReportRec & { data: Record<string, unknown> }>(`/reports/${id}`),
    create: (pid: string, b: Record<string, unknown>) => post<ReportRec>(`/projects/${pid}/reports`, b),
    pdfUrl: (id: string) => `${BASE}/reports/${id}/pdf`,
  },
  model: {
    status: () => req<ModelStatus>("/model/status"),
    metrics: () => req<{ test_metrics: null | Record<string, unknown>; training_history: Record<string, number>[]; prediction_visualizations: string[]; message: string | null }>("/model/metrics"),
    dataset: () => req<{ available: boolean; root: string; splits: Record<string, { n_pairs: number; changed_pixel_fraction_sampled?: number; problems: string[] }>; source: string; usage_note: string }>("/model/dataset"),
    architecture: () => req<Record<string, string | number>>("/model/architecture"),
    training: () => req<{ id: string; status: string; history: Record<string, number>[]; message: string; config: Record<string, number> }[]>("/model/training"),
    startTraining: (b: Record<string, unknown>) => post<{ training_run_id: string }>("/model/training", { ...b, confirm: true }),
    evaluate: () => post<{ job_id: string }>("/model/evaluate"),
    vizUrl: (n: string) => `${BASE}/model/visualization/${encodeURIComponent(n)}`,
  },
  satellite: {
    status: () => req<{ search_available: boolean; download_available: boolean; message: string | null }>("/satellite/status"),
    search: (b: Record<string, unknown>) => post<{ scenes: { id: string; name: string; acquisition_date: string; cloud_cover: number | null; tile_id: string; size_mb: number; preview_url: string }[] }>("/satellite/search", b),
    import: (pid: string, b: Record<string, unknown>) => post<{ observation_id: string; job_id: string }>(`/satellite/projects/${pid}/import`, b),
  },
  jobs: { get: (id: string) => req<{ id: string; status: string; progress: number; message: string }>(`/jobs/${id}`) },
  settings: {
    get: () => req<{ llm: Overview["system"]["llm"]; satellite: Overview["system"]["satellite"]; limits: { max_upload_mb: number } }>("/settings"),
    putLlm: (b: Record<string, string>) => req<Overview["system"]["llm"]>("/settings/llm", { method: "PUT", body: JSON.stringify(b) }),
  },
  assistant: {
    providers: () => req<{ default: string; providers: Record<string, ProviderInfo> }>("/assistant/providers"),
    create: (project_id: string, provider?: string, model?: string) => post<Conversation>("/assistant/conversations", { project_id, provider, model }),
    list: (pid: string) => req<Conversation[]>(`/assistant/conversations${qs({ project_id: pid })}`),
    get: (id: string) => req<Conversation>(`/assistant/conversations/${id}`),
    remove: (id: string) => req<unknown>(`/assistant/conversations/${id}`, { method: "DELETE" }),
    offlineSummary: (analysisId: string) => req<{ text: string; generated_by: string }>(`/assistant/offline-summary/${analysisId}`),
    messageUrl: (id: string) => `${BASE}/assistant/conversations/${id}/messages`,
  },
};
export type { Summary };
