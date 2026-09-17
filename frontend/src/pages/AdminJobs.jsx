import { useState, useEffect, useCallback } from "react";
import { useAuth, guardLender, isGuest } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { jobs } from "../lib/api";
import { formatDate } from "../lib/dates";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { SkeletonTable } from "../components/ui/Skeleton";
import ErrorState from "../components/ui/ErrorState";
import EmptyState from "../components/ui/EmptyState";

const VARIANT = { COMPLETED: "APPROVE", FAILED: "HIGH", PROCESSING: "MEDIUM", RETRYING: "MEDIUM", PENDING: "LOW" };

export default function AdminJobs() {
  const { session } = useAuth();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setData(await jobs.list({ status: filter || undefined }, session.token));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [filter, session?.token]);

  useEffect(() => {
    load();
    const t = setInterval(() => { if (document.visibilityState === "visible") load(); }, 8000);
    return () => clearInterval(t);
  }, [load]);

  const retry = async (id) => {
    if (!guardLender(session, toast)) return;
    try {
      await jobs.retry(id, session.token);
      toast.success("Job re-queued");
      load();
    } catch (e) { toast.error("Retry failed: " + e.message); }
  };

  const guest = isGuest(session);
  return (
    <div>
      <PageHeader eyebrow="Governance" title="Background Jobs" description="Async work with real status — document verification, retries, failures" />
      {!loading && !error && data?.by_status && (
        <div className="dash-metrics" style={{ marginBottom: 16 }}>
          {Object.entries(data.by_status).map(([k, v]) => (
            <div className="metric-card" key={k}><small>{k}</small><b>{v}</b></div>
          ))}
        </div>
      )}
      <Card padding="sm">
        <div className="filters-row">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="filter-select">
            <option value="">All statuses</option>
            {["PENDING", "PROCESSING", "COMPLETED", "FAILED", "RETRYING"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>auto-refreshes every 8s while visible</span>
        </div>
        {loading ? <SkeletonTable rows={8} cols={6} /> :
          error ? <ErrorState message={error} onRetry={load} /> :
          !(data?.jobs || []).length ? <EmptyState title="No jobs" description="Upload a document to trigger verification." /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Job</th><th>Ref</th><th>Status</th><th>Attempts</th><th>Error</th><th>Finished</th><th></th></tr></thead>
              <tbody>
                {data.jobs.map((j) => (
                  <tr key={j.id}>
                    <td><b>#{j.id} {j.kind}</b></td>
                    <td style={{ fontSize: 12 }}>{j.ref_type} {j.ref_id}</td>
                    <td><Badge variant={VARIANT[j.status] || "LOW"}>{j.status}</Badge></td>
                    <td>{j.attempts}/{j.max_attempts}</td>
                    <td style={{ fontSize: 12, color: "var(--danger)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" }}>{j.error || "—"}</td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDate(j.finished_at)}</td>
                    <td>{j.status === "FAILED" && <Button variant="ghost" size="sm" disabled={guest} onClick={() => retry(j.id)}>Retry</Button>}</td>
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
