import { useEffect, useState } from "react";
import "./Gauge.css";

export default function Gauge({ label, value, max = 100, display, color }) {
  const [fill, setFill] = useState(0);
  const pct = Math.max(0, Math.min(100, ((value ?? 0) / max) * 100));
  useEffect(() => {
    const t = requestAnimationFrame(() => requestAnimationFrame(() => setFill(pct)));
    return () => cancelAnimationFrame(t);
  }, [pct]);
  const R = 70;
  const C = Math.PI * R;
  return (
    <div className="gauge">
      <svg viewBox="0 0 160 92" className="gauge-svg">
        <path d="M 10 82 A 70 70 0 0 1 150 82" fill="none" stroke="rgba(148,163,184,.18)" strokeWidth="12" strokeLinecap="round" />
        <path d="M 10 82 A 70 70 0 0 1 150 82" fill="none" stroke={color || "var(--primary)"}
          strokeWidth="12" strokeLinecap="round" strokeDasharray={C}
          strokeDashoffset={C * (1 - fill / 100)} className="gauge-arc" />
      </svg>
      <div className="gauge-center">
        <div className="gauge-value">{display}</div>
        <div className="gauge-label">{label}</div>
      </div>
    </div>
  );
}
