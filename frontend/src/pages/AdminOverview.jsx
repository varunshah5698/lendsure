import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { admin } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import DecisionBadge from "../components/risk/DecisionBadge";
import ErrorState from "../components/ui/ErrorState";
import { SkeletonCard } from "../components/ui/Skeleton";
import AuditTimeline from "../components/audit/AuditTimeline";
import Sparkline from "../components/charts/Sparkline";
import Icon from "../components/ui/Icon";
import "./AdminOverview.css";

export default function AdminOverview() {
  const { session } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setData(await admin.overview(session.token));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [session?.token]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div><PageHeader title="Admin Overview" /><SkeletonCard /><SkeletonCard /></div>;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const mix = data.decision_mix || {};
  const mixTotal = Object.values(mix).reduce((s, v) => s + v, 0) || 1;
  const maxDay = Math.max(1, ...(data.series_14d || []).map((d) => d.count));

  return (
    <div>
      <PageHeader
        title="Admin Overview"
        description={`Command center · model ${data.model_version} · ${data.borrowers?.toLocaleString()} borrowers`}
      />

      <div className="admin-stat-grid">
        <Card padding="sm">
          <div className="admin-stat-label">Pending Reviews</div>
          <div className={`admin-stat-value ${data.pending_review > 0 ? "admin-stat-alert" : ""}`}>
            {data.pending_review}
          </div>
          <Link to="/admin/approvals?filter=pending" className="admin-stat-link">Open approval queue →</Link>
        </Card>
        <Card padding="sm">
          <div className="admin-stat-label">Borrowers</div>
          <div className="admin-stat-value">{data.borrowers?.toLocaleString()}</div>
          <div className="admin-stat-sub">{data.analyses?.toLocaleString()} total analyses</div>
        </Card>
        <Card padding="sm">
          <div className="admin-stat-label">Avg Trust / Confidence</div>
          <div className="admin-stat-value">{data.avg_trust} <span className="admin-stat-unit">/ {data.avg_confidence}</span></div>
          <div className="admin-stat-sub">Across latest analyses</div>
        </Card>
        <Card padding="sm">
          <div className="admin-stat-label">High Risk / High Fraud</div>
          <div className="admin-stat-value">{data.high_risk} <span className="admin-stat-unit">/ {data.high_fraud}</span></div>
          <div className="admin-stat-sub">{data.reviewed} decisions reviewed</div>
        </Card>
      </div>

      <div className="admin-two-col">
        <Card>
          <CardHeader>
            <CardTitle>Decision Mix</CardTitle>
            <CardDescription>Latest analysis per borrower</CardDescription>
          </CardHeader>
          <CardContent>
            {Object.keys(mix).length === 0 && <p className="admin-muted">No analyses yet.</p>}
            {Object.entries(mix).sort((a, b) => b[1] - a[1]).map(([d, c]) => (
              <div key={d} className="admin-mix-row">
                <DecisionBadge decision={d} />
                <div className="admin-mix-bar">
                  <div className="admin-mix-fill" style={{ width: `${Math.round((c / mixTotal) * 100)}%` }} />
                </div>
                <span className="admin-mix-count">{c}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activity — Last 14 Days</CardTitle>
            <CardDescription>Analyses completed per day</CardDescription>
          </CardHeader>
          <CardContent>
            {(data.series_14d || []).length === 0 && <p className="admin-muted">No recent activity.</p>}
            {(data.series_14d || []).length > 1 && (
              <div style={{ marginBottom: 10 }}>
                <Sparkline data={(data.series_14d || []).map((d) => d.count)} width={420} height={64} />
              </div>
            )}
            <div className="admin-bars">
              {(data.series_14d || []).map((d) => (
                <div key={d.day} className="admin-bar-col" title={`${d.day}: ${d.count}`}>
                  <div className="admin-bar" style={{ height: `${Math.max(4, Math.round((d.count / maxDay) * 90))}px` }} />
                  <div className="admin-bar-label">{d.day.slice(5)}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="admin-two-col">
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
            <CardDescription>Latest audit events across the platform</CardDescription>
          </CardHeader>
          <CardContent>
            <AuditTimeline events={data.recent_activity || []} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Admin Shortcuts</CardTitle>
            <CardDescription>Common administrative actions</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="admin-shortcuts">
              <Link to="/admin/approvals?filter=pending" className="admin-shortcut">
                <span className="admin-shortcut-icon"><Icon name="check-circle" size={20} /></span>
                <span><b>Review approvals</b><small>{data.pending_review} awaiting decision</small></span>
              </Link>
              <Link to="/admin/approvals" className="admin-shortcut">
                <span className="admin-shortcut-icon"><Icon name="clipboard" size={20} /></span>
                <span><b>All decisions</b><small>Browse & override any analysis</small></span>
              </Link>
              <Link to="/admin/policies" className="admin-shortcut">
                <span className="admin-shortcut-icon"><Icon name="sliders" size={20} /></span>
                <span><b>Risk policies</b><small>Tune thresholds & lending rules</small></span>
              </Link>
              <Link to="/admin/model" className="admin-shortcut">
                <span className="admin-shortcut-icon"><Icon name="cpu" size={20} /></span>
                <span><b>Model performance</b><small>AUC, drivers & metrics</small></span>
              </Link>
              <Link to="/admin/settings" className="admin-shortcut">
                <span className="admin-shortcut-icon"><Icon name="tool" size={20} /></span>
                <span><b>Settings & sessions</b><small>API keys, active logins{data.active_api_keys ? ` (${data.active_api_keys} keys)` : ""}</small></span>
              </Link>
              <Link to="/borrowers" className="admin-shortcut">
                <span className="admin-shortcut-icon"><Icon name="users" size={20} /></span>
                <span><b>Borrowers</b><small>Search the full portfolio</small></span>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
