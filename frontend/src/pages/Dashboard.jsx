import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { dashboard, intel, inr } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import MetricCard from "../components/dashboard/MetricCard";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { SkeletonCard } from "../components/ui/Skeleton";
import ErrorState from "../components/ui/ErrorState";
import "./Dashboard.css";

export default function Dashboard() {
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [recent, setRecent] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [portfolio, setPortfolio] = useState(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const m = await dashboard.metrics(session.token);
      setData(m);
      setRecent(m.recent || []);
      try {
        const [w, p] = await Promise.all([
          intel.warnings(session.token),
          intel.portfolio(session.token),
        ]);
        setWarnings((w.warnings || []).slice(0, 6));
        setPortfolio(p);
      } catch {
        // intelligence widgets are additive — dashboard still renders
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div>
      <PageHeader title="Dashboard" description="Lending Intelligence Overview" />
      <div className="dashboard-grid"><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>
    </div>
  );

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const greet = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

  return (
    <div>
      <PageHeader title={greet()} description="Lending Intelligence Overview · live from the database" />

      <div className="dashboard-grid">
        <MetricCard label="Borrowers" value={data.borrowers?.toLocaleString()} sub={`${data.borrowers?.toLocaleString()}-profile portfolio`} icon="users" />
        <MetricCard label="Low Risk" value={data.low_risk} variant="success" icon="check" />
        <MetricCard label="Medium Risk" value={data.medium_risk} variant="warning" sub="watchlist" icon="zap" />
        <MetricCard label="High Risk" value={data.high_risk} variant="danger" sub="needs caution" icon="flag" />
        <MetricCard label="Potential Fraud" value={data.fraud_high} variant="danger" sub="high-severity" icon="shield" />
        <MetricCard label="Pending Verification" value={data.pending_verification} variant="warning" sub="review queue" icon="clipboard" />
        <MetricCard label="Avg Trust Score" value={data.avg_trust ?? "—"} icon="heart" />
        <MetricCard label="Avg Confidence" value={data.avg_confidence != null ? `${data.avg_confidence}%` : "—"} icon="target" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Early Warnings</CardTitle>
          <CardDescription>Missed installments · risk deterioration ≥15pts · fraud HIGH — live backend signals</CardDescription>
        </CardHeader>
        <CardContent>
          {!warnings.length && <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No active warnings. The watch is quiet.</p>}
          {warnings.map((w, i) => (
            <div key={i} className="audit-row" style={{ cursor: "pointer" }} onClick={() => w.link && navigate(w.link)}>
              <div><Badge variant={w.severity === "high" ? "HIGH" : "MEDIUM"}>{w.type.replace(/_/g, " ")}</Badge>{" "}
                <b>{w.borrower_name || w.borrower_id}</b>
                <br /><small style={{ color: "var(--text-muted)" }}>{w.evidence}</small></div>
            </div>
          ))}
        </CardContent>
      </Card>

      {portfolio && (
        <Card>
          <CardHeader>
            <CardTitle>Portfolio Intelligence</CardTitle>
            <CardDescription>Live aggregates · SIMULATION rows excluded</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="bd-grid-2">
              <div className="bd-stat"><small>Disbursed</small><b>{inr(portfolio.loans?.principal)}</b></div>
              <div className="bd-stat"><small>Outstanding</small><b>{inr(portfolio.loans?.outstanding)}</b></div>
              <div className="bd-stat"><small>Repaid</small><b>{inr(portfolio.loans?.repaid)}</b></div>
              <div className="bd-stat"><small>Active / Completed / Defaulted</small><b>{portfolio.loans?.active ?? 0} / {portfolio.loans?.completed ?? 0} / {portfolio.loans?.defaulted ?? 0}</b></div>
            </div>
            {(portfolio.active_exposure_by_risk || []).length > 0 && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
                Active exposure by risk: {portfolio.active_exposure_by_risk.map((r) => `${r.risk_level} ${inr(r.exposure)}`).join(" · ")}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Recent Borrowers</CardTitle>
          <CardDescription>Latest analyses across the portfolio</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Borrower</th>
                  <th>Trust</th>
                  <th>Risk</th>
                  <th>Fraud</th>
                  <th>Requested</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.borrower_id} className="clickable" onClick={() => navigate(`/borrower/${r.borrower_id}`)}>
                    <td>
                      <div className="borrower-cell">
                        <div className="borrower-avatar">{(r.name || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}</div>
                        <div><div className="borrower-name">{r.name}</div><div className="borrower-id">{r.borrower_id}</div></div>
                      </div>
                    </td>
                    <td><span className="trust-value">{r.trust ?? "—"}</span></td>
                    <td><Badge variant={r.risk}>{r.risk || "—"}</Badge></td>
                    <td><Badge variant={r.fraud === "HIGH" ? "HIGH" : r.fraud === "MEDIUM" ? "MEDIUM" : "LOW"}>{r.fraud || "—"}</Badge></td>
                    <td>{inr(r.requested)}</td>
                    <td><Badge variant={r.decision}>{(r.decision || "").replace(/_/g, " ")}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
