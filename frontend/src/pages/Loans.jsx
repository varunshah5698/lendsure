import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { loans, inr } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Avatar from "../components/ui/Avatar";
import { SkeletonTable } from "../components/ui/Skeleton";
import ErrorState from "../components/ui/ErrorState";
import EmptyState from "../components/ui/EmptyState";

export default function Loans() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setData(await loans.list({ status: filter || undefined, limit: 100 }, session.token));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [filter, session?.token]);

  useEffect(() => { load(); }, [load]);

  const p = data?.portfolio || {};
  return (
    <div>
      <PageHeader title="Loans" description="Disbursed portfolio — real schedules, real repayments" />
      {!loading && !error && (
        <div className="dash-metrics" style={{ marginBottom: 16 }}>
          <div className="metric-card"><small>Active loans</small><b>{p.n ?? "—"}</b></div>
          <div className="metric-card"><small>Disbursed principal</small><b>{inr(p.principal)}</b></div>
          <div className="metric-card"><small>Outstanding</small><b>{inr(p.outstanding)}</b></div>
          <div className="metric-card"><small>Repaid</small><b>{inr(p.repaid)}</b></div>
        </div>
      )}
      <Card padding="sm">
        <div className="filters-row">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="filter-select">
            <option value="">All statuses</option>
            {["ACTIVE", "COMPLETED", "DEFAULTED"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        {loading ? <SkeletonTable rows={8} cols={6} /> :
          error ? <ErrorState message={error} onRetry={load} /> :
          !(data?.rows || []).length ? <EmptyState title="No loans yet" description="Approve a loan request to disburse the first loan." /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Loan</th><th>Borrower</th><th>Principal</th><th>EMI</th><th>Outstanding</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {data.rows.map((l) => (
                  <tr key={l.id}>
                    <td><b>#{l.id}</b> <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{l.duration_months}m @ {l.interest_rate}%</span></td>
                    <td><div className="borrower-cell"><Avatar name={l.borrower_name || l.borrower_id} />
                      <div><div className="borrower-name">{l.borrower_name || l.borrower_id}</div></div></div></td>
                    <td><b>{inr(l.principal)}</b></td>
                    <td>{inr(l.emi)}</td>
                    <td>{inr(l.outstanding_principal)}</td>
                    <td><Badge variant={l.status === "ACTIVE" ? "APPROVE" : l.status === "DEFAULTED" ? "HIGH" : "LOW"}>{l.status}</Badge></td>
                    <td><Button variant="secondary" size="sm" onClick={() => navigate(`/loans/${l.id}`)}>Open</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
