import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AnalysisViewer, { type ViewMode } from "../features/analysis/AnalysisViewer";
import EventInspector from "../features/review/EventInspector";
import { Empty, ErrorBox, Notice, PageHeader, Pill, Spinner, StatusBadge } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { pct } from "../lib/format";
import { api } from "../services/api";

export default function Workspace() {
  const app = useApp(); const a = app.analysis;
  const [mode, setMode] = useState<ViewMode>("overlay"); const [opacity, setOpacity] = useState(0.7); const [swipe, setSwipe] = useState(0.5); const [conf, setConf] = useState(0);
  const ev = useAsync(() => (a && a.status === "completed" && app.projectId ? api.events.list(app.projectId, { analysis_id: a.id, limit: 1000 }) : Promise.resolve(null)), [a?.id, a?.status]);
  const events = useMemo(() => (ev.data?.events ?? []).filter((e) => e.confidence >= conf && (!app.filter.ids || app.filter.ids.includes(e.event_id))), [ev.data, conf, app.filter.ids]);
  if (!app.projectId) return <Empty title="No project" hint="Create a project first." />;
  if (!a) return <div><PageHeader title="Analysis workspace" /><Empty title="No analysis selected" hint="Run an analysis, then open it here."><Link className="btn-primary" to="/new-analysis">New analysis</Link></Empty></div>;
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Analysis workspace" subtitle={`${a.id} · ${a.before_date} → ${a.after_date} · ${a.image_size.join("×")} px`} actions={<Pill tone={a.status === "completed" ? "good" : "warn"}>{a.status}</Pill>} />
      {a.status !== "completed" ? (
        <div className="p-6"><Notice tone={a.status === "failed" || a.status === "blocked" ? "warn" : "info"}>Analysis is <b>{a.status}</b>. {a.status_message}</Notice>
          {a.status === "blocked" && a.status_message.includes("checkpoint") && <p className="mt-3 text-sm text-slate2-400">Train or provide a model checkpoint: see <Link to="/model" className="text-signal underline">Model Lab</Link>.</p>}</div>
      ) : (
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="relative min-h-[420px]">
            <div className="absolute left-3 top-3 z-[500] flex flex-wrap items-center gap-2 rounded-md border border-ink-700 bg-ink-900/90 p-2 text-xs">
              <div role="radiogroup" aria-label="View mode" className="flex gap-1">{(["before", "after", "overlay", "mask", "swipe"] as ViewMode[]).map((m) => <button key={m} role="radio" aria-checked={mode === m} className={`rounded px-2 py-1 capitalize ${mode === m ? "bg-signal text-ink-950" : "hover:bg-ink-700"}`} onClick={() => setMode(m)}>{m === "mask" ? "predicted mask" : m}</button>)}</div>
              {mode === "overlay" && <label className="flex items-center gap-1">Opacity<input type="range" min={0} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(+e.target.value)} aria-label="Overlay opacity" /></label>}
              {mode === "swipe" && <label className="flex items-center gap-1">Before ◂▸ After<input type="range" min={0} max={1} step={0.01} value={swipe} onChange={(e) => setSwipe(+e.target.value)} aria-label="Swipe position" /></label>}
              <label className="flex items-center gap-1">Min conf {conf.toFixed(2)}<input type="range" min={0} max={1} step={0.05} value={conf} onChange={(e) => setConf(+e.target.value)} aria-label="Minimum confidence" /></label>
            </div>
            <div className="absolute bottom-3 left-3 z-[500] rounded bg-ink-900/90 px-2 py-1 text-xs text-slate2-300">Red = model-predicted change (not ground truth). Boxes coloured by review status.</div>
            <AnalysisViewer analysis={a} mode={mode} opacity={opacity} events={events} selectedUid={app.selectedEventUid} highlight={app.highlightIds} onSelect={app.selectEvent} swipe={swipe} />
          </div>
          <aside className="min-h-0 overflow-auto border-l border-ink-700 bg-ink-850">
            {app.selectedEventUid ? (<div><button className="btn-ghost m-3" onClick={() => app.selectEvent(null)}>← All events</button><EventInspector uid={app.selectedEventUid} onChanged={ev.reload} /></div>) : (
              <div className="p-4">
                <div className="mb-3 grid grid-cols-2 gap-2 text-xs"><div className="card p-2"><div className="text-slate2-400">Candidate events</div><div className="font-mono text-lg">{a.metrics.n_events}</div></div><div className="card p-2"><div className="text-slate2-400">Changed area</div><div className="font-mono text-lg">{pct(a.metrics.changed_pct, 2)}</div></div></div>
                {a.alignment?.notes?.map((n, i) => <Notice key={i} tone="warn">{n}</Notice>)}
                {a.compatibility?.status && a.compatibility.status !== "compatible" && <div className="mt-2"><Notice tone="warn">Domain: {a.compatibility.status}. {a.compatibility.notes?.join(" ")}</Notice></div>}
                <h3 className="label mt-3">Events ({events.length}{app.filter.ids ? " · assistant filter" : ""})</h3>
                {app.filter.ids && <button className="btn-ghost mb-2 !py-0.5 text-xs" onClick={() => app.setFilter({})}>Clear filter</button>}
                {ev.loading ? <Spinner /> : events.length === 0 ? <Empty title="No events match" /> : (
                  <ul className="space-y-1">{events.map((e) => (<li key={e.uid}><button onClick={() => app.selectEvent(e.uid)} className="flex w-full items-center justify-between rounded border border-ink-700 px-2 py-1.5 text-left text-sm hover:bg-ink-700"><span className="font-mono">{e.event_id}</span><span className="text-xs text-slate2-400">conf {e.confidence.toFixed(2)} · P{e.priority_score.toFixed(0)}</span><StatusBadge status={e.review_status} /></button></li>))}</ul>)}
              </div>)}
          </aside>
        </div>
      )}
      {ev.error && <ErrorBox message={ev.error} onRetry={ev.reload} />}
    </div>
  );
}
