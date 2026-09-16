import { motion } from "framer-motion";
import Icon from "../ui/Icon";
import "./MetricCard.css";

export default function MetricCard({ label, value, sub, trend, variant = "default", icon, index = 0 }) {
  return (
    <motion.div
      className={`metric-card metric-${variant}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.3), ease: "easeOut" }}
      whileHover={{ y: -3, transition: { duration: 0.15 } }}
      whileTap={{ scale: 0.98 }}
    >
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
    </motion.div>
  );
}
