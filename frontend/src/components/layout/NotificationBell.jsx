import { useState, useEffect, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { notify } from "../../lib/api";
import { formatDate } from "../../lib/dates";
import Icon from "../ui/Icon";
import "./NotificationBell.css";

/**
 * Live notification bell: Server-Sent Events for instant delivery with a
 * visibility-aware polling fallback. Badge + list always reflect backend rows.
 */
export default function NotificationBell() {
  const { session } = useAuth();
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [live, setLive] = useState(false);
  const esRef = useRef(null);
  const pollRef = useRef(null);

  const refresh = useCallback(async () => {
    if (!session) return;
    try {
      const u = await notify.unread(session.token);
      setUnread(u.unread);
    } catch {}
  }, [session]);

  const loadList = useCallback(async () => {
    if (!session) return;
    try {
      setItems(await notify.list(session.token));
      const u = await notify.unread(session.token);
      setUnread(u.unread);
    } catch {}
  }, [session]);

  // SSE stream (primary) — falls back to polling on any failure.
  useEffect(() => {
    if (!session) return;
    let stopped = false;
    let es = null;
    const startPolling = () => {
      if (pollRef.current || stopped) return;
      const tick = () => {
        if (document.visibilityState === "visible") refresh();
        pollRef.current = setTimeout(tick, 30000);
      };
      tick();
    };
    (async () => {
      try {
        const t = await notify.ticket(session.token);
        if (stopped) return;
        es = new EventSource(`/api/ls/events/stream?ticket=${t.ticket}`);
        esRef.current = es;
        es.onmessage = (ev) => {
          try {
            const n = JSON.parse(ev.data);
            setItems((prev) => [n, ...prev].slice(0, 50));
            setUnread((u) => u + 1);
          } catch {}
        };
        es.onerror = () => {
          try { es.close(); } catch {}
          esRef.current = null;
          setLive(false);
          startPolling();
        };
        // confirm liveness shortly after connect
        setTimeout(() => { if (!stopped && esRef.current) setLive(true); }, 2500);
      } catch {
        if (!stopped) startPolling();
      }
    })();
    refresh();
    return () => {
      stopped = true;
      try { es?.close(); } catch {}
      if (pollRef.current) clearTimeout(pollRef.current);
      pollRef.current = null;
      esRef.current = null;
    };
  }, [session, refresh]);

  // close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (!e.target.closest(".notif-bell")) setOpen(false); };
    document.addEventListener("click", h);
    return () => document.removeEventListener("click", h);
  }, [open ]);

  const markAll = async () => {
    for (const n of items.filter((i) => !i.is_read).slice(0, 20)) {
      try { await notify.markRead(n.id, session.token); } catch {}
    }
    loadList();
  };

  if (!session) return null;
  return (
    <div className="notif-bell">
      <button
        className="notif-btn"
        onClick={() => { setOpen((o) => !o); if (!open) loadList(); }}
        aria-label="Notifications"
        title={live ? "Live updates connected" : "Notifications (polling)"}
      >
        <span className="notif-icon"><Icon name="bell" size={17} /></span>
        {unread > 0 && <span className="notif-badge">{unread > 99 ? "99+" : unread}</span>}
        <span className={`notif-dot ${live ? "notif-live" : "notif-poll"}`} />
      </button>
      {open && (
        <div className="notif-panel">
          <div className="notif-head">
            <b>Notifications</b>
            <span className="notif-mode">{live ? "● live" : "○ polling"}</span>
            {unread > 0 && <button className="link-btn" onClick={markAll}>Mark read</button>}
          </div>
          <div className="notif-list">
            {items.length === 0 && <div className="notif-empty">No notifications yet. Loan events, repayments and document results land here.</div>}
            {items.map((n) => (
              <Link key={n.id} to={n.link || "#"} className={`notif-item ${n.is_read ? "" : "notif-unread"}`}
                onClick={async () => { if (!n.is_read) { try { await notify.markRead(n.id, session.token); } catch {} } setOpen(false); }}>
                <div className="notif-title">{n.title}</div>
                {n.body && <div className="notif-body">{n.body}</div>}
                <div className="notif-time">{formatDate(n.created_at)}</div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
