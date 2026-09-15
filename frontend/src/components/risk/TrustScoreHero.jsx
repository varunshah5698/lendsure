import { useMemo } from "react";
import useCountUp from "../../hooks/useCountUp";
import ProgressBar from "../ui/ProgressBar";
import "./TrustScoreHero.css";

function grade(score) {
  if (score >= 85) return { label: "Excellent", cls: "tsh-grade-excellent" };
  if (score >= 70) return { label: "Good", cls: "tsh-grade-good" };
  if (score >= 50) return { label: "Fair", cls: "tsh-grade-fair" };
  return { label: "Needs Care", cls: "tsh-grade-poor" };
}

export default function TrustScoreHero({ score = 0, confidence, factors = [], analysisId }) {
  const animated = useCountUp(score, 1400);
  const g = grade(score);
  const R = 84;
  const C = 2 * Math.PI * R;
  const filled = useMemo(() => Math.max(0, Math.min(100, score)) / 100, [score]);

  return (
    <div className="tsh">
      <div className="tsh-glow" aria-hidden="true" />
      <div className="tsh-main">
        <div className="tsh-ring-wrap">
          <svg viewBox="0 0 200 200" className="tsh-ring">
            <defs>
              <linearGradient id="tshGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#22d3ee" />
                <stop offset="55%" stopColor="#6366f1" />
                <stop offset="100%" stopColor="#a855f7" />
              </linearGradient>
            </defs>
            <circle cx="100" cy="100" r={R} fill="none" stroke="rgba(148,163,184,.15)" strokeWidth="13" />
            <circle
              cx="100" cy="100" r={R} fill="none" stroke="url(#tshGrad)" strokeWidth="13"
              strokeLinecap="round" strokeDasharray={C}
              strokeDashoffset={C * (1 - filled)}
              transform="rotate(-90 100 100)" className="tsh-arc"
            />
            {[0, 25, 50, 75].map((t) => {
              const a = (t / 100) * 2 * Math.PI - Math.PI / 2;
              return <circle key={t} cx={100 + R * Math.cos(a)} cy={100 + R * Math.sin(a)} r="2.5" fill="rgba(148,163,184,.4)" />;
            })}
          </svg>
          <div className="tsh-center">
            <div className="tsh-score">{animated}</div>
            <div className="tsh-of">/ 100</div>
            <div className={`tsh-grade ${g.cls}`}>{g.label}</div>
          </div>
        </div>
        <div className="tsh-meta">
          <div className="tsh-title">Trust Score</div>
          {analysisId != null && <div className="tsh-sub">Analysis #{analysisId} · 66 signals evaluated</div>}
          {confidence != null && (
            <div className="tsh-conf">
              <span>Model confidence</span>
              <b>{confidence}%</b>
            </div>
          )}
          <div className="tsh-scale">
            <span>0</span>
            <div className="tsh-scale-bar" />
            <span>100</span>
          </div>
        </div>
      </div>
      {factors.length > 0 && (
        <div className="tsh-factors">
          <div className="tsh-factors-title">What shapes this score</div>
          {factors.slice(0, 5).map((f, i) => (
            <ProgressBar
              key={f.code || f.title || i}
              label={`${f.impact === "lowers" ? "− " : "+ "}${f.title || f.code}`}
              value={Math.abs(f.weight ?? f.score ?? 0)}
              max={25}
              display={`${f.impact === "lowers" ? "−" : "+"}${Math.abs(Math.round(f.weight ?? f.score ?? 0))}`}
              color={f.impact === "lowers" ? "var(--danger)" : "var(--success)"}
            />
          ))}
        </div>
      )}
    </div>
  );
}
