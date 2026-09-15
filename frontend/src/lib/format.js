export function timeAgo(ts) {
  if (!ts) return "";
  const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`;
  return new Date(ts).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtInt(n) {
  return n == null ? "—" : Number(n).toLocaleString("en-IN");
}

export function fmtPct(n, digits = 1) {
  return n == null ? "—" : `${Number(n).toFixed(digits)}%`;
}

export function fmtSigned(n, digits = 2) {
  if (n == null) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;
}

export function initials(name) {
  return (name || "?").split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

const AVATAR_COLORS = [
  ["#6366f1", "#4338ca"], ["#0ea5e9", "#0369a1"], ["#10b981", "#047857"],
  ["#f59e0b", "#b45309"], ["#ec4899", "#be185d"], ["#8b5cf6", "#6d28d9"],
];
export function avatarGradient(name) {
  let h = 0;
  for (const c of String(name || "?")) h = (h * 31 + c.charCodeAt(0)) % 997;
  const [a, b] = AVATAR_COLORS[h % AVATAR_COLORS.length];
  return `linear-gradient(135deg, ${a}, ${b})`;
}
