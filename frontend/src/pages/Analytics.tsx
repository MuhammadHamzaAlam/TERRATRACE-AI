import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Empty, ErrorBox, PageHeader, Spinner, Stat } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { STATUS_COLOR, num, pct } from "../lib/format";
import { api } from "../services/api";
import { REVIEW_LABELS, type ReviewStatus } from "../types/api";

const tip = { contentStyle: { background: "#142238", border: "1px solid #2a4163", fontSize: 12 } };
const ax = { tick: { fill: "#aab6c8", fontSize: 11 } };

export default function Analytics() {
  const app = useApp(); const a = app.analysis;
  const d = useAsync(async () => {
    if (!a || !app.projectId || a.status !== "completed") return null;
    const [summary, events, clusters] = await Promise.all([api.analyses.summary(a.id), api.events.list(app.projectId, { analysis_id: a.id, limit: 1000 }), api.events.clusters(app.projectId, a.id)]);
    return { summary, events: events.events, clusters };
  }, [a?.id, a?.status]);
  if (!app.projectId || !a) return <div><PageHeader title="Analytics" /><Empty title="No completed analysis selected" hint="Select an analysis from the top bar." /></div>;
  if (d.loading && !d.data) return <Spinner />;
  if (d.error) return <ErrorBox message={d.error} onRetry={d.reload} />;
  if (!d.data) return <div><PageHeader title="Analytics" /><Empty title={`Analysis ${a.id} is ${a.status}`} /></div>;
  const { summary: s, events, clusters } = d.data;
  const status = (Object.keys(REVIEW_LABELS) as ReviewStatus[]).map((k) => ({ name: REVIEW_LABELS[k], key: k, value: s.review_status_counts[k] ?? 0 })).filter((x) => x.value > 0);
  const top = [...events].sort((x, y) => y.priority_score - x.priority_score).slice(0, 10).map((e) => ({ name: e.event_id, priority: e.priority_score }));
  const sizeBins = (() => { const bins = [[0, 100], [100, 500], [500, 2000], [2000, 10000], [10000, 1e9]]; return bins.map(([lo, hi]) => ({ name: hi > 1e8 ? `≥${lo}` : `${lo}–${hi}`, count: events.filter((e) => e.area_px >= lo && e.area_px < hi).length })); })();
  return (
    <div>
      <PageHeader title="Analytics" subtitle={`${a.id} · ${s.before_date} → ${s.after_date}`} />
      <div className="space-y-4 p-6">
        <div className="grid gap-3 sm:grid-cols-4"><Stat label="Candidate events" value={s.n_events} /><Stat label="Clusters" value={s.n_clusters} /><Stat label="Changed share" value={pct(s.changed_pct, 2)} hint="of analysed image" /><Stat label="Changed area" value={s.changed_area_m2 != null ? `${num(s.changed_area_m2, 0)} m²` : `${num(s.changed_pixels)} px`} hint={s.changed_area_m2 != null ? "geodesic" : "not georeferenced"} /></div>
        {s.n_events === 0 ? <Empty title="No candidate events in this analysis" /> : (
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Model confidence distribution</h2><div className="h-56"><ResponsiveContainer><BarChart data={s.confidence_distribution}><CartesianGrid stroke="#1d2f4a" /><XAxis dataKey="range" {...ax} /><YAxis allowDecimals={false} {...ax} /><Tooltip {...tip} /><Bar dataKey="count" fill="#3fb8af" /></BarChart></ResponsiveContainer></div></section>
            <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Review status</h2><div className="h-56"><ResponsiveContainer><PieChart><Pie data={status} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} label>{status.map((x) => <Cell key={x.key} fill={STATUS_COLOR[x.key]} />)}</Pie><Tooltip {...tip} /></PieChart></ResponsiveContainer></div></section>
            <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Top analytical priority</h2><div className="h-56"><ResponsiveContainer><BarChart data={top} layout="vertical" margin={{ left: 30 }}><CartesianGrid stroke="#1d2f4a" /><XAxis type="number" domain={[0, 100]} {...ax} /><YAxis type="category" dataKey="name" width={70} {...ax} /><Tooltip {...tip} /><Bar dataKey="priority" fill="#e0a458" /></BarChart></ResponsiveContainer></div></section>
            <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Event size distribution (px)</h2><div className="h-56"><ResponsiveContainer><BarChart data={sizeBins}><CartesianGrid stroke="#1d2f4a" /><XAxis dataKey="name" {...ax} /><YAxis allowDecimals={false} {...ax} /><Tooltip {...tip} /><Bar dataKey="count" fill="#8ab4f8" /></BarChart></ResponsiveContainer></div></section>
            <section className="card p-4 lg:col-span-2"><h2 className="mb-2 text-sm font-semibold">Confidence vs. area</h2><div className="h-64"><ResponsiveContainer><ScatterChart><CartesianGrid stroke="#1d2f4a" /><XAxis type="number" dataKey="area_px" name="area px" scale="log" domain={["auto", "auto"]} {...ax} /><YAxis type="number" dataKey="confidence" name="confidence" domain={[0.4, 1]} {...ax} /><ZAxis range={[40, 40]} /><Tooltip {...tip} cursor={{ strokeDasharray: "3 3" }} /><Scatter data={events} fill="#3fb8af" /></ScatterChart></ResponsiveContainer></div></section>
            <section className="card overflow-x-auto p-0 lg:col-span-2"><h2 className="p-4 pb-2 text-sm font-semibold">Cluster statistics</h2>
              {clusters.length === 0 ? <div className="px-4 pb-4 text-sm text-slate2-400">No clusters formed (events are spatially isolated at the current DBSCAN parameters).</div> : (
                <table className="w-full"><thead><tr><th className="th">Cluster</th><th className="th">Events</th><th className="th">Total area</th><th className="th">Mean conf.</th><th className="th">Priority</th><th className="th">DBSCAN eps</th><th className="th" /></tr></thead>
                  <tbody>{clusters.map((c) => (<tr key={c.uid} className="border-t border-ink-700"><td className="td font-mono">{c.cluster_id}</td><td className="td">{c.event_count}</td><td className="td">{c.total_area_m2 != null ? `${num(c.total_area_m2, 1)} m²` : `${num(c.total_area_px)} px`}</td><td className="td font-mono">{c.mean_confidence.toFixed(2)}</td><td className="td font-mono">{c.priority_score.toFixed(1)}</td><td className="td text-xs text-slate2-400">{String(c.params.eps)} {String(c.params.unit)}</td><td className="td"><button className="btn-ghost !py-0.5 text-xs" onClick={() => { app.selectCluster(c.cluster_id); app.setFilter({ cluster: c.cluster_id }); }}>Select</button></td></tr>))}</tbody></table>)}</section>
          </div>)}
      </div>
    </div>
  );
}
