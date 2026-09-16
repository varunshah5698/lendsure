/**
 * LendSure mark — "Verdict Prism" edition.
 * A hexagonal shield-ring (protection) fused with a lightning-check bolt
 * (fast, confident decisions), wrapped by an orbit sweep (live intel) and a
 * spark (insight). Lime-to-emerald gradients on deep forest — nothing flat,
 * nothing borrowed. One SVG, scales from favicon to billboard.
 */
export default function Logo({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="LendSure logo"
      style={{ flexShrink: 0, filter: "drop-shadow(0 3px 8px rgba(10,56,38,.35))" }}>
      <defs>
        <linearGradient id="lsRing" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#eaffb0" />
          <stop offset="0.55" stopColor="#4ade80" />
          <stop offset="1" stopColor="#0e9f6e" />
        </linearGradient>
        <linearGradient id="lsBolt" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#e9ff9e" />
          <stop offset="0.5" stopColor="#a3e635" />
          <stop offset="1" stopColor="#34d399" />
        </linearGradient>
        <radialGradient id="lsCore" cx="0.5" cy="0.42" r="0.75">
          <stop offset="0" stopColor="#14532d" />
          <stop offset="1" stopColor="#071711" />
        </radialGradient>
      </defs>

      {/* hex shield core */}
      <path d="M32 3 L55.7 16.7 V43.3 L32 57 L8.3 43.3 V16.7 Z"
        fill="url(#lsCore)" stroke="url(#lsRing)" strokeWidth="4"
        strokeLinejoin="round" />
      {/* inner etched ring */}
      <path d="M32 10.5 L49.4 20.5 V40.5 L32 50.5 L14.6 40.5 V20.5 Z"
        fill="none" stroke="#4ade80" strokeOpacity="0.28" strokeWidth="1.4" />

      {/* lightning-check verdict bolt */}
      <path d="M37.5 15 L23 36.5 h8.2 L27.5 49 L43 27.5 h-8.6 Z"
        fill="url(#lsBolt)" stroke="#071711" strokeOpacity="0.35" strokeWidth="1" />

      {/* orbit sweep + satellite dot */}
      <path d="M12 46 A24 24 0 0 0 50 50" fill="none" stroke="#b9ff66"
        strokeOpacity="0.65" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="51.5" cy="49.5" r="3.4" fill="#d4ff4f" />

      {/* insight spark */}
      <path d="M14.5 8.5 l1.5 3.6 3.6 1.5 -3.6 1.5 -1.5 3.6 -1.5 -3.6 -3.6 -1.5 3.6 -1.5 Z"
        fill="#eaffb0" />
    </svg>
  );
}
