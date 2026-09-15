import { useState, useEffect } from "react";
import "./kit.css";

export default function ScrollTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const h = () => setShow(window.scrollY > 600);
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);
  if (!show) return null;
  return (
    <button className="kit-scrolltop" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} aria-label="Back to top">
      ↑
    </button>
  );
}
