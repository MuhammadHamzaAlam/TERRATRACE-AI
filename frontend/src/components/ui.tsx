import { AlertTriangle, Info, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { REVIEW_LABELS, type ReviewStatus } from "../types/api";
import { STATUS_COLOR } from "../lib/format";

export const Spinner = ({ label = "Loading" }: { label?: string }) => (
  <div role="status" className="flex items-center gap-2 p-6 text-sm text-slate2-400"><Loader2 className="h-4 w-4 animate-spin" /> {label}…</div>
);
export const ErrorBox = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div role="alert" className="m-4 flex items-start gap-2 rounded-md border border-rose2/40 bg-rose2/10 p-3 text-sm text-rose2">
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><div className="flex-1">{message}</div>
    {onRetry && <button className="btn-ghost !py-0.5" onClick={onRetry}>Retry</button>}
  </div>
);
export const Notice = ({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) => (
  <div className={`flex items-start gap-2 rounded-md border p-3 text-sm ${tone === "warn" ? "border-amber2/40 bg-amber2/10 text-amber2" : "border-ink-600 bg-ink-800 text-slate2-300"}`}>
    {tone === "warn" ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> : <Info className="mt-0.5 h-4 w-4 shrink-0" />}<div>{children}</div>
  </div>
);
export const Empty = ({ title, hint, children }: { title: string; hint?: string; children?: ReactNode }) => (
  <div className="flex flex-col items-center gap-2 p-10 text-center"><div className="text-sm font-medium text-slate2-300">{title}</div>{hint && <div className="max-w-md text-xs text-slate2-400">{hint}</div>}{children}</div>
);
export const PageHeader = ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) => (
  <div className="flex flex-wrap items-end justify-between gap-3 border-b border-ink-700 px-6 py-4">
    <div><h1 className="text-lg font-semibold tracking-tight">{title}</h1>{subtitle && <p className="mt-0.5 text-sm text-slate2-400">{subtitle}</p>}</div>
    <div className="flex items-center gap-2">{actions}</div>
  </div>
);
export const Stat = ({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) => (
  <div className="card p-4"><div className="text-xs uppercase tracking-wide text-slate2-400">{label}</div><div className="mt-1 font-mono text-2xl font-medium">{value}</div>{hint && <div className="mt-1 text-xs text-slate2-500">{hint}</div>}</div>
);
export const StatusBadge = ({ status }: { status: ReviewStatus }) => (
  <span className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs" style={{ borderColor: STATUS_COLOR[status] + "66", color: STATUS_COLOR[status] }}>
    <span className="h-1.5 w-1.5 rounded-full" style={{ background: STATUS_COLOR[status] }} />{REVIEW_LABELS[status]}
  </span>
);
export const Progress = ({ value }: { value: number }) => (
  <div className="h-1.5 w-full overflow-hidden rounded bg-ink-700" role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
    <div className="h-full bg-signal transition-all" style={{ width: `${Math.round(value * 100)}%` }} />
  </div>
);
export const Pill = ({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" }) => {
  const c = { neutral: "border-ink-600 text-slate2-300", good: "border-mint/40 text-mint", warn: "border-amber2/40 text-amber2", bad: "border-rose2/40 text-rose2" }[tone];
  return <span className={`inline-block rounded border px-1.5 py-0.5 text-xs ${c}`}>{children}</span>;
};
export const NeedProject = ({ children, need = "project" }: { children: ReactNode; need?: "project" | "analysis" }) => children;
