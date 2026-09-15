import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { loans, inr } from "../lib/api";
import { formatDate } from "../lib/dates";
import { isGuest } from "../context/AuthContext";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Avatar from "../components/ui/Avatar";
import { SkeletonTable } from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";
import ErrorState from "../components/ui/ErrorState";
import SearchInput from "../components/ui/SearchInput";
import Pagination from "../components/ui/Pagination";
import DecisionBadge from "../components/risk/DecisionBadge";

const FILTERS = ["", "SUBMITTED", "UNDER_REVIEW", "MORE_INFORMATION_REQUIRED", "APPROVED", "REJECTED", "DRAFT", "WITHDRAWN"];

export default function LoanRequests() {
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const d = await loans.requests({ status: filter || undefined, limit: 100 }, session.token);
      setData(d);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [filter, session?.token]);

  useEffect(() => { load(); }, [load]);

  const rows = (data?.rows || []).slice((page - 1) * 12, page * 12);

  return (
    <div>
      <PageHeader
        title="Loan Requests"
        description="Full lifecycle: draft → submitted → review → approved / rejected — every transition audited"
      />
      <Card padding="sm">
        <div className="filters-row">
          <select value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }} className="filter-select">
            <option value="">All statuses</option>
            {FILTERS.filter(Boolean).map((f) => <option key={f} value={f}>{f.replace(/_/g, " ")}</option>)}
          </select>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {Object.entries(data?.by_status || {}).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ")}
          </span>
        </div>
        {loading ? <SkeletonTable rows={8} cols={6} /> :
          error ? <ErrorState message={error} onRetry={load} /> :
          !rows.length ? <EmptyState title="No loan requests" description="Create one from a borrower profile." /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Borrower</th><th>Amount</th><th>Terms</th><th>Status</th><th>Updated</th><th></th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div className="borrower-cell">
                        <Avatar name={r.borrower_name || r.borrower_id} />
                        <div><div className="borrower-name">{r.borrower_name || r.borrower_id}</div>
                        <div className="borrower-id">#{r.id} · {r.borrower_id}</div></div>
                      </div>
                    </td>
                    <td><b>{inr(r.amount)}</b></td>
                    <td style={{ fontSize: 12 }}>{r.interest_rate}% × {r.duration_months}m</td>
                    <td><Badge variant={r.status === "APPROVED" ? "APPROVE" : r.status === "REJECTED" ? "HIGH" : r.status}>{r.status.replace(/_/g, " ")}</Badge></td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDate(r.updated_at)}</td>
                    <td><Button variant="secondary" size="sm" onClick={() => navigate(`/loan-requests/${r.id}`)}>Open</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.rows.length > 12 && (
          <Pagination page={page} total={data.rows.length} pageSize={12} onChange={setPage} />
        )}
      </Card>
      {isGuest(session) && (
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>
          Guests are read-only — sign in with Phone OTP to submit, review and approve requests.
        </p>
      )}
    </div>
  );
}
