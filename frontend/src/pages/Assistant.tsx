import { Bot, Clipboard, Loader2, MessageSquarePlus, Send, Trash2, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Empty, Notice, PageHeader, Pill } from "../components/ui";
import { useChat } from "../features/assistant/useChat";
import { useApp } from "../hooks/AppState";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

const SUGGESTIONS = ["Summarize this analysis.", "Which cluster has the most detections?", "Compare the latest two observations.", "Show pending verification events.", "Show all detections above 85% confidence.", "What limitations should I consider when interpreting these results?", "Generate an executive summary."];

export default function Assistant() {
  const app = useApp();
  const prov = useAsync(api.assistant.providers, []);
  const hist = useAsync(() => (app.projectId ? api.assistant.list(app.projectId) : Promise.resolve([])), [app.projectId]);
  const chat = useChat(app.projectId, app.analysisId, app.applyAction);
  const [provider, setProvider] = useState(""); const [model, setModel] = useState(""); const [text, setText] = useState(""); const [offline, setOffline] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { if (prov.data && !provider) { setProvider(prov.data.default); } }, [prov.data, provider]);
  useEffect(() => { const p = prov.data?.providers[provider]; if (p) setModel(p.selected_model ?? p.models[0]?.name ?? ""); }, [provider, prov.data]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [chat.msgs]);
  useEffect(() => { chat.fresh(); /* new project -> new conversation */ }, [app.projectId]); // eslint-disable-line
  const info = prov.data?.providers[provider];
  const submit = async (t = text) => { if (!t.trim()) return; setText(""); await chat.send(t, provider, model); hist.reload(); };
  const selectModel = async (m: string) => { setModel(m); try { await api.settings.putLlm(provider === "ollama" ? { provider, ollama_model: m } : { provider, xai_model: m }); } catch { /* shown on next call */ } };

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="TerraTrace Intelligence Assistant" subtitle="Answers come from tool calls against your project's real records — not from the model's memory." />
      <div className="grid min-h-0 flex-1 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="min-h-0 space-y-4 overflow-auto border-r border-ink-700 p-4">
          <div><label className="label" htmlFor="pv">Provider</label><select id="pv" className="input" value={provider} onChange={(e) => setProvider(e.target.value)}><option value="ollama">Ollama (local)</option><option value="grok">Grok (xAI, optional)</option></select></div>
          <div><label className="label" htmlFor="md">Model</label>
            {info?.models.length ? <select id="md" className="input" value={model} onChange={(e) => selectModel(e.target.value)}>{info.models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}</select> : <input id="md" className="input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="model name" onBlur={() => model && selectModel(model)} />}</div>
          <div className="text-xs">{prov.loading ? "Checking provider…" : info?.available ? <Pill tone="good">available</Pill> : <Pill tone="bad">unavailable</Pill>}</div>
          {info && !info.available && <Notice tone="warn">{info.message}</Notice>}
          <div className="rounded-md border border-ink-700 p-2 text-xs text-slate2-300"><div className="label">Context</div>Project: {app.project?.name ?? "—"}<br />Analysis: {app.analysis ? `${app.analysis.id} (${app.analysis.before_date}→${app.analysis.after_date})` : "none"}{app.filter.ids && <><br />Filter: {app.filter.ids.length} events</>}</div>
          <button className="btn-ghost w-full" onClick={chat.fresh}><MessageSquarePlus className="h-4 w-4" />New conversation</button>
          <div><div className="label">Previous conversations</div><ul className="space-y-1">{(hist.data ?? []).slice(0, 12).map((c) => (<li key={c.id} className="flex items-center gap-1"><button className="flex-1 truncate rounded px-2 py-1 text-left text-xs hover:bg-ink-700" onClick={() => chat.open(c.id)}>{c.title}</button></li>))}{(hist.data ?? []).length === 0 && <li className="text-xs text-slate2-500">None yet</li>}</ul></div>
          {app.analysisId && <button className="btn-ghost w-full text-xs" onClick={async () => { try { setOffline((await api.assistant.offlineSummary(app.analysisId!)).text); } catch (e) { setOffline((e as Error).message); } }}>Deterministic summary (no LLM)</button>}
          {offline && <pre className="whitespace-pre-wrap rounded border border-ink-700 p-2 text-xs text-slate2-300">{offline}</pre>}
        </aside>
        <section className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4" aria-live="polite">
            {!app.projectId ? <Empty title="Select a project" /> : chat.msgs.length === 0 ? (
              <div className="mx-auto max-w-xl pt-8 text-center"><Bot className="mx-auto h-8 w-8 text-signal" /><h2 className="mt-2 text-base font-semibold">Ask about your analyses</h2><p className="mb-4 text-sm text-slate2-400">The assistant retrieves events, clusters, histories and reports through approved read-only tools. It cannot confirm or reject detections.</p>
                <div className="flex flex-wrap justify-center gap-2">{SUGGESTIONS.map((s) => <button key={s} className="btn-ghost text-xs" onClick={() => submit(s)} disabled={chat.busy}>{s}</button>)}</div></div>
            ) : chat.msgs.map((m) => (
              <div key={m.id} className={m.role === "user" ? "ml-auto max-w-2xl" : "max-w-3xl"}>
                <div className={`rounded-lg p-3 text-sm ${m.role === "user" ? "bg-ink-700" : "card"}`}>
                  {m.tools.length > 0 && <ul className="mb-2 space-y-1">{m.tools.map((t, i) => (<li key={i} className="flex items-center gap-1.5 text-xs text-slate2-400">{t.running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wrench className={`h-3 w-3 ${t.ok ? "text-signal" : "text-rose2"}`} />}<span className="font-mono">{t.name}</span>{t.summary && <span>— {t.summary}</span>}</li>))}</ul>}
                  <div className="whitespace-pre-wrap">{m.content}{m.streaming && !m.content && !m.error && <span className="text-slate2-500">Thinking…</span>}</div>
                  {m.error && <div role="alert" className="mt-2 rounded border border-rose2/40 bg-rose2/10 p-2 text-xs text-rose2"><b>{m.error.code.replace(/_/g, " ")}:</b> {m.error.message}</div>}
                </div>
                {m.role === "assistant" && m.content && !m.streaming && <button className="mt-1 flex items-center gap-1 text-xs text-slate2-500 hover:text-slate2-300" onClick={() => navigator.clipboard?.writeText(m.content)}><Clipboard className="h-3 w-3" />Copy</button>}
              </div>))}
            <div ref={end} />
          </div>
          <form className="flex gap-2 border-t border-ink-700 p-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <label className="sr-only" htmlFor="msg">Message</label>
            <input id="msg" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={app.projectId ? "Ask about events, clusters, comparisons, reports…" : "Select a project first"} disabled={!app.projectId || chat.busy} maxLength={4000} />
            <button className="btn-primary" type="submit" disabled={!text.trim() || chat.busy || !app.projectId}><Send className="h-4 w-4" />Send</button>
            {chat.busy && <button type="button" className="btn-ghost" onClick={chat.stop}>Stop</button>}
            {chat.msgs.length > 0 && <button type="button" className="btn-ghost" aria-label="Clear conversation" onClick={async () => { if (chat.conv) { await api.assistant.remove(chat.conv.id); hist.reload(); } chat.fresh(); }}><Trash2 className="h-4 w-4" /></button>}
          </form>
        </section>
      </div>
    </div>
  );
}
