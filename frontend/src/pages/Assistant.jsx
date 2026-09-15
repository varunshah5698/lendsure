import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { assistant } from "../lib/api";
import Button from "../components/ui/Button";
import Icon from "../components/ui/Icon";
import ErrorState from "../components/ui/ErrorState";
import "./Assistant.css";

const QUICK = [
  { label: "Highest risk", ask: "Show my highest-risk borrowers." },
  { label: "Prioritize today", ask: "Which recovery cases should I prioritize today?" },
  { label: "Overdue grievances", ask: "Show overdue grievances." },
  { label: "My city", ask: "Which borrowers in my city are most likely to default?" },
];

const RAIL_LINKS = [
  { label: "Borrowers", path: "/borrowers", icon: "users" },
  { label: "Cases", path: "/cases", icon: "folder" },
  { label: "Grievances", path: "/grievances", icon: "shield-check" },
  { label: "How scoring works", path: "/admin/model", icon: "chart" },
];

function RichText({ text }) {
  const lines = String(text || "").split("\n");
  return (
    <div className="ai-msg-text">
      {lines.map((ln, i) => {
        const m = ln.match(/^\s*[-*]\s+(.*)$/);
        const body = m ? m[1] : ln;
        const parts = body.split(/(\*\*[^*]+\*\*)/g);
        return (
          <div key={i} className={m ? "ai-bullet" : undefined}>
            {parts.map((p, j) =>
              p.startsWith("**") && p.endsWith("**") && p.length > 4
                ? <b key={j}>{p.slice(2, -2)}</b>
                : <span key={j}>{p}</span>
            )}
            {ln === "" && <br />}
          </div>
        );
      })}
    </div>
  );
}

/** AI Recovery Intelligence in Pulse-template dress: dark tablet panel,
 *  serif title, side rail with recent questions, pill conversation,
 *  big white ask bar with quick chips. Same grounded backend as before. */
export default function Assistant() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [toolsLine, setToolsLine] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    assistant.status(session?.token)
      .then(setStatus)
      .catch((e) => setStatusError(e.message));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const recent = messages.filter((m) => m.role === "user").slice(-6).reverse();

  const send = async (text) => {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    setToolsLine("");
    const history = [...messages.slice(-8).map((m) => ({ role: m.role, content: m.text })), { role: "user", content: message }];
    setMessages((ms) => [...ms, { role: "user", text: message }]);
    setBusy(true);
    try {
      const r = await assistant.chat(message, history.slice(0, -1), session?.token);
      if (r.tools_used?.length) setToolsLine(`Consulted live data: ${r.tools_used.join(", ")}`);
      setMessages((ms) => [...ms, { role: "assistant", text: r.reply, model: r.model }]);
    } catch (e) {
      setMessages((ms) => [...ms, { role: "error", text: e.message }]);
    } finally {
      setBusy(false);
    }
  };

  const newChat = () => {
    if (busy) return;
    setMessages([]);
    setToolsLine("");
    setInput("");
  };

  if (statusError) return <ErrorState message={statusError} onRetry={() => window.location.reload()} />;

  return (
    <div className="ai-wrap">
      {/* ------- side rail ------- */}
      <aside className="ai-side">
        <div className="ai-brand">
          <span className="ai-brand-mark"><Icon name="sparkles" size={16} /></span>
          <span>Recovery Intel</span>
        </div>
        <button className="ai-new" onClick={newChat} disabled={busy}>
          <span className="ai-plus">＋</span> New analysis
        </button>
        <nav className="ai-rail">
          {RAIL_LINKS.map((l) => (
            <button key={l.path} className="ai-rail-item" onClick={() => navigate(l.path)}>
              <Icon name={l.icon} size={15} /> {l.label}
            </button>
          ))}
        </nav>
        <div className="ai-recent">
          <div className="ai-recent-title">Recent questions</div>
          {!recent.length && (
            <div className="ai-recent-empty">Your questions in this session appear here.</div>
          )}
          {recent.map((m, i) => (
            <button key={i} className="ai-recent-item" title={m.text} onClick={() => send(m.text)}>
              {m.text.length > 34 ? m.text.slice(0, 34) + "…" : m.text}
            </button>
          ))}
        </div>
        <div className="ai-model">
          <div className="ai-model-title">{status ? status.model : "Loading model…"}</div>
          <div className="ai-model-sub">
            {status ? (status.configured ? `Live on ${status.provider}` : "Provider not configured") : "Checking provider…"}
          </div>
        </div>
      </aside>

      {/* ------- main panel ------- */}
      <div className="ai-main">
        <div className="ai-head">
          <h1 className="ai-title">Recovery intelligence</h1>
          <p className="ai-sub">Grounded answers from live records you are allowed to see.</p>
        </div>

        <div className="ai-chat">
          {!messages.length && (
            <div className="ai-welcome">
              <div className="ai-assistant-bubble">
                Ask about borrowers, risk, recovery queues, grievances or policy — I check the live
                database first and explain what I find, with ids you can verify.
              </div>
            </div>
          )}
          {messages.map((m, i) => m.role === "user" ? (
            <div key={i} className="ai-row ai-row-user">
              <div className="ai-bubble ai-bubble-user">{m.text}</div>
            </div>
          ) : (
            <div key={i} className="ai-row">
              <div className={`ai-bubble ${m.role === "error" ? "ai-bubble-error" : "ai-bubble-assistant"}`}>
                {m.role === "error" ? m.text : <RichText text={m.text} />}
                {m.model && <div className="ai-model-tag">{m.model}</div>}
              </div>
            </div>
          ))}
          {busy && <div className="ai-thinking">Analyzing live records…</div>}
          {toolsLine && !busy && <div className="ai-tools">{toolsLine}</div>}
          <div ref={bottomRef} />
        </div>

        {status && !status.configured && (
          <div className="ai-offline">
            <b>AI provider not configured.</b> This page never fakes answers, so chat stays off until an
            administrator sets <code>LLM_API_KEY</code> in the backend environment and restarts.
          </div>
        )}
        <div className="ai-bar">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            placeholder="Ask anything…"
            aria-label="Ask the AI recovery analyst"
            className="ai-input"
            disabled={busy || !status?.configured}
          />
          <div className="ai-bar-row">
            <div className="ai-chips">
              {QUICK.map((q) => (
                <button key={q.label} className="ai-chip" disabled={busy || !status?.configured} onClick={() => send(q.ask)}>
                  {q.label}
                </button>
              ))}
            </div>
            <button className="ai-send" onClick={() => send()} disabled={busy || !input.trim() || !status?.configured} aria-label="Send question">
              <Icon name={busy ? "clock" : "search"} size={17} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
