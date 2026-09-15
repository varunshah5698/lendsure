import "./Badge.css";

const VARIANT_MAP = {
  LOW: "success", MEDIUM: "warning", HIGH: "danger",
  APPROVE: "success", APPROVE_WITH_CONDITIONS: "warning", REDUCE_AMOUNT: "info",
  MANUAL_REVIEW: "purple", REJECT: "danger",
  verified: "success", needs_review: "warning", suspicious: "danger",
  default: "default",
};

export default function Badge({ variant, children, className = "", dot = true, ...props }) {
  const v = VARIANT_MAP[variant] || variant || "default";
  return (
    <span className={`badge badge-${v} ${className}`} {...props}>
      {dot && <span className="badge-dot" />}
      {children}
    </span>
  );
}
