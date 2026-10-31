import { useMemo, useState } from "react";
import EventInspector from "../features/review/EventInspector";
import { Empty, ErrorBox, Notice, PageHeader, Spinner, StatusBadge } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { area } from "../lib/format";
import { api } from "../services/api";
import { REVIEW_LABELS, type ReviewStatus } from "../types/api";

export default function ReviewCenter() {
  const app = useApp(); const a = app.analysis;
  const [status, setStatus] = useState<string>(app.filter.review_status ?? ""); const [conf, setConf] = useState<string>(""); const [prio, setPrio] = useState(0);
  const [cluster, setCluster] = useState(""); const [sel, setSel] = useState<Set<string>>(new Set()); const [bulkErr, setBulkErr] = useState<string | null>(null);
  const [tab, setTab] = useState<"queue" | "history">("queue");
  const q = useAsync(() => (app.projectId ? api.events.list(app.projectId, { analysis_id: a?.id, review_status: status || app.filter.review_status, priority_min: prio || undefined, cluster: cluster || undefined, limit: 500,
    confidence_min: conf === "high" ? 0.85 : undefined, confidence_max: conf === "low" ? 0.6 : undefined }) : Promise.resolve(null)), [app.projectId, a?.id, status, conf, prio, cluster, app.filter.review_status]);
  const hist = useAsync(() => (app.projectId && tab === "history" ? api.events.history(app.projectId) : Promise.resolve([])), [app.projectId, tab, q.data]);
  const rows = useMemo(() => (q.data?.events ?? []).filter((e) => !app.filter.ids || app.filter.ids.includes(e.event_id)), [q.data, app.filter.ids]);
  const toggle = (u: string) => setSel((s) => { const n = new Set(s); n.has(u) ? n.delete(u) : n.add(u); return n; });
  const bulk = async (s: ReviewStatus) => {
    if (!app.projectId || sel.size === 0) return;
    if (!window.confirm(`Apply "${REVIEW_LABELS[s]}" to ${sel.size} events? Each change is recorded in the audit history under reviewer "${localStorage.getItem("tt_reviewer") ?? "local-analyst"}".`)) return;
    try { await api.events.bulk(app.projectId, [...sel], s, "Bulk review"); setSel(new Set()); q.reload(); } catch (e) { setBulkErr((e as Error).message); }
  };
  if (!app.projectId) return <Empty title="No project selected" />;
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Review center" subtitle="Human verification. Only analysts change review status — the assistant cannot." actions={<div className="flex gap-1" role="tablist"><button role="tab" aria-selected={tab === "queue"} className={tab === "queue" ? "btn-primary" : "btn-ghost"} onClick={() => setTab("queue")}>Queue</button><button role="tab" aria-selected={tab === "history"} className={tab === "history" ? "btn-primary" : "btn-ghost"} onClick={() => setTab("history")}>Audit history</button></div>} />
      {tab === "history" ? (
        <div className="overflow-auto p-6">{hist.loading ? <Spinner /> : (hist.data ?? []).length === 0 ? <Empty title="No review decisions recorded" /> : (
          <table className="card w-full"><thead><tr><th className="th">When</th><th className="th">Event</th><th className="th">Change</th><th className="th">Reviewer</th><th className="th">Notes</th></tr></thead><tbody>{hist.data!.map((h) => (<tr key={h.id} className="border-t border-ink-700"><td className="td font-mono text-xs">{h.created_at.replace("T", " ").slice(0, 16)}</td><td className="td font-mono">{h.event_id} <span className="text-xs text-slate2-500">{h.analysis_id}</span></td><td className="td">{h.previous_status} → <b>{h.new_status}</b></td><td className="td">{h.reviewer}</td><td className="td text-slate2-300">{h.notes}</td></tr>))}</tbody></table>)}</div>
      ) : (
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_400px]">
          <div className="min-h-0 overflow-auto p-4">
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <div><label className="label" htmlFor="fs">Status</label><select id="fs" className="input" value={status} onChange={(e) => { setStatus(e.target.value); app.setFilter({}); }}><option value="">All</option>{(Object.keys(REVIEW_LABELS) as ReviewStatus[]).map((s) => <option key={s} value={s}>{REVIEW_LABELS[s]}</option>)}</select></div>
              <div><label className="label" htmlFor="fc">Confidence</label><select id="fc" className="input" value={conf} onChange={(e) => setConf(e.target.value)}><option value="">Any</option><option value="high">High (≥ 0.85)</option><option value="low">Low (≤ 0.60)</option></select></div>
              <div><label className="label" htmlFor="fp">Min priority {prio}</label><input id="fp" type="range" min={0} max={100} value={prio} onChange={(e) => setPrio(+e.target.value)} /></div>
              <div><label className="label" htmlFor="fk">Cluster</label><input id="fk" className="input !w-24" placeholder="CL-001" value={cluster} onChange={(e) => setCluster(e.target.value)} /></div>
              {app.filter.ids && <button className="btn-ghost" onClick={() => app.setFilter({})}>Clear assistant filter</button>}
            </div>
            {sel.size > 0 && (<div className="mb-3 flex items-center gap-2 rounded-md border border-amber2/40 bg-amber2/10 p-2 text-sm"><span>{sel.size} selected</span><button className="btn-ghost" onClick={() => bulk("confirmed")}>Confirm…</button><button className="btn-ghost" onClick={() => bulk("rejected")}>Reject…</button><button className="btn-ghost" onClick={() => setSel(new Set())}>Clear</button><span className="text-xs text-slate2-400">You will be asked to confirm.</span></div>)}
            {bulkErr && <ErrorBox message={bulkErr} />}
            {q.loading && !q.data ? <Spinner /> : q.error ? <ErrorBox message={q.error} onRetry={q.reload} /> : rows.length === 0 ? <Empty title="No events match these filters" hint="Run an analysis, or relax the filters." /> : (
              <div className="card overflow-x-auto"><table className="w-full"><thead><tr><th className="th w-8"><input type="checkbox" aria-label="Select all" checked={sel.size === rows.length} onChange={(e) => setSel(e.target.checked ? new Set(rows.map((r) => r.uid)) : new Set())} /></th><th className="th">Event</th><th className="th">Status</th><th className="th">Conf.</th><th className="th">Priority</th><th className="th">Area</th><th className="th">Cluster</th><th className="th">Temporal</th></tr></thead>
                <tbody>{rows.map((e) => (<tr key={e.uid} onClick={() => app.selectEvent(e.uid)} className={`cursor-pointer border-t border-ink-700 hover:bg-ink-800 ${app.selectedEventUid === e.uid ? "bg-ink-700" : ""} ${app.highlightIds.includes(e.event_id) ? "outline outline-1 outline-amber2" : ""}`}>
                  <td className="td" onClick={(x) => x.stopPropagation()}><input type="checkbox" aria-label={`Select ${e.event_id}`} checked={sel.has(e.uid)} onChange={() => toggle(e.uid)} /></td><td className="td font-mono">{e.event_id}<div className="text-[10px] text-slate2-500">{e.analysis_id}</div></td><td className="td"><StatusBadge status={e.review_status} /></td><td className="td font-mono">{e.confidence.toFixed(2)}</td><td className="td font-mono">{e.priority_score.toFixed(1)}</td><td className="td">{area(e.area_m2, e.area_px)}</td><td className="td">{e.cluster ?? "—"}</td><td className="td">{e.temporal_status}</td></tr>))}</tbody></table></div>)}
          </div>
          <aside className="min-h-0 overflow-auto border-l border-ink-700 bg-ink-850">{app.selectedEventUid ? <EventInspector uid={app.selectedEventUid} onChanged={q.reload} /> : <div className="p-4"><Notice>Select an event to see its before/after crops, predicted mask and confidence, then confirm or reject it.</Notice></div>}</aside>
        </div>)}
    </div>
  );
}
