import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ObservationTimeline from "../features/monitoring/ObservationTimeline";
import { Empty, ErrorBox, Notice, PageHeader, Spinner, Stat } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { num, pct } from "../lib/format";
import { api } from "../services/api";

const tip = { contentStyle: { background: "#142238", border: "1px solid #2a4163", fontSize: 12 } };

export default function Temporal() {
  const app = useApp();
  const tl = useAsync(() => (app.projectId ? api.projects.timeline(app.projectId) : Promise.resolve(null)), [app.projectId, app.analyses.length]);
  const done = app.analyses.filter((a) => a.status === "completed").sort((x, y) => x.after_date.localeCompare(y.after_date));
  const [a, setA] = useState(""); const [b, setB] = useState("");
  useEffect(() => { if (app.comparison) { setA(app.comparison.a); setB(app.comparison.b); } else if (done.length >= 2 && !a && !b) { setA(done[0].id); setB(done[done.length - 1].id); } }, [app.comparison, done.length]); // eslint-disable-line
  const cmp = useAsync(() => (a && b && a !== b ? api.analyses.compare(a, b) : Promise.resolve(null)), [a, b]);
  if (!app.projectId) return <Empty title="No project selected" />;
  if (tl.loading && !tl.data) return <Spinner />;
  if (tl.error) return <ErrorBox message={tl.error} onRetry={tl.reload} />;
  const t = tl.data!;
  const series = t.analyses.map((x) => ({ name: `${x.before_date.slice(5)}→${x.after_date.slice(5)}`, id: x.analysis_id, events: x.n_events, area: x.changed_area_m2 ?? x.changed_pct }));
  return (
    <div>
      <PageHeader title="Temporal monitoring" subtitle="History of observations, analyses and recurring candidate regions. Detections are not confirmed real-world change." />
      <div className="space-y-4 p-6">
        <div className="grid gap-3 sm:grid-cols-4"><Stat label="Observations" value={t.observations.length} /><Stat label="Completed analyses" value={t.analyses.length} /><Stat label="Recurring locations" value={t.tracks.recurring} hint="detected in ≥ 2 analyses" /><Stat label="Single-analysis locations" value={t.tracks.single} /></div>
        <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Observation timeline</h2><ObservationTimeline tl={t} onOpen={app.setAnalysisId} /></section>
        {t.analyses.length === 0 ? <Notice>No completed analyses yet — nothing to chart. Trends are never interpolated.</Notice> : (
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Candidate events per analysis</h2><div className="h-56"><ResponsiveContainer><BarChart data={series}><CartesianGrid stroke="#1d2f4a" /><XAxis dataKey="name" tick={{ fill: "#aab6c8", fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fill: "#aab6c8", fontSize: 11 }} /><Tooltip {...tip} /><Bar dataKey="events" fill="#3fb8af" /></BarChart></ResponsiveContainer></div></section>
            <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Detected area per analysis ({t.analyses.some((x) => x.changed_area_m2 != null) ? "m²" : "% of image"})</h2><div className="h-56"><ResponsiveContainer><LineChart data={series}><CartesianGrid stroke="#1d2f4a" /><XAxis dataKey="name" tick={{ fill: "#aab6c8", fontSize: 11 }} /><YAxis tick={{ fill: "#aab6c8", fontSize: 11 }} /><Tooltip {...tip} /><Line dataKey="area" stroke="#e0a458" dot /></LineChart></ResponsiveContainer></div></section>
          </div>)}
        <section className="card p-4" aria-labelledby="cmp"><h2 id="cmp" className="mb-3 text-sm font-semibold">Compare two analyses</h2>
          {done.length < 2 ? <div className="text-sm text-slate2-400">At least two completed analyses are required for a historical comparison.</div> : (
            <>
              <div className="mb-3 grid gap-3 sm:grid-cols-2"><div><label className="label" htmlFor="ca">Reference (A)</label><select id="ca" className="input" value={a} onChange={(e) => setA(e.target.value)}>{done.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.before_date}→{x.after_date}</option>)}</select></div>
                <div><label className="label" htmlFor="cb">Comparison (B)</label><select id="cb" className="input" value={b} onChange={(e) => setB(e.target.value)}>{done.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.before_date}→{x.after_date}</option>)}</select></div></div>
              {cmp.loading ? <Spinner /> : cmp.error ? <ErrorBox message={cmp.error} /> : cmp.data ? (
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-4"><Stat label="Δ events (B−A)" value={(cmp.data.delta.n_events > 0 ? "+" : "") + cmp.data.delta.n_events} /><Stat label="Δ changed %" value={cmp.data.delta.changed_pct == null ? "—" : pct(cmp.data.delta.changed_pct, 2)} /><Stat label="Δ area m²" value={cmp.data.delta.changed_area_m2 == null ? "n/a" : num(cmp.data.delta.changed_area_m2, 0)} /><Stat label="Δ clusters" value={cmp.data.delta.n_clusters} /></div>
                  {!cmp.data.same_grid && <Notice tone="warn">The analyses use different pixel grids; association between them relies on geographic coordinates only.</Notice>}
                  <div className="grid gap-3 sm:grid-cols-3">
                    {([["New in B", cmp.data.new_in_b], ["Persisting (recurring)", cmp.data.persisting], ["Not detected in B", cmp.data.not_detected_in_b]] as [string, string[]][]).map(([t2, ids]) => (
                      <div key={t2} className="rounded-md border border-ink-700 p-3"><div className="label">{t2} ({ids.length})</div><div className="flex flex-wrap gap-1 font-mono text-xs">{ids.length ? ids.map((i) => <span key={i} className="rounded bg-ink-700 px-1.5 py-0.5">{i}</span>) : <span className="text-slate2-500">none</span>}</div></div>))}
                  </div>
                  <p className="text-xs text-slate2-500">{cmp.data.caveat}</p>
                </div>) : null}
            </>)}
        </section>
      </div>
    </div>
  );
}
