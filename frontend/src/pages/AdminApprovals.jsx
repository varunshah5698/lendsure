import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { admin, inr } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Modal from "../components/ui/Modal";
import DecisionBadge from "../components/risk/DecisionBadge";
import SearchInput from "../components/ui/SearchInput";
import Pagination from "../components/ui/Pagination";
import Avatar from "../components/ui/Avatar";
import EmptyState from "../components/ui/EmptyState";
import ErrorState from "../components/ui/ErrorState";
import { SkeletonTable } from "../components/ui/Skeleton";
import "./AdminApprovals.css";

const FILTERS = [
  { value: "pending", label: "Pending Review" },
  { value: "all", label: "All Decisions" },
  { value: "reviewed", label: "Reviewed" },
  { value: "MANUAL_REVIEW", label: "Manual Review" },
  { value: "REJECT", label: "Reject" },
  { value: "REDUCE_AMOUNT", label: "Reduce Amount" },
  { value: "APPROVE_WITH_CONDITIONS", label: "Conditional" },
  { value: "APPROVE", label: "Approve" },
];

const REVIEW_CHOICES = ["APPROVE", "APPROVE_WITH_CONDITIONS", "REDUCE_AMOUNT", "MANUAL_REVIEW", "REJECT"];

export default function AdminApprovals() {
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [filter, setFilter] = useState(params.get("filter") || "pending");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reviewing, setReviewing] = useState(null);
  const [choice, setChoice] = useState("APPROVE");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setData(await admin.approvals(
        { decision: filter === "all" ? undefined : filter, q, page, page_size: 12 },
        session.token
      ));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [filter, q, page, session?.token]);

  useEffect(() => {
    const t = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  const openReview = (row) => {
    if (!guardLender(session, toast)) return;
    setReviewing(row);
    setChoice(row.decision === "MANUAL_REVIEW" ? "APPROVE_WITH_CONDITIONS" : row.decision);
    setNote("");
  };

  const submitReview = async () => {
    if (choice === "REJECT" && note.trim().length < 5) {
      toast.error("A reason (min 5 characters) is required to reject");
      return;
    }
    try {
      setSubmitting(true);
      const r = await admin.reviewApproval(reviewing.id, { decision: choice, note: note.trim() }, session.token);
      toast.success(`Decision recorded: ${r.from} → ${r.to}`);
      setReviewing(null);
      load();
    } catch (e) { toast.error("Review failed: " + e.message); }
    finally { setSubmitting(false); }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div>
      <PageHeader
        title="Approvals"
        description="Review engine decisions, approve, reject or override with a documented reason"
      />

      <Card padding="sm">
        <div className="filters-row">
          <SearchInput
            value={q}
            onChange={(v) => { setQ(v); setPage(1); }}
            placeholder="Search borrower name or ID…"
          />
          <select
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setPage(1); }}
            className="filter-select"
          >
            {FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </div>

        {loading ? (
          <SkeletonTable rows={8} cols={7} />
        ) : !data?.rows?.length ? (
          <EmptyState
            title={filter === "pending" ? "Queue is clear" : "No decisions found"}
            description={filter === "pending" ? "No analyses are waiting for manual review." : "Try adjusting your filters."}
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Borrower</th>
                  <th>Trust</th>
                  <th>Risk / Fraud</th>
                  <th>Engine Decision</th>
                  <th>Review Status</th>
                  <th>Recommended</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div className="borrower-cell">
                        <Avatar name={r.borrower_name} />
                        <div>
                          <div className="borrower-name">{r.borrower_name}</div>
                          <div className="borrower-id">{r.borrower_id} · {r.city}</div>
                        </div>
                      </div>
                    </td>
                    <td><span className="trust-value">{r.trust_score ?? "—"}</span></td>
                    <td>
                      <Badge variant={r.risk_level}>{r.risk_level}</Badge>{" "}
                      <Badge variant={r.fraud_risk}>{r.fraud_risk}</Badge>
                    </td>
                    <td><DecisionBadge decision={r.decision} /></td>
                    <td>
                      {r.review_decision ? (
                        <span className="review-done" title={`${r.reviewed_by} · ${r.reviewed_at}`}>
                          ✓ {r.review_decision.replace(/_/g, " ")}
                        </span>
                      ) : (
                        <span className="review-pending">Awaiting review</span>
                      )}
                    </td>
                    <td>{r.recommended_amount != null ? inr(r.recommended_amount) : "—"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Button variant="ghost" size="sm" onClick={() => navigate(`/borrower/${r.borrower_id}`)}>View</Button>
                      <Button variant="secondary" size="sm" onClick={() => openReview(r)} disabled={isGuest(session)} title={isGuest(session) ? "Sign in with Phone OTP for lender actions" : "Review decision"}>
                        {r.review_decision ? "Re-review" : "Review"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > 0 && (
          <Pagination page={page} total={data.total} pageSize={12} onChange={setPage} />
        )}
      </Card>

      <Modal
        open={!!reviewing}
        onClose={() => setReviewing(null)}
        title={`Review — ${reviewing?.borrower_name}`}
        description={`Engine decision: ${reviewing?.decision?.replace(/_/g, " ")} · Trust ${reviewing?.trust_score} · Risk ${reviewing?.risk_level} · Fraud ${reviewing?.fraud_risk}`}
        width={560}
        actions={
          <>
            <Button variant="ghost" onClick={() => setReviewing(null)}>Cancel</Button>
            <Button variant="primary" onClick={submitReview} disabled={submitting}>
              {submitting ? "Recording…" : "Record Decision"}
            </Button>
          </>
        }
      >
        <div className="review-choices">
          {REVIEW_CHOICES.map((c) => (
            <label key={c} className={`review-choice ${choice === c ? "review-choice-active" : ""}`}>
              <input type="radio" name="review-decision" checked={choice === c} onChange={() => setChoice(c)} />
              <DecisionBadge decision={c} />
            </label>
          ))}
        </div>
        <label className="review-note-label">
          Reviewer note {choice === "REJECT" ? "(required)" : "(optional)"}
        </label>
        <textarea
          className="review-note"
          rows={3}
          placeholder={choice === "REJECT" ? "Explain why this application is being rejected…" : "Add context for the audit trail (optional)…"}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {reviewing?.review_decision && (
          <p className="review-prev">
            Previously reviewed: <b>{reviewing.review_decision.replace(/_/g, " ")}</b> by {reviewing.reviewed_by}
            {reviewing.review_note ? ` — “${reviewing.review_note}”` : ""}
          </p>
        )}
      </Modal>
    </div>
  );
}
