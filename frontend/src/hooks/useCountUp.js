import { useState, useEffect, useRef } from "react";

export default function useCountUp(target, duration = 1200, decimals = 0) {
  const [value, setValue] = useState(0);
  const raf = useRef(null);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const end = Number(target) || 0;
    if (reduce) { setValue(end); return; }
    const start = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Number((end * eased).toFixed(decimals)));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration, decimals]);
  return value;
}
