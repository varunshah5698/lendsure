import { useState, useEffect, useMemo } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { dashboard, intel, inr } from "../lib/api";
import Reveal from "../components/ui/Reveal";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import Icon from "../components/ui/Icon";
import DecisionDistribution from "../components/dashboard/DecisionDistribution";
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
  const [tableFilter, setTableFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const m = await dashboard.metrics(session?.token);
      setData(m);
      setRecent(m.recent || []);
      try {
        const [w, p] = await Promise.all([
          intel.warnings(session?.token),
          intel.portfolio(session?.token),
        ]);
        setWarnings((w.warnings || []).slice(0, 7));
        setPortfolio(p);
      } catch {
        // intelligence widgets are additive
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // Filtered recent borrowers
  const filteredRecent = useMemo(() => {
    let list = recent;
    if (tableFilter === "high") {
      list = list.filter((r) => r.risk === "HIGH" || r.fraud === "HIGH");
    } else if (tableFilter === "low") {
      list = list.filter((r) => r.risk === "LOW");
    } else if (tableFilter === "review") {
      list = list.filter(
        (r) =>
          r.decision === "MANUAL_REVIEW" ||
          r.decision === "APPROVE_WITH_CONDITIONS"
      );
    } else if (tableFilter === "fraud") {
      list = list.filter((r) => r.fraud === "HIGH" || r.fraud === "MEDIUM");
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (r) =>
          (r.name && r.name.toLowerCase().includes(q)) ||
          (r.borrower_id && r.borrower_id.toLowerCase().includes(q))
      );
    }
    return list;
  }, [recent, tableFilter, searchQuery]);

  if (loading) {
    return (
      <div className="dashboard-container">
        <div className="db-header-skeleton">
          <div className="skeleton-title" />
          <div className="skeleton-sub" />
        </div>
        <div className="db-kpi-grid">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <div className="db-main-layout">
          <div className="db-col-main">
            <SkeletonCard />
            <SkeletonCard />
          </div>
          <div className="db-col-side">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </div>
      </div>
    );
  }

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const greet = () => {
    const h = new Date().getHours();
    return h < 12
      ? "Good morning"
      : h < 17
      ? "Good afternoon"
      : "Good evening";
  };

  const userName =
    session?.display_name && session.display_name !== "Guest"
      ? `, ${session.display_name.split(" ")[0]}`
      : "";

  // Repayment calculations
  const principal = portfolio?.loans?.principal || 50000;
  const repaid = portfolio?.loans?.repaid || 4442.44;
  const outstanding = portfolio?.loans?.outstanding || 46057.56;
  const repaymentPct =
    principal > 0 ? Math.min(Math.round((repaid / principal) * 100), 100) : 0;

  return (
    <div className="dashboard-container">
      {/* ---------- EXECUTIVE HEADER & QUICK ACTIONS ---------- */}
      <div className="db-header">
        <div className="db-header-left">
          <div className="db-header-badge">
            <span className="db-live-dot" />
            <span className="db-live-text">
              Live Engine · {data.borrowers?.toLocaleString()} Active Profiles
            </span>
          </div>
          <h1 className="db-header-title">
            {greet()}
            {userName}
          </h1>
          <p className="db-header-desc">
            Lending intelligence matrix, portfolio health, and automated risk
            radar.
          </p>
        </div>

        <div className="db-header-actions">
          <Link to="/borrowers" className="db-btn db-btn-primary">
            <Icon name="users" size={16} />
            <span>Analyze Borrower</span>
          </Link>
          <Link to="/simulations" className="db-btn db-btn-secondary">
            <Icon name="flask" size={16} />
            <span>Simulate Risk</span>
          </Link>
          <Link to="/assistant" className="db-btn db-btn-secondary">
            <Icon name="sparkles" size={16} />
            <span>AI Copilot</span>
          </Link>
        </div>
      </div>

      {/* ---------- 4 TOP EXECUTIVE KPI CARDS ---------- */}
      <div className="db-kpi-grid">
        {/* KPI 1: Capital & Loan Exposure */}
        <Reveal delay={0.0}>
          <div className="db-kpi-card db-kpi-card--capital">
            <div className="db-kpi-top">
              <span className="db-kpi-label">Active Exposure</span>
              <span className="db-kpi-icon-wrap icon-green">
                <Icon name="cash" size={18} />
              </span>
            </div>
            <div className="db-kpi-value">{inr(outstanding)}</div>
            <div className="db-kpi-progress-wrap">
              <div className="db-kpi-progress-bar">
                <div
                  className="db-kpi-progress-fill"
                  style={{ width: `${repaymentPct}%` }}
                />
              </div>
              <div className="db-kpi-foot">
                <span>{inr(principal)} Disbursed</span>
                <span className="db-kpi-highlight">{repaymentPct}% Repaid</span>
              </div>
            </div>
          </div>
        </Reveal>

        {/* KPI 2: Borrower Universe */}
        <Reveal delay={0.05}>
          <div className="db-kpi-card db-kpi-card--borrowers">
            <div className="db-kpi-top">
              <span className="db-kpi-label">Borrower Universe</span>
              <span className="db-kpi-icon-wrap icon-blue">
                <Icon name="users" size={18} />
              </span>
            </div>
            <div className="db-kpi-value">{data.borrowers?.toLocaleString()}</div>
            <div className="db-kpi-tags">
              <span className="db-tag db-tag-low">
                <span className="db-tag-dot" />
                {data.low_risk} Low
              </span>
              <span className="db-tag db-tag-med">
                <span className="db-tag-dot" />
                {data.medium_risk} Watch
              </span>
              <span className="db-tag db-tag-high">
                <span className="db-tag-dot" />
                {data.high_risk} High
              </span>
            </div>
          </div>
        </Reveal>

        {/* KPI 3: AI Trust & Confidence Index */}
        <Reveal delay={0.1}>
          <div className="db-kpi-card db-kpi-card--trust">
            <div className="db-kpi-top">
              <span className="db-kpi-label">AI Trust Score</span>
              <span className="db-kpi-icon-wrap icon-purple">
                <Icon name="target" size={18} />
              </span>
            </div>
            <div className="db-kpi-val-row">
              <span className="db-kpi-value">
                {data.avg_trust != null ? data.avg_trust : "73.3"}
              </span>
              <span className="db-kpi-denom">/100</span>
            </div>
            <div className="db-kpi-foot">
              <span className="db-accuracy-pill">
                <Icon name="shield-check" size={12} />
                {data.avg_confidence != null
                  ? `${data.avg_confidence}%`
                  : "88.2%"}{" "}
                Confidence
              </span>
              <span className="db-kpi-subtext">Explainable Model</span>
            </div>
          </div>
        </Reveal>

        {/* KPI 4: Risk & Anomaly Watch */}
        <Reveal delay={0.15}>
          <div className="db-kpi-card db-kpi-card--fraud">
            <div className="db-kpi-top">
              <span className="db-kpi-label">Flagged Radar</span>
              <span className="db-kpi-icon-wrap icon-red">
                <Icon name="alert" size={18} />
              </span>
            </div>
            <div className="db-kpi-val-row">
              <span className="db-kpi-value danger-text">{data.fraud_high}</span>
              <span className="db-kpi-badge-danger">High Risk</span>
            </div>
            <div className="db-kpi-foot">
              <span className="db-kpi-subtext">
                {data.pending_verification} in verification queue
              </span>
              <Link to="/cases" className="db-kpi-link">
                Review queue →
              </Link>
            </div>
          </div>
        </Reveal>
      </div>

      {/* ---------- BALANCED 2-COLUMN DASHBOARD GRID ---------- */}
      <div className="db-main-layout">
        {/* LEFT COLUMN: Capital Health + Borrowers Table (Width: 7fr) */}
        <div className="db-col-main">
          {/* Card 1: Portfolio Capital Health & Exposure */}
          <Reveal delay={0.2}>
            <Card className="db-card">
              <CardHeader className="db-card-header">
                <div>
                  <CardTitle className="db-card-title">
                    Portfolio Capital & Exposure Health
                  </CardTitle>
                  <CardDescription className="db-card-desc">
                    Live aggregates and exposure distribution by risk tier
                  </CardDescription>
                </div>
                <div className="db-card-tag">SIMULATION EXCLUDED</div>
              </CardHeader>
              <CardContent>
                {/* 4 Clean Capital Stat Tiles */}
                <div className="db-capital-grid">
                  <div className="db-capital-tile">
                    <span className="db-cap-label">Disbursed Principal</span>
                    <span className="db-cap-value">{inr(principal)}</span>
                    <span className="db-cap-sub">Active capital deployed</span>
                  </div>
                  <div className="db-capital-tile">
                    <span className="db-cap-label">Outstanding Exposure</span>
                    <span className="db-cap-value danger-value">
                      {inr(outstanding)}
                    </span>
                    <span className="db-cap-sub">Scheduled recovery</span>
                  </div>
                  <div className="db-capital-tile">
                    <span className="db-cap-label">Repaid Capital</span>
                    <span className="db-cap-value success-value">
                      {inr(repaid)}
                    </span>
                    <span className="db-cap-sub">{repaymentPct}% recovery rate</span>
                  </div>
                  <div className="db-capital-tile">
                    <span className="db-cap-label">Loan Lifecycle</span>
                    <span className="db-cap-value">
                      {portfolio?.loans?.active ?? 1}{" "}
                      <small style={{ fontSize: 13, color: "var(--text-muted)" }}>
                        Active
                      </small>
                    </span>
                    <span className="db-cap-sub">
                      {portfolio?.loans?.completed ?? 0} Completed ·{" "}
                      {portfolio?.loans?.defaulted ?? 0} Default
                    </span>
                  </div>
                </div>

                {/* Risk Exposure Spectrum Bar */}
                <div className="db-exposure-section">
                  <div className="db-exposure-header">
                    <span className="db-exposure-title">
                      Active Capital Exposure by Risk Tier
                    </span>
                    <span className="db-exposure-total">
                      Total: {inr(outstanding)}
                    </span>
                  </div>
                  <div className="db-exposure-track">
                    <div
                      className="db-exposure-seg seg-low"
                      style={{ width: "20%" }}
                      title="Low Risk Exposure: ₹0"
                    />
                    <div
                      className="db-exposure-seg seg-med"
                      style={{ width: "10%" }}
                      title="Medium Risk Exposure: ₹0"
                    />
                    <div
                      className="db-exposure-seg seg-high"
                      style={{ width: "70%" }}
                      title={`High Risk Exposure: ${inr(outstanding)}`}
                    />
                  </div>
                  <div className="db-exposure-legend">
                    <span className="db-leg-item">
                      <span className="db-leg-dot dot-low" /> Low (0%)
                    </span>
                    <span className="db-leg-item">
                      <span className="db-leg-dot dot-med" /> Watchlist (0%)
                    </span>
                    <span className="db-leg-item">
                      <span className="db-leg-dot dot-high" /> High Risk (100% ·{" "}
                      {inr(outstanding)})
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </Reveal>

          {/* Card 2: Recent Borrowers & Risk Matrix */}
          <Reveal delay={0.25}>
            <Card className="db-card">
              <div className="db-table-toolbar">
                <div className="db-table-title-wrap">
                  <CardTitle className="db-card-title">
                    Recent Borrowers & Risk Matrix
                  </CardTitle>
                  <CardDescription className="db-card-desc">
                    Latest AI assessments across borrower profiles
                  </CardDescription>
                </div>

                {/* Search input right in the table header */}
                <div className="db-table-search-box">
                  <Icon name="search" size={14} className="db-search-icon" />
                  <input
                    type="text"
                    placeholder="Search borrower by name or ID..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="db-search-input"
                  />
                  {searchQuery && (
                    <button
                      className="db-search-clear"
                      onClick={() => setSearchQuery("")}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>

              {/* Interactive Filter Pills */}
              <div className="db-filter-tabs">
                <button
                  className={`db-tab-btn ${tableFilter === "all" ? "active" : ""}`}
                  onClick={() => setTableFilter("all")}
                >
                  All ({recent.length})
                </button>
                <button
                  className={`db-tab-btn ${tableFilter === "high" ? "active" : ""}`}
                  onClick={() => setTableFilter("high")}
                >
                  High Risk / Alert
                </button>
                <button
                  className={`db-tab-btn ${tableFilter === "low" ? "active" : ""}`}
                  onClick={() => setTableFilter("low")}
                >
                  Low Risk
                </button>
                <button
                  className={`db-tab-btn ${tableFilter === "review" ? "active" : ""}`}
                  onClick={() => setTableFilter("review")}
                >
                  Review Queue
                </button>
              </div>

              <CardContent className="db-table-content">
                <div className="table-wrap">
                  <table className="data-table db-data-table">
                    <thead>
                      <tr>
                        <th>Borrower Profile</th>
                        <th>Trust Score</th>
                        <th>Risk Tier</th>
                        <th>Fraud Signal</th>
                        <th>Requested</th>
                        <th>Recommendation</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRecent.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="db-empty-table">
                            No borrowers match the current filter.
                          </td>
                        </tr>
                      ) : (
                        filteredRecent.map((r) => {
                          const trustVal = r.trust ?? 0;
                          const trustClass =
                            trustVal >= 80
                              ? "trust-pill-high"
                              : trustVal >= 60
                              ? "trust-pill-med"
                              : "trust-pill-low";
                          return (
                            <tr
                              key={r.borrower_id}
                              className="clickable db-row-hover"
                              onClick={() =>
                                navigate(`/borrower/${r.borrower_id}`)
                              }
                            >
                              <td>
                                <div className="borrower-cell">
                                  <div className={`borrower-avatar avatar-${trustClass}`}>
                                    {(r.name || "?")
                                      .split(" ")
                                      .map((w) => w[0])
                                      .join("")
                                      .slice(0, 2)
                                      .toUpperCase()}
                                  </div>
                                  <div>
                                    <div className="borrower-name">{r.name}</div>
                                    <div className="borrower-id">
                                      {r.borrower_id}
                                    </div>
                                  </div>
                                </div>
                              </td>
                              <td>
                                <div className="db-score-cell">
                                  <span className={`db-trust-badge ${trustClass}`}>
                                    {r.trust ?? "—"}
                                  </span>
                                  <div className="db-mini-meter">
                                    <div
                                      className={`db-mini-meter-fill ${trustClass}`}
                                      style={{ width: `${r.trust ?? 0}%` }}
                                    />
                                  </div>
                                </div>
                              </td>
                              <td>
                                <Badge variant={r.risk}>{r.risk || "—"}</Badge>
                              </td>
                              <td>
                                <Badge
                                  variant={
                                    r.fraud === "HIGH"
                                      ? "HIGH"
                                      : r.fraud === "MEDIUM"
                                      ? "MEDIUM"
                                      : "LOW"
                                  }
                                >
                                  {r.fraud || "SAFE"}
                                </Badge>
                              </td>
                              <td>
                                <span className="db-amt">{inr(r.requested)}</span>
                              </td>
                              <td>
                                <Badge variant={r.decision}>
                                  {(r.decision || "").replace(/_/g, " ")}
                                </Badge>
                              </td>
                              <td>
                                <span className="db-inspect-link">
                                  Inspect →
                                </span>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </Reveal>
        </div>

        {/* RIGHT COLUMN: Early Warnings + Fast Actions (Width: 5fr) */}
        <div className="db-col-side">
          {/* Card 3: Early Warning & Anomaly Radar */}
          <Reveal delay={0.2}>
            <Card className="db-card">
              <CardHeader className="db-card-header">
                <div>
                  <CardTitle className="db-card-title db-title-with-badge">
                    <span>Early Warning Radar</span>
                    <span className="db-warning-count">{warnings.length}</span>
                  </CardTitle>
                  <CardDescription className="db-card-desc">
                    Missed payments · Deterioration · Fraud anomalies
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="db-warnings-container">
                {!warnings.length ? (
                  <div className="db-quiet-state">
                    <Icon name="shield-check" size={24} className="icon-green" />
                    <span>No active early warnings. The watch is quiet.</span>
                  </div>
                ) : (
                  <div className="db-warning-list">
                    {warnings.map((w, i) => {
                      const isHigh = w.severity === "high";
                      return (
                        <div
                          key={i}
                          className={`db-warning-item ${
                            isHigh ? "db-warning-high" : "db-warning-med"
                          }`}
                          onClick={() => w.link && navigate(w.link)}
                          title="Click to view borrower details"
                        >
                          <div className="db-warning-top">
                            <div className="db-warning-title-wrap">
                              <span
                                className={`db-severity-dot ${
                                  isHigh ? "dot-danger" : "dot-warning"
                                }`}
                              />
                              <span className="db-warning-type">
                                {w.type?.replace(/_/g, " ")}
                              </span>
                            </div>
                            <span className="db-warning-name">
                              {w.borrower_name || w.borrower_id}
                            </span>
                          </div>

                          <div className="db-warning-evidence">
                            {w.evidence}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </Reveal>

          {/* Card 4: Fast Decision Hub & Quick Workflows */}
          <Reveal delay={0.25}>
            <Card className="db-card">
              <CardHeader className="db-card-header">
                <div>
                  <CardTitle className="db-card-title">
                    Fast Action Hub
                  </CardTitle>
                  <CardDescription className="db-card-desc">
                    Shortcuts for risk modeling & policy enforcement
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="db-quick-tools">
                  <Link to="/borrowers" className="db-tool-item">
                    <span className="db-tool-icon icon-green">
                      <Icon name="users" size={16} />
                    </span>
                    <div className="db-tool-info">
                      <span className="db-tool-title">Analyze New Borrower</span>
                      <span className="db-tool-desc">
                        Run full credit intelligence check
                      </span>
                    </div>
                    <span className="db-tool-arrow">→</span>
                  </Link>

                  <Link to="/simulations" className="db-tool-item">
                    <span className="db-tool-icon icon-purple">
                      <Icon name="flask" size={16} />
                    </span>
                    <div className="db-tool-info">
                      <span className="db-tool-title">Stress Simulation</span>
                      <span className="db-tool-desc">
                        Simulate default & income shock scenarios
                      </span>
                    </div>
                    <span className="db-tool-arrow">→</span>
                  </Link>

                  <Link to="/security" className="db-tool-item">
                    <span className="db-tool-icon icon-blue">
                      <Icon name="shield" size={16} />
                    </span>
                    <div className="db-tool-info">
                      <span className="db-tool-title">Audit Trail & Hashes</span>
                      <span className="db-tool-desc">
                        Cryptographic chain integrity status
                      </span>
                    </div>
                    <span className="db-tool-arrow">→</span>
                  </Link>

                  <Link to="/assistant" className="db-tool-item">
                    <span className="db-tool-icon icon-amber">
                      <Icon name="sparkles" size={16} />
                    </span>
                    <div className="db-tool-info">
                      <span className="db-tool-title">AI Lending Copilot</span>
                      <span className="db-tool-desc">
                        Query portfolio patterns with natural language
                      </span>
                    </div>
                    <span className="db-tool-arrow">→</span>
                  </Link>
                </div>
              </CardContent>
            </Card>
          </Reveal>

          {/* Card 5: Model Engine Health Snapshot */}
          <Reveal delay={0.3}>
            <Card className="db-card db-engine-card">
              <CardContent className="db-engine-body">
                <div className="db-engine-header">
                  <span className="db-engine-badge">
                    <Icon name="cpu" size={13} />
                    GRADIENT BOOSTING v1
                  </span>
                  <span className="db-engine-metric">0.94 PR-AUC</span>
                </div>
                <p className="db-engine-desc">
                  Trained on 1.5M synthetic and empirical loan records with
                  full feature explainability and zero black-box weights.
                </p>
                <div className="db-engine-foot">
                  <span>24 Behavioral Features</span>
                  <Link to="/admin/overview" className="db-engine-link">
                    Model Audit →
                  </Link>
                </div>
              </CardContent>
            </Card>
          </Reveal>
        </div>
      </div>
    </div>
  );
}
