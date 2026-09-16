import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import "./CashFlowChart.css";

/**
 * Interactive cash-flow chart: animated Bars <-> Lines toggle, clickable
 * series chips, hover crosshair tooltip. Pure SVG + framer-motion, no deps.
 *
 * points: [{ label, values: { seriesKey: number } }]
 * series: [{ key, label, color }]
 */
export default function CashFlowChart({ title, subtitle, points = [], series = [], format = (v) => v }) {
  const [view, setView] = useState("bars"); // bars | lines
  const [hidden, setHidden] = useState({});
  const [hover, setHover] = useState(null);

  const visible = useMemo(() => series.filter((s) => !hidden[s.key]), [series, hidden]);
  const max = useMemo(() => {
    let m = 0;
    for (const p of points) for (const s of visible) m = Math.max(m, p.values?.[s.key] || 0);
    return m || 1;
  }, [points, visible]);

  const W = 680, H = 260, PL = 8, PR = 8, PT = 14, PB = 30;
  const iw = W - PL - PR, ih = H - PT - PB;
  const n = Math.max(points.length, 1);
  const slot = iw / n;
  const x = (i) => PL + slot * i + slot / 2;
  const y = (v) => PT + ih - (Math.min(v, max) / max) * ih;

  const linePath = (key) =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.values?.[key] || 0).toFixed(1)}`).join(" ");

  const toggleSeries = (key) => setHidden((h) => ({ ...h, [key]: !h[key] }));

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0, bd = Infinity;
    points.forEach((_, i) => {
      const d = Math.abs(x(i) - px);
      if (d < bd) { bd = d; best = i; }
    });
    setHover(best);
  };

  if (!points.length) return null;
  const bw = Math.min(34, (slot / Math.max(visible.length, 1)) - 8);

  return (
    <div className="cfc">
      <div className="cfc-head">
        <div>
          <div className="cfc-title">{title}</div>
          {subtitle && <div className="cfc-sub">{subtitle}</div>}
        </div>
        <div className="cfc-toggle" role="tablist" aria-label="Chart type">
          {["bars", "lines"].map((v) => (
            <button key={v} role="tab" aria-selected={view === v}
              className={`cfc-toggle-btn ${view === v ? "cfc-toggle-on" : ""}`}
              onClick={() => { setView(v); setHover(null); }}>
              {view === v && <motion.span layoutId={undefined} className="cfc-toggle-glow" />}
              {v === "bars" ? "Bars" : "Lines"}
            </button>
          ))}
        </div>
      </div>

      <div className="cfc-chips">
        {series.map((s) => (
          <button key={s.key} onClick={() => toggleSeries(s.key)}
            className={`cfc-chip ${hidden[s.key] ? "cfc-chip-off" : ""}`}
            aria-pressed={!hidden[s.key]}>
            <span className="cfc-dot" style={{ background: s.color }} />
            {s.label}
          </button>
        ))}
      </div>

      <div className="cfc-stage">
        <svg viewBox={`0 0 ${W} ${H}`} className="cfc-svg" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          {[0.25, 0.5, 0.75, 1].map((f) => (
            <line key={f} x1={PL} x2={W - PR} y1={PT + ih * (1 - f)} y2={PT + ih * (1 - f)}
              className="cfc-grid" />
          ))}
          <AnimatePresence mode="wait">
            {view === "bars" ? (
              <motion.g key="bars" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                {points.map((p, i) => (
                  <g key={i}>
                    {visible.map((s, j) => {
                      const v = p.values?.[s.key] || 0;
                      const h = Math.max((v / max) * ih, v > 0 ? 3 : 0);
                      const cx = x(i) + (j - (visible.length - 1) / 2) * bw;
                      return (
                        <motion.rect key={s.key} x={cx - bw / 2} width={bw} rx={4}
                          fill={s.color} initial={{ y: PT + ih, height: 0 }}
                          animate={{ y: PT + ih - h, height: h }}
                          transition={{ type: "spring", stiffness: 260, damping: 26, delay: i * 0.02 }}>
                          <title>{`${p.label} · ${s.label}: ${format(v)}`}</title>
                        </motion.rect>
                      );
                    })}
                  </g>
                ))}
              </motion.g>
            ) : (
              <motion.g key="lines" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                {visible.map((s) => (
                  <g key={s.key}>
                    <motion.path d={linePath(s.key)} fill="none" stroke={s.color}
                      strokeWidth={2.6} strokeLinecap="round"
                      initial={{ pathLength: 0 }} animate={{ pathLength: 1 }}
                      transition={{ duration: 0.7, ease: "easeOut" }} />
                    {points.map((p, i) => (
                      <motion.circle key={i} cx={x(i)} cy={y(p.values?.[s.key] || 0)} r={hover === i ? 5 : 3.4}
                        fill="#fff" stroke={s.color} strokeWidth={2.4}
                        initial={{ scale: 0 }} animate={{ scale: 1 }}
                        transition={{ delay: 0.05 * i, type: "spring", stiffness: 400, damping: 18 }}>
                        <title>{`${p.label} · ${s.label}: ${format(p.values?.[s.key] || 0)}`}</title>
                      </motion.circle>
                    ))}
                  </g>
                ))}
              </motion.g>
            )}
          </AnimatePresence>
          {hover != null && points[hover] && (
            <line x1={x(hover)} x2={x(hover)} y1={PT} y2={PT + ih} className="cfc-cross" />
          )}
          {points.map((p, i) => (
            <text key={i} x={x(i)} y={H - 8} textAnchor="middle" className="cfc-xlabel">
              {p.label.length > 7 ? p.label.slice(5) : p.label}
            </text>
          ))}
        </svg>
        {hover != null && points[hover] && (
          <div className="cfc-tip" style={{ left: `${(x(hover) / W) * 100}%` }}>
            <b>{points[hover].label}</b>
            {visible.map((s) => (
              <div key={s.key} className="cfc-tip-row">
                <span className="cfc-dot" style={{ background: s.color }} />
                {s.label}: <b>{format(points[hover].values?.[s.key] || 0)}</b>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
