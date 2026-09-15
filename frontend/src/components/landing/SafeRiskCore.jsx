import { Component, Suspense, lazy, useState, useEffect, useRef, useCallback } from "react";

const CSS_FALLBACK = {
  default: function CSSFallbackComp() {
    return (
      <div className="lp-scene-fallback" aria-hidden="true">
        <div className="lp-fallback-orb" />
        <div className="lp-fallback-ring lp-fallback-ring--1" />
        <div className="lp-fallback-ring lp-fallback-ring--2" />
        <div className="lp-fallback-ring lp-fallback-ring--3" />
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
 * 3D hero that can never crash the page. Labels update the DOM directly
 * (refs, no React state) so 60fps orbital motion never re-renders React.
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
    items.forEach(({ label, x, y }) => {
      let el = overlay.__els && overlay.__els[label];
      if (!el) {
        el = document.createElement("span");
        el.textContent = label;
        el.style.position = "absolute";
        el.style.color = "#191a23";
        el.style.fontSize = "11px";
        el.style.fontWeight = "700";
        el.style.letterSpacing = "0.06em";
        el.style.whiteSpace = "nowrap";
        el.style.pointerEvents = "none";
        el.style.textShadow = "0 0 8px rgba(255,255,255,.95), 0 1px 3px rgba(25,26,35,.3)";
        el.style.fontFamily = "'Inter', sans-serif";
        if (!overlay.__els) overlay.__els = {};
        overlay.__els[label] = el;
        overlay.appendChild(el);
      }
      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -130%)`;
    });
  }, []);

  if (!webgl) return <CSS_FALLBACK.default />;

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <SceneGuard fallback={<CSS_FALLBACK.default />}>
        <Suspense fallback={<CSS_FALLBACK.default />}>
          <RiskCoreScene className={className} onLabels={handleLabels} />
        </Suspense>
      </SceneGuard>
      <div ref={overlayRef} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />
    </div>
  );
}