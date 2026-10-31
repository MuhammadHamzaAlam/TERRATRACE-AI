export const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);
export const num = (v: number | null | undefined, d = 0) => (v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
export const area = (m2: number | null | undefined, px?: number) => (m2 != null ? `${num(m2, 1)} m²` : px != null ? `${num(px)} px` : "—");
export const date = (s: string | null | undefined) => (s ? new Date(s).toISOString().slice(0, 10) : "—");
export const ago = (s: string) => {
  const d = (Date.now() - new Date(s + (s.endsWith("Z") ? "" : "Z")).getTime()) / 1000;
  if (d < 60) return "just now"; if (d < 3600) return `${Math.floor(d / 60)} min ago`; if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return `${Math.floor(d / 86400)} d ago`;
};
export const STATUS_COLOR: Record<string, string> = { pending: "#e0a458", confirmed: "#7bd88f", rejected: "#e06c75", needs_investigation: "#8ab4f8" };
