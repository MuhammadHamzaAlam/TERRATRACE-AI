import { Play, Satellite, Search } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, Notice, PageHeader, Pill, Progress } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync, usePoll } from "../hooks/useAsync";
import { api } from "../services/api";
import type { Analysis, Observation } from "../types/api";

type Mode = "pair" | "consecutive" | "first_latest" | "range";

function RunningAnalysis({ id }: { id: string }) {
  const f = useCallback(() => api.analyses.get(id), [id]);
  const a = usePoll(f, (x) => ["completed", "failed", "blocked"].includes(x.status), 1000);
  if (!a) return null;
  const tone = a.status === "completed" ? "good" : a.status === "running" || a.status === "pending" ? "warn" : "bad";
  return (
    <div className="rounded-md border border-ink-700 p-3">
      <div className="mb-1 flex items-center justify-between text-sm"><span className="font-mono">{a.id} · {a.before_date} → {a.after_date}</span><Pill tone={tone}>{a.status}</Pill></div>
      <Progress value={a.progress} />
      <div className="mt-1 text-xs text-slate2-400">{a.status_message || "Queued"}{a.status === "completed" && ` — ${a.metrics.n_events} candidate events`}</div>
      {a.alignment?.notes?.map((n, i) => <div key={i} className="mt-1 text-xs text-amber2">{n}</div>)}
      {a.compatibility?.status && a.compatibility.status !== "compatible" && <div className="mt-1 text-xs text-amber2">Domain: {a.compatibility.status}. {a.compatibility.notes?.join(" ")}</div>}
    </div>
  );
}

function Sentinel({ projectId, onImported }: { projectId: string; onImported: () => void }) {
  const st = useAsync(api.satellite.status, []);
  const [bbox, setBbox] = useState("13.30,52.45,13.50,52.55"); const [start, setStart] = useState(""); const [end, setEnd] = useState(""); const [cloud, setCloud] = useState(30);
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.satellite.search>>["scenes"] | null>(null); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const search = async () => {
    setErr(null); setBusy(true);
    try { const b = bbox.split(",").map(Number); if (b.length !== 4 || b.some(Number.isNaN)) throw new Error("bbox must be minLon,minLat,maxLon,maxLat"); setRes((await api.satellite.search({ bbox: b, start, end, max_cloud: cloud })).scenes); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const importScene = async (s: NonNullable<typeof res>[number]) => {
    try { await api.satellite.import(projectId, { product_id: s.id, product_name: s.name, bbox: bbox.split(",").map(Number), acquisition_date: s.acquisition_date, label: `Sentinel-2 ${s.acquisition_date}` }); setMsg(`Import of ${s.acquisition_date} started — it appears under Projects when processed.`); setTimeout(onImported, 3000); }
    catch (e) { setErr((e as Error).message); }
  };
  return (
    <section className="card space-y-3 p-4" aria-labelledby="s2">
      <h2 id="s2" className="flex items-center gap-2 text-sm font-semibold"><Satellite className="h-4 w-4" />Sentinel-2 (Copernicus Data Space)</h2>
      <Notice tone="warn">Sentinel-2 is 10 m/pixel; the model is trained on 0.5 m LEVIR-CD imagery. Analyses on Sentinel-2 are flagged <b>unvalidated</b> and need explicit acknowledgement.</Notice>
      {st.data && !st.data.download_available && <Notice>{st.data.message}</Notice>}
      <div className="grid gap-2 sm:grid-cols-5">
        <div className="sm:col-span-2"><label className="label" htmlFor="bb">AOI bbox (lon/lat)</label><input id="bb" className="input font-mono" value={bbox} onChange={(e) => setBbox(e.target.value)} /></div>
        <div><label className="label" htmlFor="s2s">From</label><input id="s2s" type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="label" htmlFor="s2e">To</label><input id="s2e" type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        <div><label className="label" htmlFor="s2c">Max cloud %</label><input id="s2c" type="number" className="input" min={0} max={100} value={cloud} onChange={(e) => setCloud(+e.target.value)} /></div>
      </div>
      <button className="btn-primary" disabled={!start || !end || busy} onClick={search}><Search className="h-4 w-4" />{busy ? "Searching…" : "Search scenes"}</button>
      {err && <ErrorBox message={err} />}{msg && <Notice>{msg}</Notice>}
      {res && (res.length === 0 ? <Empty title="No scenes found" hint="Widen the date range or cloud threshold." /> : (
        <ul className="grid gap-2 sm:grid-cols-2">{res.map((s) => (
          <li key={s.id} className="flex gap-3 rounded-md border border-ink-700 p-2">
            <img src={`/api/satellite/scenes/${s.id}/quicklook`} alt="" className="h-20 w-20 rounded object-cover bg-ink-800" loading="lazy" onError={(e) => ((e.target as HTMLImageElement).style.visibility = "hidden")} />
            <div className="min-w-0 flex-1 text-sm"><div className="font-medium">{s.acquisition_date} · tile {s.tile_id}</div><div className="text-xs text-slate2-400">Cloud {s.cloud_cover?.toFixed(1) ?? "n/a"}% · {s.size_mb} MB</div>
              <button className="btn-ghost mt-1 !py-0.5 text-xs" disabled={!st.data?.download_available} onClick={() => importScene(s)}>Import to project</button></div></li>))}</ul>))}
    </section>
  );
}

export default function NewAnalysis() {
  const app = useApp();
  const obs = useAsync(() => (app.projectId ? api.projects.observations(app.projectId) : Promise.resolve([] as Observation[])), [app.projectId]);
  const [mode, setMode] = useState<Mode>("pair");
  const [before, setBefore] = useState(""); const [after, setAfter] = useState(""); const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const [threshold, setThreshold] = useState(0.5); const [minPx, setMinPx] = useState(20); const [eps, setEps] = useState(""); const [gap, setGap] = useState(false); const [misal, setMisal] = useState(false);
  const [started, setStarted] = useState<Analysis[]>([]); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  const sorted = useMemo(() => [...(obs.data ?? [])].sort((a, b) => a.acquisition_date.localeCompare(b.acquisition_date)), [obs.data]);
  const pairs = useMemo<[Observation, Observation][]>(() => {
    const find = (id: string) => sorted.find((o) => o.id === id);
    if (mode === "pair") { const b = find(before), a = find(after); return b && a ? [[b, a]] : []; }
    if (mode === "consecutive") return sorted.slice(1).map((o, i) => [sorted[i], o] as [Observation, Observation]);
    if (mode === "first_latest") return sorted.length >= 2 ? [[sorted[0], sorted[sorted.length - 1]]] : [];
    const r = sorted.filter((o) => (!from || o.acquisition_date >= from) && (!to || o.acquisition_date <= to));
    return r.length >= 2 ? [[r[0], r[r.length - 1]]] : [];
  }, [mode, sorted, before, after, from, to]);
  const warnings = pairs.flatMap(([b, a]) => {
    const w: string[] = [];
    if (b.georeferenced !== a.georeferenced) w.push(`${b.id}/${a.id}: one is georeferenced, the other is not — will be blocked.`);
    if (!b.georeferenced && (b.width !== a.width || b.height !== a.height)) w.push(`${b.id}/${a.id}: different sizes without georeferencing — will be blocked.`);
    if (a.acquisition_date <= b.acquisition_date) w.push(`${b.id}/${a.id}: 'after' must be later than 'before'.`);
    if (b.meta.domain_compatibility?.status === "unvalidated") w.push(`${b.id}: resolution outside LEVIR-CD domain (${b.pixel_size_m?.toFixed(1)} m) — needs acknowledgement below.`);
    return w;
  });

  const start = async () => {
    if (!app.projectId) return; setBusy(true); setErr(null);
    try {
      const made: Analysis[] = [];
      for (const [b, a] of pairs) made.push(await api.analyses.create(app.projectId, { before_observation_id: b.id, after_observation_id: a.id, threshold, min_event_pixels: minPx, cluster_eps: eps ? +eps : null, allow_domain_gap: gap, allow_misaligned: misal }));
      setStarted(made); app.reloadAnalyses();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  if (!app.projectId) return <div><PageHeader title="New analysis" /><Empty title="Select or create a project first" hint="Analyses compare two observations of a project." /></div>;
  return (
    <div>
      <PageHeader title="New analysis" subtitle={`Project: ${app.project?.name ?? ""}`} />
      <div className="grid gap-4 p-6 lg:grid-cols-3">
        <section className="card space-y-4 p-4 lg:col-span-2" aria-labelledby="sel">
          <h2 id="sel" className="text-sm font-semibold">1. Choose observations</h2>
          {sorted.length < 2 ? <Notice>This project needs at least two observations. Upload them in <Link className="text-signal underline" to="/projects">Projects</Link> or import Sentinel-2 below.</Notice> : (
            <>
              <div role="radiogroup" aria-label="Comparison mode" className="flex flex-wrap gap-2">
                {([["pair", "Any two"], ["consecutive", "Consecutive pairs"], ["first_latest", "First vs latest"], ["range", "Date range"]] as [Mode, string][]).map(([m, l]) => (
                  <button key={m} role="radio" aria-checked={mode === m} className={mode === m ? "btn-primary" : "btn-ghost"} onClick={() => setMode(m)}>{l}</button>))}
              </div>
              {mode === "pair" && <div className="grid gap-3 sm:grid-cols-2">
                <div><label className="label" htmlFor="bf">Before (earlier)</label><select id="bf" className="input" value={before} onChange={(e) => setBefore(e.target.value)}><option value="">Select…</option>{sorted.map((o) => <option key={o.id} value={o.id}>{o.acquisition_date} · {o.label}</option>)}</select></div>
                <div><label className="label" htmlFor="af">After (later)</label><select id="af" className="input" value={after} onChange={(e) => setAfter(e.target.value)}><option value="">Select…</option>{sorted.map((o) => <option key={o.id} value={o.id}>{o.acquisition_date} · {o.label}</option>)}</select></div></div>}
              {mode === "range" && <div className="grid gap-3 sm:grid-cols-2"><div><label className="label" htmlFor="rf">From</label><input id="rf" type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} /></div><div><label className="label" htmlFor="rt">To</label><input id="rt" type="date" className="input" value={to} onChange={(e) => setTo(e.target.value)} /></div></div>}
              <div className="text-sm text-slate2-300">{pairs.length === 0 ? "No valid pair selected." : `${pairs.length} analysis${pairs.length > 1 ? "es" : ""} will run: ` + pairs.map(([b, a]) => `${b.acquisition_date}→${a.acquisition_date}`).join(", ")}</div>
              {warnings.map((w, i) => <Notice key={i} tone="warn">{w}</Notice>)}
              <h2 className="text-sm font-semibold">2. Configuration</h2>
              <div className="grid gap-3 sm:grid-cols-4">
                <div><label className="label" htmlFor="th">Probability threshold</label><input id="th" type="number" step={0.05} min={0.05} max={0.95} className="input" value={threshold} onChange={(e) => setThreshold(+e.target.value)} /></div>
                <div><label className="label" htmlFor="mp">Min event pixels</label><input id="mp" type="number" min={1} className="input" value={minPx} onChange={(e) => setMinPx(+e.target.value)} /></div>
                <div><label className="label" htmlFor="ce">Cluster eps (m or px)</label><input id="ce" type="number" className="input" placeholder="auto" value={eps} onChange={(e) => setEps(e.target.value)} /></div>
              </div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={gap} onChange={(e) => setGap(e.target.checked)} />Allow analysis outside the validated resolution range (results will be marked unvalidated)</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={misal} onChange={(e) => setMisal(e.target.checked)} />Allow poorly aligned pairs (expect false detections)</label>
              {err && <ErrorBox message={err} />}
              <button className="btn-primary" disabled={pairs.length === 0 || busy} onClick={start}><Play className="h-4 w-4" />Start analysis</button>
            </>
          )}
        </section>
        <section className="card space-y-2 p-4" aria-labelledby="prog"><h2 id="prog" className="text-sm font-semibold">Progress</h2>
          {started.length === 0 ? <div className="text-sm text-slate2-500">Progress is reported live from the backend job once started.</div> : started.map((a) => <RunningAnalysis key={a.id} id={a.id} />)}
          {started.length > 0 && <Link to="/workspace" className="btn-ghost">Open workspace</Link>}
        </section>
        <div className="lg:col-span-3"><Sentinel projectId={app.projectId} onImported={obs.reload} /></div>
      </div>
    </div>
  );
}
