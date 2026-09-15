import Badge from "../ui/Badge";

export default function RiskBadge({ level, score }) {
  if (!level) return <span className="text-muted">—</span>;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Badge variant={level}>{level}</Badge>
      {score != null && <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{score}/100</span>}
    </div>
  );
}
