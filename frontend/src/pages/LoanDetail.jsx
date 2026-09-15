import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth, guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { loans, inr } from "../lib/api";
import { formatDate } from "../lib/dates";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import ErrorState from "../components/ui/ErrorState";
import EmptyState from "../components/ui/EmptyState";
import { SkeletonCard } from "../components/ui/Skeleton";

const SCHED_LABEL = { UPCOMING: "Upcoming", DUE: "Due", PAID: "Paid", PARTIALLY_PAID: "Partial", LATE: "Late", MISSED: "Missed", WAIVED: "Waived" };

export default function LoanDetail() {
  const { id } = useParams();
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [loan, setLoan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [payOpen, setPayOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setLoan(await loans.get(id, session.token));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [id, session?.token]);

  useEffect(() => { load(); }, [load]);

  const repay = async () => {
    if (!guardLender(session, toast)) return;
    const amt = Number(amount);
    if (!(amt > 0)) return toast.error("Enter a valid amount");
    try {
      setBusy(true);
      const r = await loans.repay(id, { amount: amt, method: "manual" }, session.token);
      setPayOpen(false);
      setAmount("");
      toast.success(r.duplicate ? "Already recorded (idempotent)" : `Repayment recorded — outstanding ${inr(r.loan.outstanding_principal)}`);
      load();
    } catch (e) { toast.error("Repayment failed: " + e.message); }
    finally { setBusy(false); }
  };

  if (loading) return <div><PageHeader title="Loan" /><SkeletonCard /><SkeletonCard /></div>;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!loan) return null;

  const guest = isGuest(session);
  return (
    <div>
      <div className="bd-back"><button className="bd-back-link" onClick={() => navigate("/loans")}>← All loans</button></div>
      <PageHeader
        title={`Loan #${loan.id} — ${inr(loan.principal)}`}
        description={`${loan.borrower?.name || loan.borrower_id} · ${loan.interest_rate}% × ${loan.duration_months}m · EMI ${inr(loan.emi)} · disbursed ${loan.disbursed_at}`}
        actions={loan.status === "ACTIVE" ? (
          <Button variant="primary" size="sm" disabled={guest} title={guest ? "Sign in with Phone OTP" : "Record repayment"} onClick={() => setPayOpen(true)}>＋ Record repayment</Button>
        ) : null}
      />
      <div className="dash-metrics" style={{ marginBottom: 16 }}>
        <div className="metric-card"><small>Status</small><b><Badge variant={loan.status === "ACTIVE" ? "APPROVE" : loan.status === "DEFAULTED" ? "HIGH" : "LOW"}>{loan.status}</Badge></b></div>
        <div className="metric-card"><small>Outstanding principal</small><b>{inr(loan.outstanding_principal)}</b></div>
        <div className="metric-card"><small>Total repaid</small><b>{inr(loan.total_paid)}</b></div>
        <div className="metric-card"><small>Installments paid</small><b>{(loan.schedule || []).filter((s) => s.status === "PAID").length}/{(loan.schedule || []).length}</b></div>
      </div>
      <div className="bd-grid">
        <Card>
          <CardHeader><CardTitle>Repayment schedule</CardTitle><CardDescription>Deterministic amortization · statuses from backend state</CardDescription></CardHeader>
          <CardContent>
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>#</th><th>Due</th><th>Principal</th><th>Interest</th><th>Total</th><th>Paid</th><th>Status</th></tr></thead>
                <tbody>
                  {(loan.schedule || []).map((s) => (
                    <tr key={s.id}>
                      <td>{s.n}</td><td>{s.due_date}</td><td>{inr(s.principal)}</td>
                      <td>{inr(s.interest)}</td><td><b>{inr(s.total_due)}</b></td><td>{inr(s.paid)}</td>
                      <td><Badge variant={s.status === "PAID" ? "APPROVE" : s.status === "MISSED" ? "HIGH" : s.status === "LATE" ? "MEDIUM" : "LOW"}>{SCHED_LABEL[s.status] || s.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Repayments</CardTitle><CardDescription>Idempotent ledger</CardDescription></CardHeader>
          <CardContent>
            {!(loan.repayments || []).length && <EmptyState title="No repayments yet" />}
            {(loan.repayments || []).map((p) => (
              <div key={p.id} className="audit-row">
                <div><b>{inr(p.amount)}</b> <span style={{ color: "var(--text-muted)" }}>· {p.method} · {p.recorded_by}</span></div>
                <small style={{ color: "var(--text-muted)" }}>{formatDate(p.created_at)}</small>
              </div>
            ))}
            <CardHeader><CardTitle>Timeline</CardTitle></CardHeader>
            {(loan.timeline || []).map((e) => (
              <div key={e.id} className="audit-row">
                <div><b>{e.type.replace(/([A-Z])/g, " $1").trim()}</b> <span style={{ color: "var(--text-muted)" }}>· {e.actor}</span></div>
                <small style={{ color: "var(--text-muted)" }}>{formatDate(e.created_at)}</small>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <Modal open={payOpen} onClose={() => setPayOpen(false)} title={`Record repayment — loan #${loan.id}`}
        actions={<><Button variant="ghost" onClick={() => setPayOpen(false)}>Cancel</Button>
          <Button variant="primary" disabled={busy} onClick={repay}>{busy ? "Recording…" : "Record"}</Button></>}>
        <label className="review-note-label">Amount (₹)</label>
        <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} className="filter-search-input" placeholder={`e.g. ${loan.emi}`} />
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>Applies to oldest unpaid installment first. Retries are idempotent — no double-charging.</p>
      </Modal>
    </div>
  );
}
