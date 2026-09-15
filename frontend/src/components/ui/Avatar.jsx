import { initials, avatarGradient } from "../../lib/format";
import "./kit.css";

export default function Avatar({ name, size = 36, style }) {
  return (
    <div
      className="kit-avatar"
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.34), background: avatarGradient(name), ...style }}
      aria-hidden="true"
    >
      {initials(name)}
    </div>
  );
}
