import { useState } from "react";
import { Link } from "react-router-dom";
import { grievances } from "../lib/api";
import Logo from "../components/ui/Logo";
import Button from "../components/ui/Button";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Icon from "../components/ui/Icon";

const CATEGORIES = [
  ["collection", "Collection behaviour (calls, visits, harassment)"],
  ["billing", "Wrong amount, EMI or charges"],
  ["repayment", "Payment not reflecting / receipt issues"],
  ["fraud_dispute", "I did not take this loan / identity misuse"],
  ["documents", "Document or KYC problems"],
  ["service", "Service quality / staff behaviour"],
  ["other", "Something else"],
];

/** Public complaint form — no login needed. Returns a trackable ticket ID. */
export default function Grievance() {
  const [form, setForm] = useState({ borrower_id: "", name: "", phone: "", category: "collection", subject: "", description: "" });
  const [done, setDone] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError("");
    if (form.name.trim().length < 2) return setError("Please tell us your name");
    if (!/^\d{10}$/.test(form.phone.replace(/\D/g, ""))) return setError("Enter a valid 10-digit mobile number");
    if (form.subject.trim().length < 5) return setError("Give a short subject (min 5 characters)");
    setLoading(true);
    try {
      const r = await grievances.create({ ...form, phone: form.phone.replace(/\D/g, "") });
      setDone(r);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", padding: "32px 16px" }}>
      <div style={{ maxWidth: 640, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
          <Link to="/" title="Back to home page" style={{ display: "inline-flex" }}><Logo size={34} /></Link>
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 19 }}>LendSure Grievance Portal</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Complaints are reviewed by our team. You will get a ticket ID to track yours.</div>
          </div>
        </div>
        {done ? (
          <Card>
            <CardHeader><CardTitle>Complaint registered</CardTitle>
              <CardDescription>Save this ticket ID — it is the only way to track your complaint.</CardDescription></CardHeader>
            <CardContent>
              <div style={{ border: "1px solid var(--pv-ink, #191a23)", borderRadius: 14, padding: "22px", textAlign: "center", background: "var(--primary-light)" }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", letterSpacing: ".08em", fontWeight: 700 }}>YOUR TICKET ID</div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 34, fontWeight: 700 }}>{done.ticket_id}</div>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
                <Link to={`/grievance/track?t=${done.ticket_id}`}><Button variant="primary">Track my complaint →</Button></Link>
                <Link to="/auth"><Button variant="secondary">Back to sign in</Button></Link>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader><CardTitle>Raise a complaint</CardTitle>
              <CardDescription>No login needed. We respond to every ticket.</CardDescription></CardHeader>
            <CardContent>
              <div style={{ display: "grid", gap: 12 }}>
                <div>
                  <label className="review-note-label">Your name</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="filter-search-input" placeholder="e.g. Asha Sharma" />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label className="review-note-label">Mobile number</label>
                    <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value.replace(/\D/g, "") })} className="filter-search-input" placeholder="10-digit mobile" maxLength={10} />
                  </div>
                  <div>
                    <label className="review-note-label">Borrower ID (if you have one)</label>
                    <input value={form.borrower_id} onChange={(e) => setForm({ ...form, borrower_id: e.target.value })} className="filter-search-input" placeholder="e.g. B10001" />
                  </div>
                </div>
                <div>
                  <label className="review-note-label">What is it about?</label>
                  <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="filter-select" style={{ width: "100%" }}>
                    {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
                <div>
                  <label className="review-note-label">Subject</label>
                  <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} className="filter-search-input" placeholder="e.g. Rude recovery calls every day" />
                </div>
                <div>
                  <label className="review-note-label">Describe what happened</label>
                  <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="filter-search-input" rows={4} placeholder="Dates, names, what was said or charged…" style={{ resize: "vertical" }} />
                </div>
                {error && <div className="auth-error">{error}</div>}
                <div>
                  <Button variant="primary" onClick={submit} disabled={loading}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><Icon name="shield-check" size={15} /> {loading ? "Submitting…" : "Submit complaint"}</span>
                  </Button>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  Already have a ticket? <Link to="/grievance/track" className="link-btn">Track it here</Link>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
