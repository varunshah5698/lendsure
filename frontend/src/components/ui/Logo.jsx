/**
 * LendSure mark — Positivus edition. Ink tile with a lime shield-check:
 * trust (shield) + confident decisions (check). One flat palette,
 * no gradients, readable from tab icon to billboard.
 */
export default function Logo({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="LendSure logo"
      style={{ flexShrink: 0, filter: "drop-shadow(0 2px 6px rgba(25,26,35,.28))" }}>
      <rect x="2" y="2" width="60" height="60" rx="17" fill="#191a23" />
      <path d="M32 10 L48 16.8 V31.5 C48 41.8 41 49 32 54 C23 49 16 41.8 16 31.5 V16.8 Z"
        fill="rgba(185,255,102,.13)" stroke="#b9ff66" strokeWidth="3.4" strokeLinejoin="round" />
      <path d="M24 32.5 l6 6 L41.5 25" fill="none" stroke="#b9ff66"
        strokeWidth="4.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
