import { Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, Notice, PageHeader, Pill, Spinner } from "../components/ui";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { date } from "../lib/format";
import { api } from "../services/api";
import ObservationTimeline from "../features/monitoring/ObservationTimeline";

export default function Projects() {
  const app = useApp();
  const [name, setName] = useState(""); const [desc, setDesc] = useState(""); const [err, setErr] = useState<string | null>(null);
  const obs = useAsync(() => (app.projectId ? api.projects.observations(app.projectId) : Promise.resolve([])), [app.projectId]);
  const tl = useAsync(() => (app.projectId ? api.projects.timeline(app.projectId) : Promise.resolve(null)), [app.projectId, app.analyses.length]);
  const [upDate, setUpDate] = useState(""); const [upLabel, setUpLabel] = useState(""); const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null); const aoiRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState(false); const [eName, setEName] = useState(""); const [eDesc, setEDesc] = useState("");

  const create = async () => {
    setErr(null);
    try { const p = await api.projects.create({ name, description: desc }); setName(""); setDesc(""); app.reloadProjects(); app.setProjectId(p.id); } catch (e) { setErr((e as Error).message); }
  };
  const upload = async () => {
    const f = fileRef.current?.files?.[0];
    if (!app.projectId || !f || !upDate) { setErr("Choose a file and an acquisition date."); return; }
    setBusy(true); setErr(null);
    try { await api.projects.uploadObservation(app.projectId, f, upDate, upLabel); if (fileRef.current) fileRef.current.value = ""; setUpLabel(""); obs.reload(); app.reloadProjects(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!app.project) return;
    const typed = window.prompt(`Deleting a project permanently removes its observations, analyses, events and reports.\nType the project name (${app.project.name}) to confirm:`);
    if (typed == null) return;
    try { await api.projects.remove(app.project.id, typed); app.setProjectId(null); app.reloadProjects(); } catch (e) { setErr((e as Error).message); }
  };
  const saveEdit = async () => { if (!app.project) return; try { await api.projects.update(app.project.id, { name: eName, description: eDesc }); setEditing(false); app.reloadProjects(); } catch (e) { setErr((e as Error).message); } };

  return (
    <div>
      <PageHeader title="Projects & monitoring" subtitle="A project is a monitored area with multiple dated observations." />
      <div className="grid gap-4 p-6 lg:grid-cols-3">
        <section className="card space-y-3 p-4" aria-labelledby="np">
          <h2 id="np" className="text-sm font-semibold">New project</h2>
          <div><label className="label" htmlFor="pn">Name</label><input id="pn" className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label className="label" htmlFor="pd">Description</label><textarea id="pd" className="input" rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
          <button className="btn-primary" disabled={!name.trim()} onClick={create}><Plus className="h-4 w-4" />Create project</button>
        </section>
        <section className="card p-4 lg:col-span-2" aria-labelledby="cp">
          {!app.project ? <Empty title="No project selected" hint="Create a project to start monitoring an area." /> : (
            <>
              <div className="mb-3 flex items-start justify-between gap-3">
                {editing ? (
                  <div className="flex-1 space-y-2"><input className="input" value={eName} onChange={(e) => setEName(e.target.value)} aria-label="Project name" /><textarea className="input" rows={2} value={eDesc} onChange={(e) => setEDesc(e.target.value)} aria-label="Project description" />
                    <div className="flex gap-2"><button className="btn-primary" onClick={saveEdit}>Save</button><button className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button></div></div>
                ) : (
                  <div><h2 id="cp" className="text-base font-semibold">{app.project.name}</h2><p className="text-sm text-slate2-400">{app.project.description || "No description"}</p>
                    <div className="mt-1 flex gap-2 text-xs text-slate2-500"><span>{app.project.counts.observations} observations</span>·<span>{app.project.counts.analyses} analyses</span>·<span>{app.project.counts.events} events</span>·<span>{app.project.counts.aois} AOIs</span></div></div>
                )}
                {!editing && <div className="flex gap-2"><button className="btn-ghost" onClick={() => { setEName(app.project!.name); setEDesc(app.project!.description); setEditing(true); }}>Edit</button><button className="btn-danger" onClick={remove} aria-label="Delete project"><Trash2 className="h-4 w-4" /></button></div>}
              </div>
              {err && <ErrorBox message={err} />}
              <h3 className="label">Add observation</h3>
              <div className="grid gap-2 sm:grid-cols-4">
                <input ref={fileRef} type="file" accept=".tif,.tiff,.png,.jpg,.jpeg" className="input sm:col-span-2" aria-label="Image file" />
                <input type="date" className="input" value={upDate} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setUpDate(e.target.value)} aria-label="Acquisition date" />
                <input className="input" placeholder="Label (optional)" value={upLabel} onChange={(e) => setUpLabel(e.target.value)} aria-label="Observation label" />
              </div>
              <div className="mt-2 flex items-center gap-2"><button className="btn-primary" onClick={upload} disabled={busy}><Upload className="h-4 w-4" />{busy ? "Uploading…" : "Upload observation"}</button>
                <button className="btn-ghost" onClick={() => aoiRef.current?.click()}>Upload AOI GeoJSON</button>
                <input ref={aoiRef} type="file" accept=".geojson,.json" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f && app.projectId) { try { await api.projects.uploadAoi(app.projectId, f); app.reloadProjects(); } catch (x) { setErr((x as Error).message); } } }} />
                <span className="text-xs text-slate2-500">GeoTIFF (georeferenced), PNG or JPEG · max 200 MB</span></div>
            </>
          )}
        </section>
      </div>
      {app.project && (
        <div className="space-y-4 px-6 pb-6">
          <section className="card p-4"><h2 className="mb-3 text-sm font-semibold">Observation timeline</h2>
            {tl.loading ? <Spinner /> : tl.data ? <ObservationTimeline tl={tl.data} onOpen={(id) => app.setAnalysisId(id)} /> : null}</section>
          <section className="card overflow-x-auto"><table className="w-full"><thead><tr><th className="th">Observation</th><th className="th">Date</th><th className="th">Source</th><th className="th">Size</th><th className="th">Georef.</th><th className="th">Domain match</th></tr></thead>
            <tbody>{(obs.data ?? []).map((o) => (<tr key={o.id} className="border-t border-ink-700"><td className="td"><span className="font-mono text-xs">{o.id}</span> {o.label}</td><td className="td">{date(o.acquisition_date)}</td><td className="td">{o.source}</td><td className="td">{o.width}×{o.height}</td>
              <td className="td">{o.georeferenced ? <Pill tone="good">{o.crs}</Pill> : <Pill tone="warn">image-relative</Pill>}</td><td className="td"><Pill tone={o.meta.domain_compatibility?.status === "compatible" ? "good" : "warn"}>{o.meta.domain_compatibility?.status ?? "unknown"}</Pill></td></tr>))}
              {obs.data?.length === 0 && <tr><td colSpan={6}><Empty title="No observations yet" hint="Upload at least two dated images of the same area." /></td></tr>}</tbody></table></section>
          <Notice>Run comparisons from <Link to="/new-analysis" className="text-signal underline">New analysis</Link>: any two observations, consecutive pairs, first vs latest, or a date range.</Notice>
        </div>
      )}
    </div>
  );
}
