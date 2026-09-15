import { useState, useEffect } from "react";
import "./kit.css";

export default function SearchInput({ value, onChange, placeholder = "Search…", debounce = 300, className = "" }) {
  const [inner, setInner] = useState(value ?? "");
  useEffect(() => { setInner(value ?? ""); }, [value]);
  useEffect(() => {
    const t = setTimeout(() => { if (inner !== (value ?? "")) onChange?.(inner); }, debounce);
    return () => clearTimeout(t);
  }, [inner, debounce, onChange, value]);
  return (
    <div className={`kit-search ${className}`}>
      <svg className="kit-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
      </svg>
      <input
        type="text" className="kit-search-input" placeholder={placeholder}
        value={inner} onChange={(e) => setInner(e.target.value)} aria-label={placeholder}
      />
      {inner && <button className="kit-search-clear" onClick={() => { setInner(""); onChange?.(""); }} aria-label="Clear search">✕</button>}
    </div>
  );
}
