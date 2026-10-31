import { useCallback, useRef, useState } from "react";
import { api, reviewer } from "../../services/api";
import type { Conversation } from "../../types/api";

export interface ToolEvent { name: string; ok?: boolean; summary?: string; running: boolean }
export interface ChatMsg { id: string; role: "user" | "assistant"; content: string; tools: ToolEvent[]; error?: { code: string; message: string }; streaming?: boolean }

/** Parse a Server-Sent-Events stream from fetch(). */
export async function* readSSE(res: Response): AsyncGenerator<Record<string, unknown>> {
  const reader = res.body!.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { done, value } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      if (chunk.startsWith("data: ")) { try { yield JSON.parse(chunk.slice(6)); } catch { /* skip malformed */ } }
    }
  }
}

export function useChat(projectId: string | null, analysisId: string | null, applyAction: (a: unknown) => boolean) {
  const [conv, setConv] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);

  const open = useCallback(async (id: string) => {
    const c = await api.assistant.get(id); setConv(c);
    setMsgs((c.messages ?? []).map((m) => ({ id: String(m.id), role: m.role, content: m.content, tools: [] })));
  }, []);
  const fresh = useCallback(() => { setConv(null); setMsgs([]); }, []);

  const send = useCallback(async (text: string, provider: string, model: string) => {
    if (!projectId || !text.trim() || busy) return;
    setBusy(true);
    let c = conv;
    try { if (!c) { c = await api.assistant.create(projectId, provider, model); setConv(c); } } catch (e) {
      setMsgs((m) => [...m, { id: crypto.randomUUID(), role: "assistant", content: "", tools: [], error: { code: "backend", message: (e as Error).message } }]); setBusy(false); return;
    }
    const aid = crypto.randomUUID();
    setMsgs((m) => [...m, { id: crypto.randomUUID(), role: "user", content: text, tools: [] }, { id: aid, role: "assistant", content: "", tools: [], streaming: true }]);
    const upd = (f: (m: ChatMsg) => ChatMsg) => setMsgs((all) => all.map((m) => (m.id === aid ? f(m) : m)));
    abort.current = new AbortController();
    try {
      const res = await fetch(api.assistant.messageUrl(c.id), { method: "POST", signal: abort.current.signal, headers: { "Content-Type": "application/json", "X-Reviewer": reviewer.get() },
        body: JSON.stringify({ message: text, analysis_id: analysisId, provider, model: model || undefined, stream: true }) });
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(typeof j.detail === "string" ? j.detail : res.statusText); }
      for await (const ev of readSSE(res)) {
        switch (ev.type) {
          case "token": upd((m) => ({ ...m, content: m.content + String(ev.text) })); break;
          case "tool_start": upd((m) => ({ ...m, tools: [...m.tools, { name: String(ev.name), running: true }] })); break;
          case "tool_result": upd((m) => ({ ...m, tools: m.tools.map((t, i) => (i === m.tools.length - 1 || t.name === ev.name) && t.running ? { ...t, running: false, ok: Boolean(ev.ok), summary: String(ev.summary) } : t) })); break;
          case "action": applyAction(ev.action); break; // validated against the allowlist inside applyAction
          case "error": upd((m) => ({ ...m, error: { code: String(ev.code), message: String(ev.message) } })); break;
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") upd((m) => ({ ...m, error: { code: "network", message: (e as Error).message } }));
    } finally { upd((m) => ({ ...m, streaming: false })); setBusy(false); }
  }, [projectId, analysisId, conv, busy, applyAction]);

  const stop = () => abort.current?.abort();
  return { conv, msgs, busy, send, stop, open, fresh, setMsgs };
}
