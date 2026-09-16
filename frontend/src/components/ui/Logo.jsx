/**
 * LendSure mark — "Momentum" edition. A complete break from the old shields:
 * a deep-forest coin ringed in lime, three ascending growth bars forming an
 * abstract L, and a pulse-arrow tearing upward through them — money in
 * motion, decisions with momentum. One SVG, favicon to billboard.
 */
export default function Logo({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="LendSure logo"
      style={{ flexShrink: 0, filter: "drop-shadow(0 3px 8px rgba(10,56,38,.35))" }}>
      <defs>
        <radialGradient id="lsDisc" cx="0.38" cy="0.34" r="0.9">
          <stop offset="0" stopColor="#1a5c40" />
          <stop offset="0.6" stopColor="#0b2e21" />
          <stop offset="1" stopColor="#050f0b" />
        </radialGradient>
        <linearGradient id="lsRing2" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#eaffb0" />
          <stop offset="0.5" stopColor="#a3e635" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
        <linearGradient id="lsBar" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#15803d" />
          <stop offset="1" stopColor="#bef264" />
        </linearGradient>
      </defs>

      {/* coin */}
      <circle cx="32" cy="32" r="29" fill="url(#lsDisc)" />
      <circle cx="32" cy="32" r="29" fill="none" stroke="url(#lsRing2)"
        strokeWidth="3.6" />
      <circle cx="32" cy="32" r="23.5" fill="none" stroke="#a3e635"
        strokeOpacity="0.22" strokeWidth="1.2" strokeDasharray="2 5" />

      {/* ascending bars → abstract L */}
      <rect x="19" y="36" width="6.5" height="11" rx="2.4" fill="url(#lsBar)" />
      <rect x="28.2" y="29" width="6.5" height="18" rx="2.4" fill="url(#lsBar)" />
      <rect x="37.4" y="21" width="6.5" height="26" rx="2.4" fill="url(#lsBar)" />

      {/* pulse arrow tearing up through the bars */}
      <polyline points="13,42 25,32 31,35.5 47,17" fill="none"
        stroke="#eaffb0" strokeWidth="3.4" strokeLinecap="round"
        strokeLinejoin="round" />
      <polygon points="47,12.5 52.5,20 43.5,20.5" fill="#eaffb0" />

      {/* momentum dot */}
      <circle cx="46" cy="46" r="3.2" fill="#a3e635" />
    </svg>
  );
}
