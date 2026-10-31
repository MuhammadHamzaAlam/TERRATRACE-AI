import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorBox, Notice, PageHeader, Pill, Spinner, Stat } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

const tip = { contentStyle: { background: "#142238", border: "1px solid #2a4163", fontSize: 12 } };

export default function ModelLab() {
  const st = useAsync(api.model.status, []); const met = useAsync(api.model.metrics, []); const ds = useAsync(api.model.dataset, []); const arch = useAsync(api.model.architecture, []); const tr = useAsync(api.model.training, []);
  const [epochs, setEpochs] = useState(8); const [msg, setMsg] = useState<string | null>(null); const [err, setErr] = useState<string | null>(null);
  const m = st.data;
  const hist = met.data?.training_history ?? [];
  const tm = met.data?.test_metrics as null | { f1: number; iou: number; precision: number; recall: number; accuracy: number; n_images: number; threshold: number; confusion_matrix: { tp: number; fp: number; fn: number; tn: number } };
  return (
    <div>
      <PageHeader title="Model laboratory" subtitle="Siamese U-Net · shared ResNet18 encoder · trained on LEVIR-CD" actions={m && <Pill tone={m.validated ? "good" : m.inference_available ? "warn" : "bad"}>{m.status.replace("_", " ")}</Pill>} />
      <div className="space-y-4 p-6">
        {st.error && <ErrorBox message={st.error} onRetry={st.reload} />}
        {m?.message && <Notice tone="warn">{m.message}</Notice>}
        <div className="grid gap-4 lg:grid-cols-3">
          <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Architecture</h2>{arch.loading ? <Spinner /> : arch.data && <dl className="space-y-1.5 text-xs">{Object.entries(arch.data).map(([k, v]) => <div key={k}><dt className="text-slate2-400 uppercase tracking-wide">{k}</dt><dd className="font-mono">{typeof v === "number" ? v.toLocaleString() : String(v)}</dd></div>)}</dl>}</section>
          <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Dataset: LEVIR-CD</h2>{ds.loading ? <Spinner /> : ds.data && (<div className="text-sm">
            {!ds.data.available ? <Notice tone="warn">Dataset not found at <code>{ds.data.root}</code>. See docs/dataset.md for acquisition steps.</Notice> : (
              <table className="w-full text-xs"><thead><tr><th className="th">Split</th><th className="th">Pairs</th><th className="th">Changed px</th></tr></thead><tbody>{Object.entries(ds.data.splits).map(([k, v]) => <tr key={k} className="border-t border-ink-700"><td className="td">{k}</td><td className="td font-mono">{v.n_pairs}</td><td className="td font-mono">{v.changed_pixel_fraction_sampled != null ? (v.changed_pixel_fraction_sampled * 100).toFixed(2) + "%" : "—"}</td></tr>)}</tbody></table>)}
            <p className="mt-2 text-xs text-slate2-500">{ds.data.usage_note}</p><p className="text-xs text-slate2-500">Source: {ds.data.source}</p></div>)}</section>
          <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Checkpoint & inference</h2><dl className="space-y-1 text-sm"><div className="flex justify-between"><dt className="text-slate2-400">Checkpoint</dt><dd>{m?.checkpoint_present ? "present" : "missing"}</dd></div><div className="flex justify-between"><dt className="text-slate2-400">Inference available</dt><dd>{m?.inference_available ? "yes" : "no"}</dd></div><div className="flex justify-between"><dt className="text-slate2-400">Validated on test split</dt><dd>{m?.validated ? "yes" : "no"}</dd></div></dl>
            <div className="mt-3 flex gap-2"><button className="btn-ghost" disabled={!m?.checkpoint_present} onClick={async () => { try { await api.model.evaluate(); setMsg("Evaluation started on the LEVIR-CD test split (runs in the background; refresh in a few minutes)."); } catch (e) { setErr((e as Error).message); } }}>Run evaluation</button></div></section>
        </div>
        <section className="card p-4" aria-labelledby="ev"><h2 id="ev" className="mb-2 text-sm font-semibold">Evaluation — LEVIR-CD test split (full 1024² images, tiled inference)</h2>
          {tm ? (<><div className="grid gap-3 sm:grid-cols-5"><Stat label="F1" value={tm.f1.toFixed(4)} /><Stat label="IoU" value={tm.iou.toFixed(4)} /><Stat label="Precision" value={tm.precision.toFixed(4)} /><Stat label="Recall" value={tm.recall.toFixed(4)} /><Stat label="Images" value={tm.n_images} hint={`threshold ${tm.threshold}`} /></div>
            <div className="mt-3 grid max-w-sm grid-cols-2 gap-1 text-center font-mono text-sm"><div className="card p-2"><div className="text-xs text-slate2-400">TP</div>{tm.confusion_matrix.tp.toLocaleString()}</div><div className="card p-2"><div className="text-xs text-slate2-400">FP</div>{tm.confusion_matrix.fp.toLocaleString()}</div><div className="card p-2"><div className="text-xs text-slate2-400">FN</div>{tm.confusion_matrix.fn.toLocaleString()}</div><div className="card p-2"><div className="text-xs text-slate2-400">TN</div>{tm.confusion_matrix.tn.toLocaleString()}</div></div>
            <p className="mt-2 text-xs text-slate2-500">Pixel-level, micro-averaged. These figures describe in-domain LEVIR-CD performance only — not performance on other sensors or resolutions.</p></>) : <Notice tone="warn">{met.data?.message ?? "Model evaluation pending — no validated checkpoint available."}</Notice>}
        </section>
        <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Training history</h2>
          {hist.length === 0 ? <div className="text-sm text-slate2-400">No training history recorded.</div> : (<div className="h-64"><ResponsiveContainer><LineChart data={hist}><CartesianGrid stroke="#1d2f4a" /><XAxis dataKey="epoch" tick={{ fill: "#aab6c8", fontSize: 11 }} /><YAxis tick={{ fill: "#aab6c8", fontSize: 11 }} /><Tooltip {...tip} /><Legend /><Line dataKey="train_loss" stroke="#e06c75" /><Line dataKey="val_f1" stroke="#3fb8af" /><Line dataKey="val_iou" stroke="#8ab4f8" /></LineChart></ResponsiveContainer></div>)}</section>
        {(met.data?.prediction_visualizations ?? []).length > 0 && <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Test predictions (before | after | ground truth | prediction)</h2><div className="grid gap-3 md:grid-cols-2">{met.data!.prediction_visualizations.map((n) => <img key={n} src={api.model.vizUrl(n)} alt={`Prediction ${n}`} className="w-full rounded border border-ink-700" loading="lazy" />)}</div></section>}
        <section className="card p-4"><h2 className="mb-2 text-sm font-semibold">Training (authorised background job)</h2>
          <div className="flex flex-wrap items-end gap-3"><div><label className="label" htmlFor="ep">Epochs</label><input id="ep" type="number" className="input !w-24" min={1} max={200} value={epochs} onChange={(e) => setEpochs(+e.target.value)} /></div>
            <button className="btn-primary" onClick={async () => { if (!window.confirm(`Start training for ${epochs} epochs? On CPU this takes hours and will overwrite models/siamese_unet/best.pt if validation F1 improves.`)) return; try { await api.model.startTraining({ epochs }); setMsg("Training started."); tr.reload(); } catch (e) { setErr((e as Error).message); } }}>Start training…</button></div>
          {msg && <div className="mt-2 text-sm text-mint">{msg}</div>}{err && <ErrorBox message={err} />}
          <p className="mt-2 text-xs text-slate2-500">CLI alternative: <code>python -m ml.training.train --data-root data/raw/LEVIR-CD</code> (see docs/ml-pipeline.md).</p>
          {(tr.data ?? []).slice(0, 3).map((t) => <div key={t.id} className="mt-2 text-xs text-slate2-300">{t.id}: {t.status} · {t.history.length}/{t.config.epochs} epochs {t.message}</div>)}</section>
      </div>
    </div>
  );
}
