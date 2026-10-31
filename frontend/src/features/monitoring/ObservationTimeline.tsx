import type { Timeline } from "../../types/api";

export default function ObservationTimeline({ tl, onOpen }: { tl: Timeline; onOpen?: (analysisId: string) => void }) {
  if (tl.observations.length === 0) return <div className="text-sm text-slate2-400">No observations yet.</div>;
  const ts = tl.observations.map((o) => new Date(o.date).getTime());
  const min = Math.min(...ts), max = Math.max(...ts), span = Math.max(max - min, 1);
  const x = (d: string) => (tl.observations.length === 1 ? 50 : 4 + ((new Date(d).getTime() - min) / span) * 92);
  return (
    <div>
      <svg viewBox="0 0 100 26" className="w-full" role="img" aria-label="Observation timeline" preserveAspectRatio="none" style={{ height: 120 }}>
        <line x1="2" y1="13" x2="98" y2="13" stroke="#2a4163" strokeWidth="0.4" />
        {tl.analyses.map((a) => (
          <path key={a.analysis_id} d={`M${x(a.before_date)} 13 Q ${(x(a.before_date) + x(a.after_date)) / 2} 3 ${x(a.after_date)} 13`} fill="none" stroke="#3fb8af" strokeWidth="0.5" opacity="0.7"
            onClick={() => onOpen?.(a.analysis_id)} style={{ cursor: "pointer" }}><title>{`${a.analysis_id}: ${a.before_date} → ${a.after_date}, ${a.n_events} candidate events`}</title></path>
        ))}
        {tl.observations.map((o) => (<g key={o.id}><circle cx={x(o.date)} cy="13" r="1.3" fill="#e0a458" /><text x={x(o.date)} y="21" fontSize="2.6" textAnchor="middle" fill="#aab6c8">{o.date}</text></g>))}
      </svg>
      <p className="text-xs text-slate2-500">Arcs are analyses between two observations. {tl.note}</p>
    </div>
  );
}
