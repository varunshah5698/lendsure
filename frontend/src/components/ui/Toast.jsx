import { useState, useEffect, useCallback, createContext, useContext } from "react";
import "./Toast.css";

const ToastContext = createContext(null);
let id = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const add = useCallback((msg, type = "success") => {
    const t = { id: ++id, msg, type };
    setToasts((prev) => [...prev, t]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== t.id));
    }, 3500);
  }, []);

  const toast = {
    success: (msg) => add(msg, "success"),
    error: (msg) => add(msg, "error"),
    info: (msg) => add(msg, "info"),
  };

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toast-container" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            {t.type === "success" && <span className="toast-icon">✓</span>}
            {t.type === "error" && <span className="toast-icon">✕</span>}
            {t.type === "info" && <span className="toast-icon">ℹ</span>}
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
