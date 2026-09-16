/**
 * LendSure mark — "Rupee Bold" edition. An unmistakable geometric rupee:
 * wide twin bars, full stem, deep bowl — with a growth-badge arrow riding
 * the ring. Lime gradients on deep forest. One SVG, favicon to billboard.
 */
export default function Logo({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="LendSure logo"
      style={{ flexShrink: 0, filter: "drop-shadow(0 3px 8px rgba(10,56,38,.35))" }}>
      <defs>
        <radialGradient id="lsD4" cx="0.38" cy="0.32" r="0.95">
          <stop offset="0" stopColor="#1e6845" />
          <stop offset="0.6" stopColor="#0b2e21" />
          <stop offset="1" stopColor="#050f0b" />
        </radialGradient>
        <linearGradient id="lsR4" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f0ffb8" />
          <stop offset="0.5" stopColor="#a3e635" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
        <linearGradient id="lsG4" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f4ffd6" />
          <stop offset="0.55" stopColor="#bef264" />
          <stop offset="1" stopColor="#34d399" />
        </linearGradient>
      </defs>

      {/* coin */}
      <circle cx="30" cy="34" r="27" fill="url(#lsD4)" />
      <circle cx="30" cy="34" r="27" fill="none" stroke="url(#lsR4)"
        strokeWidth="3.4" />

      {/* classic geometric rupee */}
      <rect x="12" y="17" width="29" height="6.4" rx="3.2" fill="url(#lsG4)" />
      <rect x="12" y="26.6" width="22" height="5.4" rx="2.7" fill="url(#lsG4)" />
      <rect x="12" y="17" width="6.4" height="30" rx="3.2" fill="url(#lsG4)" />
      <path d="M18.4 26.6 C30 26.6 36 31 36 36.2 C36 41.4 30 44.2 23.5 44.8"
        fill="none" stroke="url(#lsG4)" strokeWidth="5.4"
        strokeLinecap="round" />

      {/* growth badge */}
      <circle cx="49" cy="14.5" r="9" fill="#0b2e21" stroke="url(#lsR4)"
        strokeWidth="2.6" />
      <path d="M49 18.8 V10.4 M45.4 14 L49 10.4 L52.6 14" fill="none"
        stroke="#d4ff4f" strokeWidth="2.8" strokeLinecap="round"
        strokeLinejoin="round" />
    </svg>
  );
}
