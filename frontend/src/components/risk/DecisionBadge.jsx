import Badge from "../ui/Badge";

const LABELS = {
  APPROVE: "Approve",
  APPROVE_WITH_CONDITIONS: "Approve with Conditions",
  REDUCE_AMOUNT: "Reduce Amount",
  MANUAL_REVIEW: "Manual Review",
  REJECT: "Reject",
};

export default function DecisionBadge({ decision, size = "md" }) {
  if (!decision) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  return <Badge variant={decision}>{LABELS[decision] || decision.replace(/_/g, " ")}</Badge>;
}
