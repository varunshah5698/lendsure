import { useEffect, useState } from "react";
import "./kit.css";

export default function ProgressBar({ label, value, max = 100, display, color = "var(--primary)" }) {
  const [w, setW] = useState(0);
  const pct = Math.max(0, Math.min(100, ((value ?? 0) / max) * 100));
  useEffect(() => {
    const t = requestAnimationFrame(() => requestAnimationFrame(() => setW(pct)));
    return () => cancelAnimationFrame(t);
  }, [pct]);
  return (
    <div className="kit-progress">
      <div className="kit-progress-head">
        <span className="kit-progress-label">{label}</span>
        <span className="kit-progress-val">{display ?? `${Math.round(pct)}%`}</span>
      </div>
      <div className="kit-progress-track">
        <div className="kit-progress-fill" style={{ width: `${w}%`, background: color }} />
      </div>
    </div>
  );
}
