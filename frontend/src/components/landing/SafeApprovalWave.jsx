import { Component, Suspense, lazy, useState, useEffect, useRef, useCallback } from "react";

const CSS_FALLBACK = {
  default: function CSSFallbackComp() {
    return (
      <div className="lp-wave-fallback" aria-hidden="true">
        {Array.from({ length: 18 }).map((_, i) => (
          <span key={i} style={{ animationDelay: `${i * 0.09}s` }} />
        ))}
      </div>
    );
  },
};

const ApprovalWaveScene = lazy(() =>
  import("./ApprovalWaveScene").catch((e) => {
    console.error("[SafeApprovalWave] 3D chunk failed to load, using CSS fallback:", e);
    return CSS_FALLBACK;
  })
);

class SceneGuard extends Component {
  state = { failed: false };
  static getDerivedStateFromError(e) {
    console.error("[SafeApprovalWave] 3D scene crashed, using CSS fallback:", e);
    return { failed: true };
  }
  render() {
    if (this.state.failed) return this.props.fallback || null;
    return this.props.children;
  }
}

export default function SafeApprovalWave({ className }) {
  const [webgl, setWebgl] = useState(true);
  const dotRef = useRef(null);

  useEffect(() => {
    try {
      const c = document.createElement("canvas");
      const ok = c.getContext("webgl2") || c.getContext("webgl");
      if (!ok) setWebgl(false);
    } catch {
      setWebgl(false);
    }
  }, []);

  const handleDot = useCallback(({ x, y }) => {
    if (dotRef.current) {
      dotRef.current.style.transform = `translate(${x}px, ${y}px) translate(-50%,-50%)`;
    }
  }, []);

  if (!webgl) return <CSS_FALLBACK.default />;

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <SceneGuard fallback={<CSS_FALLBACK.default />}>
        <Suspense fallback={<CSS_FALLBACK.default />}>
          <ApprovalWaveScene className={className} onDot={handleDot} />
        </Suspense>
      </SceneGuard>
      <div
        ref={dotRef}
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: 10,
          height: 10,
          pointerEvents: "none",
          borderRadius: "50%",
          background: "#191a23",
          opacity: 0.9,
          boxShadow: "0 0 14px rgba(25,26,35,.5)",
        }}
      />
    </div>
  );
}