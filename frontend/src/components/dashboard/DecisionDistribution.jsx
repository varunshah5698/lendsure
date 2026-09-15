import "./DecisionDistribution.css";

const COLORS = {
  APPROVE: "var(--success)",
  APPROVE_WITH_CONDITIONS: "var(--warning)",
  REDUCE_AMOUNT: "var(--info)",
  MANUAL_REVIEW: "var(--purple)",
  REJECT: "var(--danger)",
};

const LABELS = {
  APPROVE: "Approve",
  APPROVE_WITH_CONDITIONS: "Conditional",
  REDUCE_AMOUNT: "Reduce Amount",
  MANUAL_REVIEW: "Manual Review",
  REJECT: "Reject",
};

export default function DecisionDistribution({ data = {} }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0);
  const total = entries.reduce((a, [, v]) => a + v, 0) || 1;

  if (!entries.length) return <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No decisions recorded.</div>;

  return (
    <div className="decision-dist">
      <div className="decision-bar">
        {entries.map(([k, v]) => (
          <div
            key={k}
            className="decision-bar-seg"
            style={{ width: `${(v / total) * 100}%`, background: COLORS[k] || "var(--text-muted)" }}
            title={`${LABELS[k] || k}: ${v}`}
          />
        ))}
      </div>
      <div className="decision-legend">
        {entries.map(([k, v]) => (
          <div key={k} className="decision-legend-item">
            <span className="decision-dot" style={{ background: COLORS[k] }} />
            <span className="decision-label">{LABELS[k] || k}</span>
            <span className="decision-count">{v}</span>
            <span className="decision-pct">{((v / total) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
