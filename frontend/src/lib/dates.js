/* One shared timestamp formatter. Storage stays UTC; display is IST
 * with an explicit label so nobody mistakes the zone. Replaces the
 * scattered `.slice(0, 16)` formatting that used to live in every page. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function pad(n) {
  return String(n).padStart(2, "0");
}

export function formatDate(ts, opts = {}) {
  if (!ts) return "—";
  // Stored as naive UTC ("2026-09-13T21:15:40.379720" or with a space).
  const d = new Date(String(ts).replace(" ", "T") + (String(ts).endsWith("Z") ? "" : "Z"));
  if (Number.isNaN(d.getTime())) return "—";
  // IST = UTC+5:30, no DST — fixed offset, safe to compute by hand.
  const ist = new Date(d.getTime() + (5.5 * 3600 + d.getTimezoneOffset() * 60) * 1000);
  const date = `${pad(ist.getDate())} ${MONTHS[ist.getMonth()]} ${ist.getFullYear()}`;
  if (opts.dateOnly) return `${date} IST`;
  return `${date}, ${pad(ist.getHours())}:${pad(ist.getMinutes())} IST`;
}

export function timeAgo(ts) {
  if (!ts) return "—";
  const d = new Date(String(ts).replace(" ", "T") + (String(ts).endsWith("Z") ? "" : "Z"));
  if (Number.isNaN(d.getTime())) return "—";
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return formatDate(ts, { dateOnly: true });
}
