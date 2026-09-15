import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { grievances } from "../lib/api";
import { formatDate } from "../lib/dates";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { SkeletonTable } from "../components/ui/Skeleton";
import ErrorState from "../components/ui/ErrorState";
import EmptyState from "../components/ui/EmptyState";

/** Staff triage queue for borrower complaints. */
export default function Grievances() {
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setRows(await grievances.list({ status: status || undefined }, session.token));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [status, session?.token]);

  useEffect(() => { load(); }, [load]);

  const openCount = rows.filter((g) => g.status === "OPEN").length;

  return (
    <div>
      <PageHeader
        title="Grievances"
        description={`Borrower complaints from the public portal${openCount ? ` · ${openCount} awaiting triage` : ""}`}
      />
      <Card padding="sm">
        <div className="filters-row">
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="filter-select">
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="IN_REVIEW">In review</option>
            <option value="ESCALATED">Escalated</option>
            <option value="RESOLVED">Resolved</option>
            <option value="CLOSED">Closed</option>
          </select>
        </div>
        {loading ? <SkeletonTable rows={6} cols={5} /> :
          error ? <ErrorState message={error} onRetry={load} /> :
          !rows.length ? <EmptyState title="No complaints" description="New borrower complaints will appear here." /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Ticket</th><th>Subject</th><th>Status</th><th>Assignee</th><th>Filed</th></tr></thead>
              <tbody>
                {rows.map((g) => (
                  <tr key={g.id} className="clickable" onClick={() => navigate(`/grievances/${g.id}`)}>
                    <td><b>{g.ticket_id}</b> <span style={{ color: "var(--text-muted)", fontSize: 12 }}>· {g.category.replace(/_/g, " ")}</span></td>
                    <td>{g.subject}<br /><small style={{ color: "var(--text-muted)" }}>{g.name} · {g.phone}</small></td>
                    <td><Badge variant={g.status === "OPEN" ? "MEDIUM" : g.status === "RESOLVED" || g.status === "CLOSED" ? "APPROVE" : "MANUAL_REVIEW"}>{g.status.replace(/_/g, " ")}</Badge></td>
                    <td style={{ fontSize: 12 }}>{g.assigned_to || <span style={{ color: "var(--text-muted)" }}>Unassigned</span>}</td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDate(g.created_at)}</td>
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
