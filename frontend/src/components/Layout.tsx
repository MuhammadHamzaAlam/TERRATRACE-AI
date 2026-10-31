import { BarChart3, Bot, ClipboardCheck, FileText, FlaskConical, FolderKanban, Gauge, Globe2, GitCompare, Layers, Menu, PlusSquare, Settings as Cog, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useApp } from "../hooks/AppState";
import { reviewer } from "../services/api";
import { ErrorBox } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/new-analysis", label: "New analysis", icon: PlusSquare },
  { to: "/workspace", label: "Workspace", icon: Layers },
  { to: "/explorer", label: "Geo explorer", icon: Globe2 },
  { to: "/temporal", label: "Temporal", icon: GitCompare },
  { to: "/review", label: "Review center", icon: ClipboardCheck },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/assistant", label: "Assistant", icon: Bot },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/model", label: "Model lab", icon: FlaskConical },
  { to: "/settings", label: "Settings", icon: Cog },
];

export default function Layout() {
  const [open, setOpen] = useState(false);
  const app = useApp();
  const [who, setWho] = useState(reviewer.get());
  return (
    <div className="flex h-full">
      <aside className={`fixed inset-y-0 left-0 z-30 w-56 transform border-r border-ink-700 bg-ink-950 transition-transform md:static md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center gap-2 px-4 py-4">
          <svg viewBox="0 0 32 32" className="h-7 w-7"><path d="M6 22 L16 8 L26 22" fill="none" stroke="#3fb8af" strokeWidth="2.5" strokeLinejoin="round" /><path d="M10 22h12" stroke="#e0a458" strokeWidth="2.5" strokeLinecap="round" /></svg>
          <div><div className="text-sm font-semibold leading-tight tracking-wide">TerraTrace AI</div><div className="text-[10px] uppercase tracking-widest text-slate2-500">Change intelligence</div></div>
          <button className="ml-auto md:hidden" aria-label="Close menu" onClick={() => setOpen(false)}><X className="h-4 w-4" /></button>
        </div>
        <nav className="space-y-0.5 px-2" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm ${isActive ? "bg-ink-700 text-white" : "text-slate2-300 hover:bg-ink-800"}`}>
              <Icon className="h-4 w-4" />{label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-ink-700 bg-ink-950 px-4 py-2">
          <button className="md:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button>
          <label className="flex items-center gap-2 text-xs text-slate2-400">Project
            <select className="input !w-48" value={app.projectId ?? ""} onChange={(e) => app.setProjectId(e.target.value || null)} aria-label="Active project">
              {app.projects.length === 0 && <option value="">No projects</option>}
              {app.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-slate2-400">Analysis
            <select className="input !w-60" value={app.analysisId ?? ""} onChange={(e) => app.setAnalysisId(e.target.value || null)} aria-label="Active analysis">
              {app.analyses.length === 0 && <option value="">No analyses</option>}
              {app.analyses.map((a) => <option key={a.id} value={a.id}>{a.id} · {a.before_date}→{a.after_date} · {a.status}</option>)}
            </select>
          </label>
          <label className="ml-auto flex items-center gap-2 text-xs text-slate2-400">Reviewer
            <input className="input !w-32" value={who} onChange={(e) => { setWho(e.target.value); reviewer.set(e.target.value || "local-analyst"); }} aria-label="Reviewer name" />
          </label>
        </header>
        <main className="min-h-0 flex-1 overflow-auto">
          {app.backendError && <ErrorBox message={app.backendError} onRetry={app.reloadProjects} />}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
