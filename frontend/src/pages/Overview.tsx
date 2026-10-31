import { Link } from "react-router-dom";
import { Empty, ErrorBox, Notice, PageHeader, Pill, Spinner, Stat } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { ago, pct } from "../lib/format";
import { api } from "../services/api";

export default function Overview() {
  const { data, error, loading, reload } = useAsync(api.overview, []);
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const c = data.counts, m = data.model;
  return (
    <div>
      <PageHeader title="Overview" subtitle="Live state of this TerraTrace deployment — every figure is read from the database." />
      <div className="grid gap-3 p-6 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Projects" value={c.projects} /><Stat label="Completed analyses" value={c.analyses_completed} hint={`${c.analyses_total} total`} />
        <Stat label="Candidate events" value={c.events} hint={`${c.events_pending} pending · ${c.events_confirmed} confirmed`} /><Stat label="Monitoring regions (AOIs)" value={c.monitoring_regions} />
      </div>
      <div className="grid gap-4 px-6 pb-6 lg:grid-cols-3">
        <section className="card p-4" aria-labelledby="model-h">
          <h2 id="model-h" className="mb-2 text-sm font-semibold">Change-detection model</h2>
          <div className="mb-2 flex gap-2"><Pill tone={m.validated ? "good" : m.inference_available ? "warn" : "bad"}>{m.status.replace("_", " ")}</Pill><span className="text-xs text-slate2-400">{m.architecture}</span></div>
          {m.metrics ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-sm">
              <dt className="text-slate2-400">F1</dt><dd>{m.metrics.f1.toFixed(3)}</dd><dt className="text-slate2-400">IoU</dt><dd>{m.metrics.iou.toFixed(3)}</dd>
              <dt className="text-slate2-400">Precision</dt><dd>{m.metrics.precision.toFixed(3)}</dd><dt className="text-slate2-400">Recall</dt><dd>{m.metrics.recall.toFixed(3)}</dd>
            </dl>
          ) : <Notice tone="warn">{m.message}</Notice>}
          <div className="mt-3 text-xs text-slate2-500">LEVIR-CD test split, in-domain only.</div>
          <Link to="/model" className="mt-2 inline-block text-xs text-signal hover:underline">Open Model Lab →</Link>
        </section>
        <section className="card p-4" aria-labelledby="act-h">
          <h2 id="act-h" className="mb-2 text-sm font-semibold">Recent activity</h2>
          {data.recent_activity.length === 0 ? <Empty title="No analyses yet" hint="Create a project, add two observations and run an analysis." /> :
            <ul className="divide-y divide-ink-700">{data.recent_activity.map((a) => (
              <li key={a.id} className="flex items-center justify-between py-1.5 text-sm"><span className="font-mono">{a.id}</span><Pill tone={a.status === "completed" ? "good" : a.status === "failed" ? "bad" : "warn"}>{a.status}</Pill><span className="text-xs text-slate2-500">{ago(a.at)}</span></li>))}</ul>}
        </section>
        <section className="card p-4" aria-labelledby="sys-h">
          <h2 id="sys-h" className="mb-2 text-sm font-semibold">System health</h2>
          <ul className="space-y-1.5 text-sm">
            <li className="flex justify-between"><span>Database</span><Pill tone="good">{data.system.database}</Pill></li>
            <li className="flex justify-between"><span>Sentinel-2 search</span><Pill tone={data.system.satellite.search_available ? "good" : "bad"}>{data.system.satellite.search_available ? "available" : "off"}</Pill></li>
            <li className="flex justify-between"><span>Sentinel-2 download</span><Pill tone={data.system.satellite.download_available ? "good" : "warn"}>{data.system.satellite.download_available ? "configured" : "needs credentials"}</Pill></li>
            <li className="flex justify-between"><span>LLM provider</span><Pill>{data.system.llm.provider}</Pill></li>
          </ul>
          <h3 className="mb-1 mt-4 text-xs font-medium uppercase tracking-wide text-slate2-400">Recent reports</h3>
          {data.recent_reports.length === 0 ? <div className="text-xs text-slate2-500">None yet.</div> : <ul className="text-sm">{data.recent_reports.map((r) => <li key={r.id} className="truncate">{r.title}</li>)}</ul>}
        </section>
      </div>
    </div>
  );
}
