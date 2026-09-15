import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useAuth, guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { loans, inr } from "../lib/api";
import { formatDate } from "../lib/dates";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import DecisionBadge from "../components/risk/DecisionBadge";
import EmptyState from "../components/ui/EmptyState";
import ErrorState from "../components/ui/ErrorState";
import { SkeletonCard } from "../components/ui/Skeleton";

const TERMINAL = ["APPROVED", "REJECTED", "WITHDRAWN", "EXPIRED"];

export default function LoanRequestDetail() {
  const { id } = useParams();
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [req, setReq] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modal, setModal] = useState(null); // info | reject | approve
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [terms, setTerms] = useState({});

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const d = await loans.getRequest(id, session.token);
      setReq(d);
      setTerms({ amount: d.amount, interest_rate: d.interest_rate, duration_months: d.duration_months });
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [id, session?.token]);

  useEffect(() => { load(); }, [load]);

  const act = async (action, body = {}) => {
    if (!guardLender(session, toast)) return;
    try {
      setBusy(true);
      const r = action === "approve"
        ? await loans.approve(id, { ...body, note }, session.token)
        : await loans.transition(id, action, { ...body, note }, session.token);
      setModal(null);
      setNote("");
      if (action === "approve" && r.loan) {
        toast.success(`Approved — loan #${r.loan.id} disbursed, EMI ${inr(r.loan.emi)}`);
        navigate(`/loans/${r.loan.id}`);
        return;
      }
      toast.success("Request updated");
      load();
    } catch (e) { toast.error("Action failed: " + e.message); }
    finally { setBusy(false); }
  };

  if (loading) return <div><PageHeader title="Loan Request" /><SkeletonCard /><SkeletonCard /></div>;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!req) return null;

  const guest = isGuest(session);
  const canAct = !guest && !TERMINAL.includes(req.status);
  const needNote = modal === "reject" || modal === "info";

  return (
    <div>
      <div className="bd-back"><button className="bd-back-link" onClick={() => navigate("/loan-requests")}>← All requests</button></div>
      <PageHeader
        title={`Request #${req.id} — ${inr(req.amount)}`}
        description={`${req.borrower_name || req.borrower_id} · ${req.interest_rate}% × ${req.duration_months}m · ${req.purpose || "General purpose"}`}
      />
      <div className="bd-grid">
        <Card>
          <CardHeader><CardTitle>Status</CardTitle></CardHeader>
          <CardContent>
            <Badge variant={req.status === "APPROVED" ? "APPROVE" : req.status === "REJECTED" ? "HIGH" : req.status}>
              {req.status.replace(/_/g, " ")}
            </Badge>
            <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {req.status === "DRAFT" && <Button size="sm" variant="primary" disabled={!canAct} title={guest ? "Sign in with Phone OTP" : "Submit for review"} onClick={() => act("submit")}>Submit →</Button>}
              {req.status === "SUBMITTED" && <Button size="sm" variant="secondary" disabled={!canAct} onClick={() => act("start_review")}>Start review</Button>}
              {(req.status === "SUBMITTED" || req.status === "UNDER_REVIEW") && (
                <>
                  <Button size="sm" variant="primary" disabled={!canAct} onClick={() => setModal("approve")}>Approve & disburse</Button>
                  <Button size="sm" variant="secondary" disabled={!canAct} onClick={() => setModal("info")}>Request info</Button>
                  <Button size="sm" variant="ghost" disabled={!canAct} onClick={() => setModal("reject")}>Reject</Button>
                </>
              )}
              {req.status === "MORE_INFORMATION_REQUIRED" && <Button size="sm" variant="primary" disabled={!canAct} onClick={() => act("submit")}>Resubmit →</Button>}
              {!TERMINAL.includes(req.status) && <Button size="sm" variant="ghost" disabled={!canAct} onClick={() => act("withdraw")}>Withdraw</Button>}
              {req.loan_id && <Link to={`/loans/${req.loan_id}`} style={{ alignSelf: "center", fontSize: 13 }}>View loan #{req.loan_id} →</Link>}
            </div>
            {guest && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>Guests are read-only — sign in with Phone OTP for lender actions.</p>}
            {req.reviewer && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>Reviewed by {req.reviewer}{req.review_note ? ` — “${req.review_note}”` : ""}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Event timeline</CardTitle><CardDescription>Every state change, audited</CardDescription></CardHeader>
          <CardContent>
            {(req.timeline || []).length === 0 && <EmptyState title="No events yet" />}
            {(req.timeline || []).map((e) => (
              <div key={e.id} className="audit-row">
                <div><b>{e.type.replace(/([A-Z])/g, " $1").trim()}</b> <span style={{ color: "var(--text-muted)" }}>· {e.actor}</span></div>
                <small style={{ color: "var(--text-muted)" }}>{formatDate(e.created_at)}</small>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Modal open={!!modal} onClose={() => setModal(null)}
        title={modal === "approve" ? "Approve & disburse" : modal === "reject" ? "Reject request" : "Request information"}
        actions={<><Button variant="ghost" onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" disabled={busy || (needNote && note.trim().length < 5)} onClick={() => act(modal === "info" ? "request_info" : modal, modal === "approve" ? { amount: +terms.amount, interest_rate: +terms.interest_rate, duration_months: +terms.duration_months } : {})}>
            {busy ? "Working…" : "Confirm"}</Button></>}>
        {modal === "approve" && (
          <div className="sim-controls">
            <label className="sim-label">Amount · <b>{inr(+terms.amount || 0)}</b>
              <input type="number" value={terms.amount} onChange={(e) => setTerms({ ...terms, amount: e.target.value })} className="filter-search-input" /></label>
            <label className="sim-label">Rate %<input type="number" step="0.5" value={terms.interest_rate} onChange={(e) => setTerms({ ...terms, interest_rate: e.target.value })} className="filter-search-input" /></label>
            <label className="sim-label">Months<input type="number" value={terms.duration_months} onChange={(e) => setTerms({ ...terms, duration_months: e.target.value })} className="filter-search-input" /></label>
          </div>
        )}
        <label className="review-note-label">Note {needNote ? "(required, min 5 chars)" : "(optional)"}</label>
        <textarea className="review-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason recorded permanently in the audit trail…" />
      </Modal>
    </div>
  );
}
