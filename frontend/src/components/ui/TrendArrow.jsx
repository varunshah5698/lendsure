import "./kit.css";

export default function TrendArrow({ value, suffix = "%", invert = false }) {
  if (value == null) return <span className="kit-trend kit-trend-flat">—</span>;
  const v = Number(value);
  const good = invert ? v < 0 : v >= 0;
  const cls = v === 0 ? "kit-trend-flat" : good ? "kit-trend-up" : "kit-trend-down";
  const arrow = v > 0 ? "▲" : v < 0 ? "▼" : "●";
  return <span className={`kit-trend ${cls}`}>{arrow} {v >= 0 ? "+" : ""}{v.toFixed(2)}{suffix}</span>;
}
