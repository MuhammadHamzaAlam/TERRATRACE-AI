import { Check, Eye, X } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip as RTooltip } from "recharts";
import { ErrorBox, Notice, Spinner, StatusBadge } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { area, date } from "../../lib/format";
import { api } from "../../services/api";
import type { ReviewStatus } from "../../types/api";

export default function EventInspector({ uid, onChanged }: { uid: string; onChanged?: () => void }) {
  const { data: e, error, loading, reload } = useAsync(() => api.events.get(uid), [uid]);
  const [notes, setNotes] = useState(""); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  if (loading && !e) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!e) return null;
  const act = async (s: ReviewStatus) => {
    setBusy(true); setErr(null);
    try { await api.events.review(e.uid, s, notes); setNotes(""); reload(); onChanged?.(); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const factors = e.priority_factors ? Object.entries(e.priority_factors.contributions).map(([k, v]) => ({ k, v })) : [];
  return (
    <div className="space-y-3 p-4 text-sm">
      <div className="flex items-center justify-between"><h3 className="font-mono text-base font-semibold">{e.event_id}</h3><StatusBadge status={e.review_status} /></div>
      <div className="text-xs text-slate2-400">Candidate change event (model prediction) · {e.analysis_id} · {date(e.before_date)} → {date(e.after_date)}</div>
      <div className="grid grid-cols-3 gap-2">
        {(["before", "after", "mask"] as const).map((k) => (
          <figure key={k}><img src={api.events.cropUrl(e.uid, k)} alt={`${k} crop of ${e.event_id}`} className="aspect-square w-full rounded border border-ink-700 bg-ink-900 object-contain" style={{ imageRendering: k === "mask" ? "pixelated" : "auto" }} /><figcaption className="mt-0.5 text-center text-xs capitalize text-slate2-400">{k === "mask" ? "predicted mask" : k}</figcaption></figure>
        ))}
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-xs">
        <dt className="text-slate2-400">Model confidence</dt><dd>{e.confidence.toFixed(3)} (max {e.conf_max?.toFixed(3)})</dd>
        <dt className="text-slate2-400">Area</dt><dd>{area(e.area_m2, e.area_px)}{e.area_m2 != null && ` · ${e.area_px} px`}</dd>
        <dt className="text-slate2-400">Priority score</dt><dd>{e.priority_score.toFixed(1)} / 100</dd>
        <dt className="text-slate2-400">Cluster</dt><dd>{e.cluster ?? "unclustered"}</dd>
        <dt className="text-slate2-400">Location</dt><dd>{e.centroid_geo ? `${e.centroid_geo[1].toFixed(6)}, ${e.centroid_geo[0].toFixed(6)}` : `px (${e.centroid_px.map((v) => v.toFixed(0)).join(", ")}) — not georeferenced`}</dd>
        <dt className="text-slate2-400">Temporal</dt><dd>{e.temporal_status}{e.track && ` · seen in ${e.track.n_observations} analyses`}</dd>
      </dl>
      {factors.length > 0 && (<div><div className="label">Priority contributions (points)</div><div className="h-24"><ResponsiveContainer><BarChart data={factors} layout="vertical" margin={{ left: 60 }}><XAxis type="number" hide /><YAxis type="category" dataKey="k" width={90} tick={{ fill: "#aab6c8", fontSize: 11 }} /><RTooltip contentStyle={{ background: "#142238", border: "1px solid #2a4163" }} /><Bar dataKey="v" fill="#3fb8af" /></BarChart></ResponsiveContainer></div>
        <p className="text-xs text-slate2-500">Analytical priority orders events for review; it is not a threat score.</p></div>)}
      <div>
        <label className="label" htmlFor="rn">Review notes</label>
        <textarea id="rn" className="input" rows={2} value={notes} onChange={(x) => setNotes(x.target.value)} placeholder="Optional rationale (stored in the audit history)" />
        <div className="mt-2 flex flex-wrap gap-2">
          <button className="btn-primary" disabled={busy} onClick={() => act("confirmed")}><Check className="h-4 w-4" />Confirm</button>
          <button className="btn-danger" disabled={busy} onClick={() => act("rejected")}><X className="h-4 w-4" />Reject</button>
          <button className="btn-ghost" disabled={busy} onClick={() => act("needs_investigation")}><Eye className="h-4 w-4" />Needs investigation</button>
          <button className="btn-ghost" disabled={busy} onClick={() => act("pending")}>Reset</button>
        </div>
        {err && <div className="mt-2 text-xs text-rose2">{err}</div>}
      </div>
      <div><div className="label">Audit history</div>
        {(e.history ?? []).length === 0 ? <div className="text-xs text-slate2-500">No review decisions yet.</div> :
          <ul className="space-y-1.5">{e.history!.map((h) => (<li key={h.id} className="rounded border border-ink-700 p-2 text-xs"><div>{h.previous_status} → <b>{h.new_status}</b> by {h.reviewer}</div><div className="text-slate2-500">{h.created_at.replace("T", " ").slice(0, 16)}</div>{h.notes && <div className="mt-0.5 text-slate2-300">{h.notes}</div>}</li>))}</ul>}
      </div>
      {e.track && e.track.observations.length > 1 && <div><div className="label">Observation history of this location</div><ul className="text-xs">{e.track.observations.map((o) => <li key={o.uid}>{o.after_date} · {o.event_id} ({o.analysis_id}) · conf {o.confidence} · {o.review_status}</li>)}</ul></div>}
      <Notice>Predictions are not confirmed changes until a human analyst confirms them.</Notice>
    </div>
  );
}
