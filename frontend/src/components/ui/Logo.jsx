/**
 * LendSure mark — "Rupee Ascent" edition. No badge, no container: a bold
 * geometric rupee whose top bar launches into a growth arrow — money lent,
 * money climbing. Deep lime-to-teal gradient reads on light and dark.
 * One SVG, favicon to billboard.
 */
export default function Logo({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="LendSure logo"
      style={{ flexShrink: 0, filter: "drop-shadow(0 3px 8px rgba(10,56,38,.3))" }}>
      <defs>
        {/* userSpaceOnUse: open line-art has zero-width/height bounds —
            objectBoundingBox gradients would not paint on it */}
        <linearGradient id="lsA" gradientUnits="userSpaceOnUse" x1="32" y1="2" x2="32" y2="62">
          <stop offset="0" stopColor="#bef264" />
          <stop offset="0.55" stopColor="#4ade80" />
          <stop offset="1" stopColor="#0d9488" />
        </linearGradient>
      </defs>

      {/* stem */}
      <path d="M17 12 V52" fill="none" stroke="url(#lsA)"
        strokeWidth="6.5" strokeLinecap="round" />
      {/* top bar launching into the growth arrow */}
      <path d="M14 16 H40 L50 6" fill="none" stroke="url(#lsA)"
        strokeWidth="6.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M44 6 H50 V12" fill="none" stroke="#bef264"
        strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      {/* mid bar */}
      <path d="M14 26 H34" fill="none" stroke="url(#lsA)"
        strokeWidth="6" strokeLinecap="round" />
      {/* bowl */}
      <path d="M20 26 C31 26 36.5 30 36.5 34.5 C36.5 39 31 42 25 42.5"
        fill="none" stroke="url(#lsA)" strokeWidth="6"
        strokeLinecap="round" />
      {/* classic descending leg */}
      <path d="M25 42.5 L33 51" fill="none" stroke="url(#lsA)"
        strokeWidth="6" strokeLinecap="round" />
    </svg>
  );
}
