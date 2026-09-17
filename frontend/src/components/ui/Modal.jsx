import { useEffect, useRef } from "react";
import "./Modal.css";

export default function Modal({ open, onClose, title, description, children, actions, width = 480 }) {
  const ref = useRef(null);
  const prevFocus = useRef(null);
  // Keep the latest close handler in a ref so the focus effect below depends
  // ONLY on `open`. If it depended on onClose (a new arrow function every
  // parent render), it would re-run on every keystroke inside the modal and
  // steal focus from the input after a single character.
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return;
    // Remember what opened the modal so focus returns there on close.
    prevFocus.current = document.activeElement;
    const handler = (e) => {
      if (e.key === "Escape") { onCloseRef.current(); return; }
      // Focus trap: keep Tab cycling inside the dialog.
      if (e.key === "Tab" && ref.current) {
        const items = ref.current.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        const vis = [...items].filter((el) => !el.disabled && el.offsetParent !== null);
        if (!vis.length) return;
        const first = vis[0];
        const last = vis[vis.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", handler);
    // Focus the first form field when there is one, else the dialog itself.
    const firstField = ref.current?.querySelector("input, textarea, select");
    if (firstField) firstField.focus();
    else ref.current?.focus();
    return () => {
      document.removeEventListener("keydown", handler);
      if (prevFocus.current && prevFocus.current.focus) prevFocus.current.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal"
        style={{ maxWidth: width }}
        ref={ref}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h3 className="modal-title">{title}</h3>
            {description && <p className="modal-desc">{description}</p>}
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {actions && <div className="modal-actions">{actions}</div>}
      </div>
    </div>
  );
}
