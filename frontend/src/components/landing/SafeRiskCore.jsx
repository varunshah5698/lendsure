import { Component, Suspense, lazy, useState, useEffect, useRef, useCallback } from "react";

const CSS_FALLBACK = {
  default: function CSSFallbackComp() {
    return (
      <div className="lp-scene-fallback lp-atom-fallback" aria-hidden="true">
        {/* Central Nucleus Cluster */}
        <div className="lp-atom-fb-nucleus">
          <div className="lp-atom-fb-ring" />
          <div className="lp-atom-fb-particle p1 red" />
          <div className="lp-atom-fb-particle p2 blue" />
          <div className="lp-atom-fb-particle p3 red" />
          <div className="lp-atom-fb-particle p4 blue" />
          <div className="lp-atom-fb-particle p5 red" />
          <div className="lp-atom-fb-particle p6 blue" />
          <div className="lp-atom-fb-particle p7 red" />
          <div className="lp-atom-fb-particle p8 blue" />
        </div>

        {/* 4 Crossing Elliptical Orbits with Rotating Electrons */}
        <div className="lp-atom-fb-orbit o1">
          <div className="lp-atom-fb-electron money">
            <span className="lp-atom-fb-tag">MONEY ₹</span>
          </div>
        </div>
        <div className="lp-atom-fb-orbit o2">
          <div className="lp-atom-fb-electron fraud">
            <span className="lp-atom-fb-tag">FRAUD 🛡️</span>
          </div>
        </div>
        <div className="lp-atom-fb-orbit o3">
          <div className="lp-atom-fb-electron credit">
            <span className="lp-atom-fb-tag">CREDIT 📊</span>
          </div>
        </div>
        <div className="lp-atom-fb-orbit o4">
          <div className="lp-atom-fb-electron trust">
            <span className="lp-atom-fb-tag">TRUST ⚡</span>
          </div>
        </div>
      </div>
    );
  },
};

const RiskCoreScene = lazy(() =>
  import("./RiskCoreScene").catch((e) => {
    console.error("[SafeRiskCore] 3D chunk failed to load, using CSS fallback:", e);
    return CSS_FALLBACK;
  })
);

class SceneGuard extends Component {
  state = { failed: false };
  static getDerivedStateFromError(e) {
    console.error("[SafeRiskCore] 3D scene crashed, using CSS fallback:", e);
    return { failed: true };
  }
  render() {
    if (this.state.failed) return this.props.fallback || null;
    return this.props.children;
  }
}

/**
 * 3D Atom Hero with zero-lag DOM labels (refs, no React state)
 * Maintains 60fps orbital motion without triggering React re-renders.
 */
export default function SafeRiskCore({ className }) {
  const [webgl, setWebgl] = useState(true);
  const overlayRef = useRef(null);

  useEffect(() => {
    try {
      const c = document.createElement("canvas");
      const ok = c.getContext("webgl2") || c.getContext("webgl");
      if (!ok) setWebgl(false);
    } catch {
      setWebgl(false);
    }
  }, []);

  const handleLabels = useCallback((items) => {
    const overlay = overlayRef.current;
    if (!overlay) return;

    items.forEach(({ id, label, icon, color, x, y }) => {
      const key = id || label;
      let el = overlay.__els && overlay.__els[key];
      if (!el) {
        el = document.createElement("div");
        el.className = `lp-atom-badge lp-atom-badge--${key.toLowerCase()}`;
        el.innerHTML = `
          <span class="lp-atom-badge-dot" style="background:${color};box-shadow:0 0 8px ${color}"></span>
          <span class="lp-atom-badge-name">${label}</span>
          <span class="lp-atom-badge-icon">${icon || ""}</span>
        `;
        if (!overlay.__els) overlay.__els = {};
        overlay.__els[key] = el;
        overlay.appendChild(el);
      }
      el.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -135%)`;
    });
  }, []);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      {/* Neo-brutalist Atom Infographic HUD */}
      <div className="lp-atom-hud">
        <div className="lp-atom-hud-header">
          <span className="lp-atom-hud-live-dot" />
          <span className="lp-atom-hud-title">ATOM RISK ENGINE</span>
        </div>
        <div className="lp-atom-hud-legend">
          <span className="lp-atom-hud-item lp-atom-hud-item--nucleus" title="Protons & Neutrons AI Cluster">
            <span className="lp-hud-dot" style={{ background: "#fbbf24" }} />
            <span className="lp-hud-text">Nucleus</span>
          </span>
          <span className="lp-atom-hud-item" title="Capital & Cashflow">
            <span className="lp-hud-dot" style={{ background: "#10b981" }} />
            <span className="lp-hud-text">Money</span>
          </span>
          <span className="lp-atom-hud-item" title="Risk & Anomaly Radar">
            <span className="lp-hud-dot" style={{ background: "#ef4444" }} />
            <span className="lp-hud-text">Fraud</span>
          </span>
          <span className="lp-atom-hud-item" title="Credit Profile & Debt">
            <span className="lp-hud-dot" style={{ background: "#6366f1" }} />
            <span className="lp-hud-text">Credit</span>
          </span>
          <span className="lp-atom-hud-item" title="Repayment Trust">
            <span className="lp-hud-dot" style={{ background: "#06b6d4" }} />
            <span className="lp-hud-text">Trust</span>
          </span>
        </div>
      </div>

      {!webgl ? (
        <CSS_FALLBACK.default />
      ) : (
        <SceneGuard fallback={<CSS_FALLBACK.default />}>
          <Suspense fallback={<CSS_FALLBACK.default />}>
            <RiskCoreScene className={className} onLabels={handleLabels} />
          </Suspense>
        </SceneGuard>
      )}

      {/* Floating 3D-tracked DOM electron badges */}
      <div
        ref={overlayRef}
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          overflow: "hidden",
        }}
      />
    </div>
  );
}