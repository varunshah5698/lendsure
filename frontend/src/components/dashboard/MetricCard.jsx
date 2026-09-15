import { useEffect, useRef } from "react";
import Icon from "../ui/Icon";
import "./MetricCard.css";

export default function MetricCard({ label, value, sub, trend, variant = "default", icon }) {
  const ref = useRef(null);
  const hasAnimated = useRef(false);

  useEffect(() => {
    if (ref.current && !hasAnimated.current) {
      hasAnimated.current = true;
      ref.current.style.opacity = "0";
      ref.current.style.transform = "translateY(6px)";
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          ref.current.style.transition = "all .3s ease";
          ref.current.style.opacity = "1";
          ref.current.style.transform = "none";
        });
      });
    }
  }, []);

  return (
    <div className={`metric-card metric-${variant}`} ref={ref}>
      <div className="metric-row">
        <div className="metric-text">
          <div className="metric-value">{value ?? "—"}</div>
          <div className="metric-label">{label}</div>
        </div>
        {icon && <span className="metric-chip" aria-hidden="true"><Icon name={icon} size={18} /></span>}
      </div>
      <div className="metric-foot">
        {sub && <div className="metric-sub">{sub}</div>}
        {trend && <div className={`metric-trend ${trend > 0 ? "trend-up" : "trend-down"}`}>
          {trend > 0 ? "↑" : "↓"} {Math.abs(trend)}%
        </div>}
      </div>
    </div>
  );
}
