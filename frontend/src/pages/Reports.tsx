import { Download, FileText } from "lucide-react";
import { useState } from "react";
import { Empty, ErrorBox, Notice, PageHeader, Pill, Spinner } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { ago } from "../lib/format";
import { api } from "../services/api";

export default function Reports() {
  const app = useApp();
  const list = useAsync(() => (app.projectId ? api.reports.list(app.projectId) : Promise.resolve([])), [app.projectId]);
  const [kind, setKind] = useState<"analysis" | "comparison">("analysis"); const [aid, setAid] = useState(""); const [bid, setBid] = useState(""); const [narr, setNarr] = useState(false);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null); const [open, setOpen] = useState<string | null>(null);
  const done = app.analyses.filter((a) => a.status === "completed");
  const detail = useAsync(() => (open ? api.reports.get(open) : Promise.resolve(null)), [open]);
  const create = async () => {
    if (!app.projectId) return; setBusy(true); setErr(null);
    try { const r = await api.reports.create(app.projectId, { kind, analysis_id: aid || app.analysisId, compare_analysis_id: kind === "comparison" ? bid : undefined, with_narrative: narr }); list.reload(); setOpen(r.id); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  if (!app.projectId) return <Empty title="Select a project" />;
  return (
    <div>
      <PageHeader title="Reports" subtitle="Deterministic reports are built from stored records and work without any LLM. An AI narrative is optional and clearly labelled." />
      <div className="grid gap-4 p-6 lg:grid-cols-3">
        <section className="card space-y-3 p-4" aria-labelledby="gr"><h2 id="gr" className="text-sm font-semibold">Generate report</h2>
          <div className="flex gap-2" role="radiogroup" aria-label="Report kind">{(["analysis", "comparison"] as const).map((k) => <button key={k} role="radio" aria-checked={kind === k} className={kind === k ? "btn-primary" : "btn-ghost"} onClick={() => setKind(k)}>{k}</button>)}</div>
          <div><label className="label" htmlFor="ra">{kind === "analysis" ? "Analysis" : "Reference analysis (A)"}</label><select id="ra" className="input" value={aid || app.analysisId || ""} onChange={(e) => setAid(e.target.value)}>{done.map((a) => <option key={a.id} value={a.id}>{a.id} · {a.before_date}→{a.after_date}</option>)}</select></div>
          {kind === "comparison" && <div><label className="label" htmlFor="rb">Comparison analysis (B)</label><select id="rb" className="input" value={bid} onChange={(e) => setBid(e.target.value)}><option value="">Select…</option>{done.map((a) => <option key={a.id} value={a.id}>{a.id} · {a.before_date}→{a.after_date}</option>)}</select></div>}
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={narr} onChange={(e) => setNarr(e.target.checked)} /><span>Add AI-generated narrative<br /><span className="text-xs text-slate2-500">Uses the configured LLM provider; numbers come only from the calculated statistics. Skipped if no provider is reachable.</span></span></label>
          {err && <ErrorBox message={err} />}
          <button className="btn-primary" disabled={busy || done.length === 0 || (kind === "comparison" && !bid)} onClick={create}><FileText className="h-4 w-4" />{busy ? "Generating…" : "Generate PDF report"}</button>
          {done.length === 0 && <Notice>Run an analysis first.</Notice>}
          {app.analysisId && (<div className="border-t border-ink-700 pt-3"><div className="label">Exports for {app.analysisId}</div><div className="flex gap-2"><a className="btn-ghost" href={api.analyses.exportUrl(app.analysisId, "csv")}><Download className="h-4 w-4" />CSV</a>
            {app.analysis?.georeferenced ? <a className="btn-ghost" href={api.analyses.exportUrl(app.analysisId, "geojson")}><Download className="h-4 w-4" />GeoJSON</a> : <span className="text-xs text-slate2-500 self-center">GeoJSON unavailable (not georeferenced)</span>}</div></div>)}
        </section>
        <section className="card lg:col-span-2" aria-labelledby="rl"><h2 id="rl" className="p-4 pb-2 text-sm font-semibold">Generated reports</h2>
          {list.loading ? <Spinner /> : (list.data ?? []).length === 0 ? <Empty title="No reports yet" /> : (
            <ul className="divide-y divide-ink-700">{list.data!.map((r) => (<li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5"><div className="min-w-0 flex-1"><button className="truncate text-left text-sm hover:underline" onClick={() => setOpen(r.id)}>{r.title}</button><div className="text-xs text-slate2-500">{r.id} · {ago(r.created_at)}</div></div>
              {r.has_narrative ? <Pill tone="warn">AI narrative · {r.narrative_provider}</Pill> : <Pill>deterministic only</Pill>}<a className="btn-ghost" href={api.reports.pdfUrl(r.id)}><Download className="h-4 w-4" />PDF</a></li>))}</ul>)}
          {open && detail.data && (<div className="border-t border-ink-700 p-4 text-sm"><h3 className="mb-2 font-semibold">{detail.data.title}</h3>{detail.data.narrative && <div className="mb-3 rounded border border-amber2/40 bg-amber2/5 p-3"><div className="mb-1 text-xs uppercase tracking-wide text-amber2">AI-generated narrative</div>{detail.data.narrative}</div>}
            <details><summary className="cursor-pointer text-xs text-slate2-400">Structured report data (calculated statistics & provenance)</summary><pre className="mt-2 max-h-80 overflow-auto rounded bg-ink-900 p-2 text-xs">{JSON.stringify(detail.data.data, null, 2)}</pre></details></div>)}
        </section>
      </div>
    </div>
  );
}
