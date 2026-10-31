import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";
import type { Analysis, Project, UiAction } from "../types/api";
import { validateAction } from "../lib/actions";

export interface EventFilter { ids?: string[]; confidence_min?: number; review_status?: string; cluster?: string; temporal_status?: string; direction?: string }
interface State {
  projects: Project[]; projectId: string | null; project: Project | null; setProjectId: (id: string | null) => void; reloadProjects: () => void;
  analyses: Analysis[]; analysisId: string | null; analysis: Analysis | null; setAnalysisId: (id: string | null) => void; reloadAnalyses: () => void;
  filter: EventFilter; setFilter: (f: EventFilter) => void; selectedEventUid: string | null; selectEvent: (uid: string | null) => void;
  selectedCluster: string | null; selectCluster: (c: string | null) => void; highlightIds: string[];
  comparison: { a: string; b: string } | null; backendError: string | null;
  applyAction: (a: unknown) => boolean;
}
const Ctx = createContext<State | null>(null);
export const useApp = () => { const c = useContext(Ctx); if (!c) throw new Error("AppState missing"); return c; };
const ls = { get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k: string, v: string | null) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch { /* ignore */ } } };

export function AppStateProvider({ children }: { children: ReactNode }) {
  const nav = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setPid] = useState<string | null>(ls.get("tt_project"));
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [analysisId, setAid] = useState<string | null>(ls.get("tt_analysis"));
  const [filter, setFilter] = useState<EventFilter>({});
  const [selectedEventUid, selectEvent] = useState<string | null>(null);
  const [selectedCluster, selectCluster] = useState<string | null>(null);
  const [highlightIds, setHighlight] = useState<string[]>([]);
  const [comparison, setComparison] = useState<{ a: string; b: string } | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  const reloadProjects = useCallback(() => {
    api.projects.list().then((p) => { setProjects(p); setBackendError(null); setPid((cur) => (cur && p.some((x) => x.id === cur) ? cur : p[0]?.id ?? null)); })
      .catch((e: Error) => setBackendError(e.message));
  }, []);
  const reloadAnalyses = useCallback(() => {
    if (!projectId) { setAnalyses([]); return; }
    api.analyses.list(projectId).then((a) => { setAnalyses(a); setAid((cur) => (cur && a.some((x) => x.id === cur) ? cur : a.find((x) => x.status === "completed")?.id ?? null)); }).catch(() => setAnalyses([]));
  }, [projectId]);
  useEffect(reloadProjects, [reloadProjects]);
  useEffect(reloadAnalyses, [reloadAnalyses]);
  useEffect(() => { ls.set("tt_project", projectId); }, [projectId]);
  useEffect(() => { ls.set("tt_analysis", analysisId); }, [analysisId]);

  const setProjectId = useCallback((id: string | null) => { setPid(id); setAid(null); setFilter({}); selectEvent(null); selectCluster(null); setHighlight([]); }, []);
  const analysis = analyses.find((a) => a.id === analysisId) ?? null;

  const applyAction = useCallback((raw: unknown) => {
    const a: UiAction | null = validateAction(raw);   // allowlist + schema validation; unknown actions are ignored
    if (!a) return false;
    const aid = "analysis_id" in a ? a.analysis_id : null;
    if (aid && analyses.some((x) => x.id === aid)) setAid(aid);
    const geo = (id: string | null) => analyses.find((x) => x.id === id)?.georeferenced ?? false;
    switch (a.type) {
      case "filter_events": { const { confidence_min, review_status, cluster, temporal_status, direction } = a.filters as EventFilter; setFilter({ ids: a.event_ids, confidence_min, review_status, cluster, temporal_status, direction }); setHighlight(a.event_ids); nav(geo(a.analysis_id) ? "/explorer" : "/workspace"); break; }
      case "open_event": selectEvent(a.event_uid); setHighlight([a.event_id]); nav("/review"); break;
      case "select_cluster": selectCluster(a.cluster_id); nav(geo(a.analysis_id) ? "/explorer" : "/analytics"); break;
      case "show_comparison": setComparison({ a: a.analysis_a, b: a.analysis_b }); nav("/temporal"); break;
      case "navigate_analysis": nav("/workspace"); break;
      case "open_report": nav("/reports"); break;
      case "show_pending_review": setFilter({ review_status: "pending" }); nav("/review"); break;
      case "highlight_events": setHighlight(a.event_ids); break;
    }
    return true;
  }, [analyses, nav]);

  const value = useMemo<State>(() => ({
    projects, projectId, project: projects.find((p) => p.id === projectId) ?? null, setProjectId, reloadProjects, analyses, analysisId, analysis,
    setAnalysisId: setAid, reloadAnalyses, filter, setFilter, selectedEventUid, selectEvent, selectedCluster, selectCluster, highlightIds, comparison, backendError, applyAction,
  }), [projects, projectId, setProjectId, reloadProjects, analyses, analysisId, analysis, reloadAnalyses, filter, selectedEventUid, selectedCluster, highlightIds, comparison, backendError, applyAction]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
