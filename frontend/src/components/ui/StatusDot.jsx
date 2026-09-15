import "./kit.css";

export default function StatusDot({ label = "LIVE", amber = false }) {
  return (
    <span className={`kit-statusdot ${amber ? "kit-statusdot-amber" : ""}`}>
      <i />{label}
    </span>
  );
}
