import { useState } from "react";
import "./kit.css";

export default function CopyButton({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text ?? "");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text ?? "";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <button className="kit-copy-btn" onClick={copy} title={`Copy ${label.toLowerCase()}`}>
      {done ? "✓ Copied" : `⧉ ${label}`}
    </button>
  );
}
