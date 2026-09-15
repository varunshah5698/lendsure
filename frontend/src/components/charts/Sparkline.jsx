import { useMemo } from "react";

export default function Sparkline({ data = [], width = 220, height = 56, color = "var(--primary)" }) {
  const d = useMemo(() => {
    if (data.length < 2) return null;
    const vals = data.map((p) => (typeof p === "number" ? p : p.count ?? p.price ?? 0));
    const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
    const P = 4;
    const pts = vals.map((v, i) => [
      P + (i / (vals.length - 1)) * (width - 2 * P),
      height - P - ((v - min) / span) * (height - 2 * P),
    ]);
    const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    const last = pts[pts.length - 1];
    return { line, last };
  }, [data, width, height]);
  if (!d) return null;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <path d={d.line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx={d.last[0]} cy={d.last[1]} r="3" fill={color} />
    </svg>
  );
}
