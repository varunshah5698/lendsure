import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { grievances } from "../lib/api";
import { formatDate } from "../lib/dates";
import Logo from "../components/ui/Logo";
import Button from "../components/ui/Button";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Badge from "../components/ui/Badge";

const STEP_ORDER = ["OPEN", "IN_REVIEW", "RESOLVED"];

/** Public tracking — ticket ID + phone number, no login. */
export default function GrievanceTrack() {
  const [params] = useSearchParams();
  const [ticket, setTicket] = useState(params.get("t") || "");
  const [phone, setPhone] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const lookup = async () => {
    setError("");
    if (!ticket.trim()) return setError("Enter your ticket ID (e.g. GRV-000001)");
    if (!/^\d{10}$/.test(phone.replace(/\D/g, ""))) return setError("Enter the 10-digit mobile number used in the complaint");
    setLoading(true);
    try {
      setData(await grievances.track(ticket.trim(), phone.replace(/\D/g, "")));
    } catch (e) { setError(e.message); setData(null); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (params.get("t")) document.getElementById("grv-phone")?.focus();
  }, []);

  const stepIdx = data ? (data.status === "ESCALATED" ? 1 : STEP_ORDER.indexOf(data.status)) : -1;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", padding: "32px 16px" }}>
      <div style={{ maxWidth: 640, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
          <Link to="/" title="Back to home page" style={{ display: "inline-flex" }}><Logo size={34} /></Link>
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 19 }}>Track your complaint</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Enter your ticket ID and mobile number.</div>
          </div>
        </div>
        <Card>
          <CardContent>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 10 }}>
              <input value={ticket} onChange={(e) => setTicket(e.target.value.toUpperCase())} className="filter-search-input" placeholder="GRV-000001" />
              <input id="grv-phone" value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} className="filter-search-input" placeholder="10-digit mobile" maxLength={10} />
              <Button variant="primary" onClick={lookup} disabled={loading}>{loading ? "…" : "Track"}</Button>
            </div>
            {error && <div className="auth-error" style={{ marginTop: 10 }}>{error}</div>}
          </CardContent>
        </Card>
        {data && (
          <Card style={{ marginTop: 16 }}>
            <CardHeader>
              <CardTitle>{data.ticket_id} · {data.subject}</CardTitle>
              <CardDescription>{data.category.replace(/_/g, " ")} · filed {formatDate(data.created_at)}</CardDescription>
            </CardHeader>
            <CardContent>
              <div style={{ marginBottom: 8 }}><Badge variant={data.status === "OPEN" ? "MEDIUM" : data.status === "RESOLVED" || data.status === "CLOSED" ? "APPROVE" : "MANUAL_REVIEW"}>{data.status.replace(/_/g, " ")}</Badge></div>
              <div style={{ display: "flex", gap: 6, margin: "14px 0" }}>
                {STEP_ORDER.map((s, i) => (
                  <div key={s} style={{ flex: 1, textAlign: "center", fontSize: 11, fontWeight: 700, color: i <= stepIdx ? "var(--text-primary)" : "var(--text-muted)" }}>
                    <div style={{
                      height: 6, borderRadius: 3, marginBottom: 6,
                      background: i <= stepIdx ? "var(--primary)" : "var(--border)",
                    }} />
                    {s.replace(/_/g, " ")}
                  </div>
                ))}
              </div>
              {data.status === "ESCALATED" && (
                <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>Your complaint has been escalated to a senior reviewer. We will contact you on your registered mobile number.</p>
              )}
              <div style={{ marginTop: 12, borderTop: "1px solid var(--border-light)", paddingTop: 12 }}>
                {(data.notes || []).map((n) => (
                  <div key={n.id} style={{ fontSize: 13, padding: "6px 0", borderBottom: "1px solid var(--border-light)" }}>
                    <div>{n.note}</div>
                    <small style={{ color: "var(--text-muted)" }}>{formatDate(n.created_at)}</small>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
                <Link to="/grievance"><Button variant="secondary">Raise another</Button></Link>
                <Link to="/auth"><Button variant="ghost">Sign in</Button></Link>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
