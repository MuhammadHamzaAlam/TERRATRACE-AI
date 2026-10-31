import { useState } from "react";
import { ErrorBox, Notice, PageHeader, Pill, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

export default function Settings() {
  const s = useAsync(api.settings.get, []); const pv = useAsync(api.assistant.providers, []); const h = useAsync(api.health, []);
  const [err, setErr] = useState<string | null>(null); const [ok, setOk] = useState<string | null>(null);
  const [om, setOm] = useState(""); const [xm, setXm] = useState("");
  const save = async (b: Record<string, string>) => { setErr(null); setOk(null); try { await api.settings.putLlm(b); setOk("Saved."); s.reload(); pv.reload(); } catch (e) { setErr((e as Error).message); } };
  if (s.loading && !s.data) return <Spinner />;
  return (
    <div>
      <PageHeader title="Settings" subtitle="Secrets are read from server environment variables and are never displayed." />
      <div className="grid gap-4 p-6 lg:grid-cols-2">
        {s.error && <ErrorBox message={s.error} onRetry={s.reload} />}
        <section className="card space-y-3 p-4"><h2 className="text-sm font-semibold">LLM provider</h2>
          <div role="radiogroup" aria-label="Default provider" className="flex gap-2">{(["ollama", "grok"] as const).map((p) => <button key={p} role="radio" aria-checked={s.data?.llm.provider === p} className={s.data?.llm.provider === p ? "btn-primary" : "btn-ghost"} onClick={() => save({ provider: p })}>{p === "ollama" ? "Ollama (local)" : "Grok (xAI)"}</button>)}</div>
          {err && <div className="text-sm text-rose2">{err}</div>}{ok && <div className="text-sm text-mint">{ok}</div>}
          <div className="rounded-md border border-ink-700 p-3"><div className="mb-1 flex items-center justify-between text-sm font-medium">Ollama {pv.data && <Pill tone={pv.data.providers.ollama.available ? "good" : "bad"}>{pv.data.providers.ollama.available ? `v${pv.data.providers.ollama.version}` : "unavailable"}</Pill>}</div>
            <div className="text-xs text-slate2-400">Server: <code>{s.data?.llm.ollama.base_url}</code> (set via <code>OLLAMA_BASE_URL</code>) · Model: <code>{s.data?.llm.ollama.model ?? "not set"}</code></div>
            {pv.data && !pv.data.providers.ollama.available && <p className="mt-2 text-xs text-amber2">{pv.data.providers.ollama.message}</p>}
            <div className="mt-2 flex gap-2"><input className="input" placeholder="tool-capable model, e.g. qwen3:8b" value={om} onChange={(e) => setOm(e.target.value)} aria-label="Ollama model" /><button className="btn-ghost" disabled={!om} onClick={() => save({ ollama_model: om })}>Set</button></div>
            {(pv.data?.providers.ollama.models.length ?? 0) > 0 && <div className="mt-2 text-xs text-slate2-400">Installed: {pv.data!.providers.ollama.models.map((m) => m.name).join(", ")}</div>}</div>
          <div className="rounded-md border border-ink-700 p-3"><div className="mb-1 flex items-center justify-between text-sm font-medium">Grok (xAI) <Pill tone={s.data?.llm.grok.api_key_configured ? "good" : "warn"}>{s.data?.llm.grok.api_key_configured ? "API key configured" : "no API key"}</Pill></div>
            <div className="text-xs text-slate2-400">Key is set with <code>XAI_API_KEY</code> on the server and never leaves it. Model: <code>{s.data?.llm.grok.model ?? "not set"}</code></div>
            <div className="mt-2 flex gap-2"><input className="input" placeholder="xAI model id" value={xm} onChange={(e) => setXm(e.target.value)} aria-label="Grok model" /><button className="btn-ghost" disabled={!xm} onClick={() => save({ xai_model: xm })}>Set</button></div></div>
          <Notice>Reports, exports and dashboards work without any LLM provider.</Notice></section>
        <section className="card space-y-3 p-4"><h2 className="text-sm font-semibold">Connections</h2>
          <ul className="space-y-2 text-sm"><li className="flex justify-between"><span>Backend API</span>{h.error ? <Pill tone="bad">unreachable</Pill> : <Pill tone="good">{h.data?.status ?? "…"}</Pill>}</li>
            <li className="flex justify-between"><span>Sentinel-2 catalogue search</span><Pill tone="good">no credentials needed</Pill></li><li className="flex justify-between"><span>Sentinel-2 downloads</span><Pill tone={s.data?.satellite.download_available ? "good" : "warn"}>{s.data?.satellite.download_available ? "configured" : "needs CDSE credentials"}</Pill></li></ul>
          {s.data?.satellite.message && <Notice>{s.data.satellite.message}</Notice>}
          <h2 className="pt-2 text-sm font-semibold">Application</h2><dl className="text-sm"><div className="flex justify-between"><dt className="text-slate2-400">Max upload</dt><dd>{s.data?.limits.max_upload_mb} MB</dd></div></dl>
          <Notice tone="warn">This build has no user authentication: run it on a trusted machine/network. See docs/security.md.</Notice></section>
      </div>
    </div>
  );
}
