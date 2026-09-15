import { useEffect, useRef } from "react";
import "./RiskScore.css";

const COLOR_MAP = {
  low: { stroke: "var(--success)", track: "var(--success-light)" },
  medium: { stroke: "var(--warning)", track: "var(--warning-light)" },
  high: { stroke: "var(--danger)", track: "var(--danger-light)" },
};

export default function RiskScore({ score, level, size = 120, label = "Score" }) {
  const r = (size - 14) / 2;
  const C = 2 * Math.PI * r;
  const pct = Math.min(100, Math.max(0, score || 0));
  const offset = C * (1 - pct / 100);
  const colors = COLOR_MAP[(level || "").toLowerCase()] || COLOR_MAP.low;
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.strokeDashoffset = C;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          ref.current.style.strokeDashoffset = offset;
        });
      });
    }
  }, [offset, C]);

  return (
    <div className="risk-score" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={colors.track} strokeWidth="10" />
        <circle
          ref={ref}
          cx={size/2} cy={size/2} r={r}
          fill="none"
          stroke={colors.stroke}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C}
          transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition: "stroke-dashoffset .8s cubic-bezier(.4,0,.2,1)" }}
        />
      </svg>
      <div className="risk-score-inner">
        <span className="risk-score-value">{score ?? "—"}</span>
        <span className="risk-score-label">{label}</span>
      </div>
    </div>
  );
}
