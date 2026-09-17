import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../components/ui/Toast";
import { borrowers, documents, simulation, inr } from "../lib/api";
import { intel } from "../lib/api";
import PageHeader from "../components/layout/PageHeader";
import Tabs from "../components/ui/Tabs";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Card, { CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/Card";
import RiskScore from "../components/risk/RiskScore";
import TrustScoreHero from "../components/risk/TrustScoreHero";
import CreditRiskPanel from "../components/risk/CreditRiskPanel";
import Gauge from "../components/risk/Gauge";
import CopyButton from "../components/ui/CopyButton";
import { downloadJSON } from "../lib/export";
import DecisionBadge from "../components/risk/DecisionBadge";
import CashFlowChart from "../components/charts/CashFlowChart";
import useCountUp from "../hooks/useCountUp";
import NetworkTab from "../components/graph/NetworkTab";
import AuditTimeline from "../components/audit/AuditTimeline";
import EmptyState from "../components/ui/EmptyState";
import Icon from "../components/ui/Icon";
import ErrorState from "../components/ui/ErrorState";
import BorrowerIntelligence from "../components/risk/BorrowerIntelligence";
import { SkeletonCard } from "../components/ui/Skeleton";
import "./BorrowerDetails.css";
import "./BorrowerProfile.css";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "cashflow", label: "Cash Flow" },
  { key: "repayment", label: "Repayment" },
  { key: "intelligence", label: "Financial Intelligence" },
  { key: "credit", label: "Credit Intelligence" },
  { key: "documents", label: "Documents" },
  { key: "network", label: "Network" },
  { key: "fraud", label: "Fraud & Trust" },
  { key: "explain", label: "Explainability" },
  { key: "recommend", label: "Recommendation" },
  { key: "audit", label: "Audit" },
];
const TAB_KEYS = new Set(TABS.map((t) => t.key));

export default function BorrowerDetails() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { session } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState(TAB_KEYS.has(searchParams.get("tab")) ? searchParams.get("tab") : "overview");
  const [borrower, setBorrower] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [financials, setFinancials] = useState([]);
  const [cashflow, setCashflow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drafting, setDrafting] = useState(false);
  const [evidence, setEvidence] = useState(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [changed, setChanged] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [b, snaps, a] = await Promise.all([
        borrowers.get(id, session.token),
        borrowers.financials(id, session.token),
        borrowers.analysis(id, session.token).catch(() => null),
      ]);
      setBorrower(b);
      setFinancials(snaps);
      setAnalysis(a);
      borrowers.cashflow(id, session.token).then(setCashflow).catch(() => setCashflow(null));
      intel.riskHistory(id, session.token).then((h) => setChanged(h.what_changed)).catch(() => {});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [id, session]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const requested = searchParams.get("tab");
    if (requested && TAB_KEYS.has(requested) && requested !== tab) setTab(requested);
    else if (requested && !TAB_KEYS.has(requested)) setSearchParams({ tab }, { replace: true });
  }, [searchParams, tab]);

  const handleTabChange = (key) => {
    setTab(key);
    setSearchParams({ tab: key });
  };

  const reRun = async () => {
    toast.info("Re-running analysis…");
    try {
      await borrowers.analyze(id, session.token);
      await load();
      toast.success("Analysis updated");
    } catch (e) { toast.error("Re-run failed: " + e.message); }
  };

  const toggleEvidence = async () => {
    if (evidenceOpen) { setEvidenceOpen(false); return; }
    try {
      const ev = await borrowers.evidence(id, session.token);
      setEvidence(ev);
      setEvidenceOpen(true);
    } catch (e) { toast.error("Failed to load evidence: " + e.message); }
  };

  if (loading) return (
    <div className="bp-dark">
      <PageHeader title="Loading…" />
      <div className="borrower-skeleton"><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>
    </div>
  );
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!borrower) return null;

  const a = analysis;
  const r = a?.recommendation;
  const fin = a?.financial;

  return (
    <div className="bp-dark">
      <div className="bd-back">
        <button className="bd-back-link" onClick={() => navigate("/borrowers")}>← All borrowers</button>
      </div>

      <div className="bp-layout">
        <aside className="bp-rail">
          <div className="bp-idrow">
            <div className="bp-avatar">
              {(borrower.name || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}
            </div>
            <div>
              <div className="bp-name">{borrower.name}</div>
              <div className="bp-role">{borrower.employment_type || "Borrower"} · {borrower.city}</div>
            </div>
          </div>
          <div className="bp-idline">
            <Icon name="idcard" size={14} />
            <span>{borrower.borrower_id}</span>
            <CopyButton text={borrower.borrower_id} label="ID" />
          </div>
          <div className="bp-badges">
            <Badge variant={borrower.verification_bucket}>{(borrower.verification_bucket || "").replace(/_/g, " ")}</Badge>
            {r?.decision && <DecisionBadge decision={r.decision} />}
          </div>

          <div className="bp-sect">Contact</div>
          <dl className="bp-contact">
            {borrower.phone && <div><dt>Phone</dt><dd>{borrower.phone}</dd></div>}
            {borrower.email && <div><dt>Email</dt><dd>{borrower.email}</dd></div>}
            <div><dt>Location</dt><dd>{[borrower.city, borrower.address_line].filter(Boolean).join(" · ") || "—"}</dd></div>
            <div><dt>Occupation</dt><dd style={{ textTransform: "capitalize" }}>{borrower.employment_type || "—"}{borrower.employment_years ? ` · ${borrower.employment_years}y` : ""}</dd></div>
            <div><dt>Account age</dt><dd>{borrower.account_age_months != null ? `${borrower.account_age_months} months` : "—"}</dd></div>
          </dl>

          <div className="bp-sect">Loan ask</div>
          <div className="bp-stats">
            <div><small>Requested</small><b>{borrower.requested_amount != null ? inr(borrower.requested_amount) : "—"}</b></div>
            <div><small>Tenure</small><b>{borrower.tenure_months != null ? `${borrower.tenure_months} mo` : "—"}</b></div>
          </div>

          <div className="bp-activity">
            <span className="bp-pulse" />
            {(borrower.verification_bucket || "").replace(/_/g, " ") || "On record"} · {borrower.account_age_months || 0} mo history
          </div>
        </aside>

        <div className="bp-main">
          {a && (
            <TrustScoreHero
              score={a.trust_score}
              confidence={r?.confidence}
              factors={[...(a.factors || [])].sort((x, y) => Math.abs(y.weight ?? y.score ?? 0) - Math.abs(x.weight ?? x.score ?? 0))}
              analysisId={a.id}
            />
          )}
          {a && (
            <div className="bp-gauges">
              <div className="bp-panel">
                <small>Repayment risk</small>
                <Gauge label="REPAYMENT RISK" value={a.risk_score} display={a.risk_level}
                  color={a.risk_level === "LOW" ? "var(--success)" : a.risk_level === "MEDIUM" ? "var(--warning)" : "var(--danger)"} />
              </div>
              <div className="bp-panel">
                <small>Fraud risk</small>
                <Gauge label="FRAUD RISK" value={a.fraud_score} display={a.fraud_risk}
                  color={a.fraud_risk === "LOW" ? "var(--success)" : a.fraud_risk === "MEDIUM" ? "var(--warning)" : "var(--danger)"} />
              </div>
              <div className="bp-panel">
                <small>Confidence</small>
                <div className="bp-conf-v">{r?.confidence ?? "—"}%</div>
                <div className="bp-conf-bar"><div className="bp-conf-fill" style={{ width: `${r?.confidence || 0}%` }} /></div>
                <div className="bp-conf-sub">model certainty in this verdict</div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="bp-toolbar">
        <Button variant="secondary" size="sm" onClick={toggleEvidence}><Icon name="file-text" size={14} /> Evidence</Button>
        <Button variant="secondary" size="sm" onClick={() => {
          downloadJSON(`${id}-analysis.json`, { borrower, analysis, financials });
          toast.success("Analysis exported");
        }}><Icon name="download" size={14} /> Export</Button>
        <Button variant="secondary" size="sm" onClick={() => window.print()}><Icon name="printer" size={14} /> Print</Button>
        <Button variant="secondary" size="sm" onClick={async () => {
          const url = window.location.href;
          try {
            if (navigator.share) await navigator.share({ title: borrower.name, url });
            else { await navigator.clipboard.writeText(url); toast.success("Link copied"); }
          } catch { /* dismissed */ }
        }}>Share</Button>
        <Button variant="primary" size="sm" onClick={reRun} disabled={session?.role === "guest"} title={session?.role === "guest" ? "Sign in as a lender for this action" : "Re-run analysis"}>Re-run</Button>
        <Button variant="primary" size="sm" disabled={drafting} onClick={async () => {
          if (session?.role === "guest") return toast.error("Guests are read-only — sign in as a lender for these actions");
          if (drafting) return;
          setDrafting(true);
          try {
            const { loans } = await import("../lib/api");
            const r = await loans.createRequest({
              borrower_id: id, amount: borrower.requested_amount || 50000,
              interest_rate: 12, duration_months: borrower.tenure_months || 12,
              purpose: borrower.purpose || "",
            }, session.token);
            toast.success(r.duplicate ? "Draft already exists — opening it" : "Loan request drafted");
            navigate(`/loan-requests/${r.id}`);
          } catch (e) { toast.error("Request failed: " + e.message); }
          finally { setDrafting(false); }
        }}>{drafting ? "Drafting…" : "New loan request"}</Button>
      </div>
      {evidenceOpen && evidence && (
        <Card style={{ marginBottom: 16 }}>
          <CardHeader>
            <CardTitle>Evidence · Analysis #{evidence.analysis_id}</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.entries(evidence.groups || {}).map(([cat, items]) => (
              <div key={cat} style={{ marginBottom: 12 }}>
                <h4 style={{ textTransform: "capitalize", margin: "0 0 6px", fontSize: 14 }}>{cat.replace(/_/g, " ")}</h4>
                {items.map((item, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 13, borderBottom: "1px solid var(--border)" }}>
                    <span style={{ color: "var(--text-muted)" }}>{item.label}</span>
                    <span>{item.value}</span>
                  </div>
                ))}
              </div>
            ))}
            {!Object.keys(evidence.groups || {}).length && <EmptyState title="No evidence recorded" />}
          </CardContent>
        </Card>
      )}

      <Tabs tabs={TABS} active={tab} onChange={handleTabChange} />

      <div className="bd-tab-content">
        {tab === "overview" && a && (
          <div className="bp-ov-grid">
            <Card>
              <CardHeader><CardTitle>Cash flow trend</CardTitle><CardDescription>Monthly income vs expenses</CardDescription></CardHeader>
              <CardContent>
                <CashFlowChart title="" points={(cashflow?.snapshots?.length ? cashflow.snapshots : financials).map((s) => ({
                    label: s.label || `M${s.month}`,
                    values: { income: s.income || 0, expenses: s.expenses || 0 },
                  }))}
                  format={(v) => inr(Math.round(v))}
                  series={[
                    { key: "income", label: "Income", color: "var(--success)" },
                    { key: "expenses", label: "Expenses", color: "var(--warning)" },
                  ]} />
                {fin && (
                  <div style={{ marginTop: 14 }}>
                    <div className="bp-ratio"><span>Debt-to-income</span><b>{fin.dti}</b></div>
                    <div className="bp-ratio"><span>Repayment capacity</span><b>{(fin.repayment_capacity * 100).toFixed(0)}%</b></div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Current Recommendation</CardTitle><CardDescription>{r?.rationale}</CardDescription></CardHeader>              <CardContent>
                <div className="bd-rec-amount">{inr(r?.recommended_amount)}</div>
                <p className="bd-rec-detail">@ {r?.interest_rate}% · {r?.duration_months} mo · EMI <b>{inr(r?.monthly_payment)}</b></p>
                <DecisionBadge decision={r?.decision} />
                <p style={{ marginTop: 12 }}><button className="link-btn" onClick={() => handleTabChange("recommend")}>Open simulator →</button></p>
              </CardContent>
            </Card>
          </div>
        )}
        {tab === "overview" && changed && (
          <Card style={{ marginTop: 16 }}>
            <CardHeader>
              <CardTitle>What changed?</CardTitle>
              <CardDescription>
                Analysis #{changed.from_analysis} → #{changed.to_analysis} · risk {changed.risk.before} → {changed.risk.after} ({changed.risk.delta >= 0 ? "+" : ""}{changed.risk.delta})
              </CardDescription>
            </CardHeader>
            <CardContent>
              {(changed.top_factor_moves || []).map((f) => (
                <div key={f.code} className="audit-row">
                  <div><b>{f.title}</b> <span style={{ color: "var(--text-muted)" }}>{f.before} → {f.after}</span></div>
                  <b style={{ color: f.delta > 0 ? "var(--danger)" : "var(--success)" }}>{f.delta > 0 ? "+" : ""}{f.delta}</b>
                </div>
              ))}
              {!(changed.top_factor_moves || []).length && <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No material factor moves between the last two analyses.</p>}
            </CardContent>
          </Card>
        )}

        {tab === "cashflow" && <CashFlowTab financials={financials} cashflow={cashflow} />}
        {tab === "repayment" && <RepaymentTab borrower={borrower} fin={fin} />}
        {["intelligence", "credit"].includes(tab) && <BorrowerIntelligence bid={id} session={session} view={tab} />}
        {tab === "documents" && <DocumentsTab borrower={borrower} bid={id} token={session.token} toast={toast} guest={session?.role === "guest"} />}
        {tab === "network" && <NetworkTab bid={id} token={session.token} guest={session?.role === "guest"} />}
        {tab === "fraud" && <FraudTrustTab analysis={a} />}
        {tab === "explain" && <ExplainTab analysis={a} />}
        {tab === "recommend" && <RecommendTab borrower={borrower} recommendation={r} bid={id} token={session.token} toast={toast} />}
        {tab === "audit" && <AuditTab bid={id} token={session.token} />}
      </div>
    </div>
  );
}

/* --- Sub-tabs --- */

function CashFlowTab({ financials, cashflow }) {
  const snaps = cashflow?.snapshots?.length ? cashflow.snapshots : financials;
  const moneyPoints = (snaps || []).map((s) => ({
    label: s.label || `M${s.month}`,
    values: {
      income: s.income || 0,
      expenses: s.expenses || 0,
      net: (s.income || 0) - (s.expenses || 0),
    },
  }));
  const oblPoints = (cashflow?.monthly_obligations || []).map((m) => ({
    label: m.month,
    values: { due: m.due || 0, paid: m.paid_actual || 0 },
  }));
  const sum = cashflow?.summary;
  if (!moneyPoints.length && !oblPoints.length) {
    return <EmptyState title="No financial data" description="Financial snapshots are not available for this borrower." />;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {sum && <CashSummary sum={sum} />}
      {!!moneyPoints.length && (
        <Card>
          <CardContent>
            <CashFlowChart title="Money in vs out" subtitle="Monthly income, expenses and net surplus"
              points={moneyPoints} format={(v) => inr(Math.round(v))}
              series={[
                { key: "income", label: "Income", color: "var(--success)" },
                { key: "expenses", label: "Expenses", color: "var(--warning)" },
                { key: "net", label: "Net", color: "var(--primary)" },
              ]} />
          </CardContent>
        </Card>
      )}
      {!!oblPoints.length && (
        <Card>
          <CardContent>
            <CashFlowChart title="Loan obligations" subtitle="EMI due vs actually paid per month"
              points={oblPoints} format={(v) => inr(Math.round(v))}
              series={[
                { key: "due", label: "Due", color: "var(--danger)" },
                { key: "paid", label: "Paid", color: "var(--success)" },
              ]} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function CashSummary({ sum }) {
  const net = useCountUp(sum.net || 0);
  const paid = useCountUp(sum.total_paid_actual || 0);
  const overdue = useCountUp(sum.overdue || 0);
  const cards = [
    ["Net surplus", inr(Math.round(net)), sum.net >= 0 ? "var(--success)" : "var(--danger)"],
    ["Paid to loans", inr(Math.round(paid)), "var(--text-primary)"],
    ["Overdue", inr(Math.round(overdue)), "var(--danger)"],
    ["Next due", sum.next_due ? `${inr(sum.next_due.amount)} · ${sum.next_due.date}` : "—", "var(--text-primary)"],
  ];
  return (
    <div className="cfc-cards">
      {cards.map(([l, v, c]) => (
        <div key={l} className="cfc-card">
          <div className="cfc-card-v" style={{ color: c }}>{v}</div>
          <div className="cfc-card-l">{l}</div>
        </div>
      ))}
    </div>
  );
}

function RepaymentTab({ borrower: b, fin }) {
  const rc = fin?.repayment_capacity;
  return (
    <div className="bd-grid">
      <Card>
        <CardHeader><CardTitle>Repayment Capacity</CardTitle></CardHeader>
        <CardContent>
          <div className="bd-rec-amount">{rc != null ? `${(rc * 100).toFixed(1)}%` : "—"}</div>
          <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>of monthly income available for repayment</p>
          <div className="bd-metric-bar" style={{ marginTop: 12 }}><div className="bd-metric-fill" style={{ width: `${((rc || 0) * 100)}%`, background: "var(--success)" }} /></div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Financial Summary</CardTitle></CardHeader>
        <CardContent>
          <div className="bd-ledger">
            {[
              ["Average income", fin?.avg_income != null ? inr(fin.avg_income) : "—"],
              ["Average expenses", fin?.avg_expenses != null ? inr(fin.avg_expenses) : "—"],
              ["Average debt", fin?.avg_debt != null ? inr(fin.avg_debt) : "—"],
              ["Debt-to-income", fin?.dti != null ? fin.dti.toFixed(2) : "—"],
              ["Loan-to-income", fin?.lti != null ? fin.lti.toFixed(2) : "—"],
            ].map(([k, v]) => (
              <div key={k} className="bd-ledger-row"><span>{k}</span><b>{v}</b></div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function DocumentsTab({ borrower: b, bid, token, toast, guest }) {
  const [docs, setDocs] = useState([]);
  const [newType, setNewType] = useState("identity");
  const [newFile, setNewFile] = useState("");
  const [uploading, setUploading] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [rot, setRot] = useState(0);
  const needLender = () => {
    if (guest) { toast.error("Guests are read-only — sign in with Phone OTP for lender actions"); return true; }
    return false;
  };

  const loadDocs = useCallback(async () => {
    try { setDocs(await documents.list(bid, token)); } catch {}
  }, [bid, token]);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  const addDoc = async () => {
    if (needLender()) return;
    if (!newFile.trim()) return toast.error("Enter a file name");
    try {
      await documents.create(bid, { doc_type: newType, file_name: newFile.trim() }, token);
      toast.success("Document registered");
      setNewFile("");
      loadDocs();
    } catch (e) { toast.error("Register failed: " + e.message); }
  };

  const updateStatus = async (docId, status) => {
    if (needLender()) { loadDocs(); return; }
    try {
      await documents.patch(docId, { status }, token);
      toast.success("Document status updated");
      loadDocs();
    } catch (e) { toast.error("Update failed: " + e.message); loadDocs(); }
  };

  const viewDoc = async (d) => {
    try {
      const r = await fetch(`/api/ls/documents/${d.id}/file`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || r.statusText);
      }
      const blob = await r.blob();
      setZoom(1);
      setRot(0);
      setViewing({ url: URL.createObjectURL(blob), mime: blob.type, name: d.file_name });
    } catch (e) { toast.error("Cannot open file: " + e.message); }
  };

  const closeViewer = () => {
    if (viewing?.url) URL.revokeObjectURL(viewing.url);
    setViewing(null);
  };

  const ico = { identity: "idcard", bank_statement: "briefcase", income_document: "file-text", salary_slip: "clipboard", business_document: "home" };

  return (
    <>
    <Card>
      <CardHeader><CardTitle>Document Center</CardTitle><CardDescription>Verification derived from structured checks</CardDescription></CardHeader>
      <CardContent>
        {docs.length ? docs.map((d) => (
          <div key={d.id} className="doc-row">
            <span className="doc-icon"><Icon name={ico[d.doc_type] || "file-text"} size={18} /></span>
            <div className="doc-info">
              <b style={{ textTransform: "capitalize" }}>{d.doc_type.replace(/_/g, " ")}</b>
              <small>{d.file_name} · quality {d.quality_score}/100</small>
            </div>
            <Badge variant={d.status}>{d.status.replace(/_/g, " ")}</Badge>
            <span title={`Pipeline: ${d.pipeline_status || "PENDING"} · OCR: ${d.ocr_status || "NOT_AVAILABLE"} · Scan: ${d.scan_status || "NOT_AVAILABLE"}`}
              style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {d.pipeline_status || "PENDING"}
            </span>
            <select value={d.status} onChange={(e) => updateStatus(d.id, e.target.value)} className="doc-select" disabled={guest}>
              <option>needs_review</option><option>verified</option><option>suspicious</option>
            </select>
            <Button variant="ghost" size="sm" onClick={() => viewDoc(d)}>View</Button>
          </div>
        )) : <EmptyState title="No documents on file" icon="file-text" />}

        <div style={{ marginTop: 20 }}>
          <h4 style={{ fontSize: 14, marginBottom: 10 }}>Register document</h4>
          <div className="doc-add-row">
            <select value={newType} onChange={(e) => setNewType(e.target.value)} className="filter-select">
              <option value="identity">Identity</option>
              <option value="bank_statement">Bank statement</option>
              <option value="income_document">Income document</option>
              <option value="salary_slip">Salary slip</option>
              <option value="business_document">Business document</option>
            </select>
            <input type="text" placeholder="e.g. b10001_bank_statement.pdf" value={newFile} onChange={(e) => setNewFile(e.target.value)} className="filter-search-input" style={{ flex: 1 }} />
            <Button variant="secondary" size="sm" onClick={addDoc} disabled={guest} title={guest ? "Sign in with Phone OTP for lender actions" : "Register document"}>＋ Register</Button>
          </div>
          <div className="doc-add-row" style={{ marginTop: 10 }}>
            <label className="filter-search-input" style={{ flex: 1, cursor: guest ? "not-allowed" : "pointer", opacity: guest ? 0.5 : 1 }}>
              {uploading ? "Uploading…" : <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Icon name="paperclip" size={13} /> Upload file (PDF/PNG/JPG, ≤2MB)…</span>}
              <input type="file" accept=".pdf,.png,.jpg,.jpeg" disabled={guest || uploading} style={{ display: "none" }}
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  if (needLender()) return;
                  if (f.size > 2000000) return toast.error("File exceeds 2MB cap");
                  try {
                    setUploading(true);
                    const fd = new FormData();
                    fd.append("doc_type", newType);
                    fd.append("file", f);
                    const r = await fetch(`/api/ls/borrowers/${bid}/documents/upload`, {
                      method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd,
                    });
                    if (!r.ok) {
                      const body = await r.json().catch(() => ({}));
                      throw new Error(body.detail || r.statusText);
                    }
                    toast.success("Uploaded — verification job queued");
                    setTimeout(loadDocs, 2500);
                  } catch (err) { toast.error("Upload failed: " + err.message); }
                  finally { setUploading(false); e.target.value = ""; }
                }} />
            </label>
          </div>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
            Verification runs asynchronously (see Admin → Background Jobs). OCR and malware-scan engines are not configured in this deployment — shown as NOT_AVAILABLE, never faked.
          </p>
        </div>
      </CardContent>
    </Card>
    {viewing && (
      <div className="modal-overlay" onClick={closeViewer}>
        <div className="modal-box" style={{ maxWidth: 860 }} onClick={(e) => e.stopPropagation()}>
          <div className="modal-head">
            <b>{viewing.name}</b>
            <span style={{ display: "flex", gap: 6 }}>
              <Button variant="ghost" size="sm" onClick={() => setZoom((z) => Math.min(3, +(z + 0.25).toFixed(2)))}>＋ Zoom</Button>
              <Button variant="ghost" size="sm" onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))}>－ Zoom</Button>
              <Button variant="ghost" size="sm" onClick={() => setRot((r) => (r + 90) % 360)}>⟳ Rotate</Button>
              <Button variant="ghost" size="sm" onClick={closeViewer}>✕ Close</Button>
            </span>
          </div>
          <div style={{ overflow: "auto", maxHeight: "70vh", display: "flex", justifyContent: "center", background: "rgba(0,0,0,.35)", borderRadius: 8 }}>
            {viewing.mime.startsWith("image/") ? (
              <img src={viewing.url} alt={viewing.name} style={{ transform: `scale(${zoom}) rotate(${rot}deg)`, maxWidth: "100%", transition: "transform .15s" }} />
            ) : viewing.mime === "application/pdf" ? (
              <iframe src={viewing.url} title={viewing.name} style={{ width: "100%", height: "70vh", border: "none" }} />
            ) : (
              <p style={{ padding: 24, fontSize: 13 }}>Preview not available for {viewing.mime || "this file type"} — use download.</p>
            )}
          </div>
        </div>
      </div>
    )}
    </>
  );
}

function FraudTrustTab({ analysis: a }) {
  if (!a) return <EmptyState title="No analysis available" />;
  return (
    <div className="bd-grid">
      <Card>
        <CardHeader>
          <CardTitle>Fraud Intelligence</CardTitle>
          <CardDescription>Fraud risk: <Badge variant={a.fraud_risk === "HIGH" ? "HIGH" : a.fraud_risk === "MEDIUM" ? "MEDIUM" : "LOW"}>{a.fraud_risk}</Badge> ({a.fraud_score}/100)</CardDescription>
        </CardHeader>
        <CardContent>
          {a.signals?.length ? a.signals.map((s, i) => (
            <div key={i} className="signal-row">
              <div className="signal-info"><b>{s.title}</b><small>{s.evidence}</small></div>
              <Badge variant={s.severity === "high" ? "HIGH" : s.severity === "medium" ? "MEDIUM" : "LOW"}>{s.severity}</Badge>
            </div>
          )) : <EmptyState title="No fraud signals detected" icon="check-circle" description="All verification and behavior checks are clean." />}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Trust Intelligence · {a.trust_score}/100</CardTitle></CardHeader>
        <CardContent>
          {(a.trust_factors || []).map((f, i) => (
            <div key={i} className="trust-factor">
              <div className="trust-factor-header">
                <span className="trust-factor-name">{f.title}</span>
                <span className="trust-factor-score">{f.score}</span>
              </div>
              <div className="trust-factor-bar"><div className="trust-factor-fill" style={{ width: `${f.score}%`, background: f.score >= 60 ? "var(--success)" : f.score >= 40 ? "var(--warning)" : "var(--danger)" }} /></div>
              <div className="trust-factor-evidence">{f.evidence} <span style={{ color: "var(--text-muted)" }}>· weight {f.weight}%</span></div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function ExplainTab({ analysis: a }) {
  if (!a) return <EmptyState title="No analysis available" />;
  const up = (a.factors || []).filter((f) => f.impact === "raises").sort((x, y) => y.score * y.weight - x.score * x.weight).slice(0, 4);
  const down = (a.factors || []).filter((f) => f.impact === "lowers").sort((x, y) => x.score * x.weight - y.score * y.weight).slice(0, 4);

  return (
    <div className="bd-grid">
      <Card>
        <CardHeader><CardTitle>{a.risk_level} Repayment Risk — Why?</CardTitle><CardDescription>Risk score {a.risk_score}/100</CardDescription></CardHeader>
        <CardContent>
          <ul className="factor-list">
            {up.map((f, i) => (
              <li key={i} className="factor-item factor-negative">
                <b>{f.title}</b>
                {f.code === "ml_default_model" && <span className="ml-chip"><Icon name="cpu" size={12} style={{ display: "inline", verticalAlign: "-1px" }} /> ML Model</span>}
                <span> — {f.observed}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Positive Signals</CardTitle><CardDescription>What pulls risk down</CardDescription></CardHeader>
        <CardContent>
          <ul className="factor-list">
            {down.map((f, i) => (
              <li key={i} className="factor-item factor-positive">
                <b>{f.title}</b> — {f.observed}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function RecommendTab({ borrower: b, recommendation: r, bid, token, toast }) {
  const [sim, setSim] = useState(null);
  const [amt, setAmt] = useState(r?.recommended_amount || 50000);
  const [rate, setRate] = useState(r?.interest_rate || 12);
  const [dur, setDur] = useState(r?.duration_months || 12);

  const runSim = useCallback(async () => {
    try {
      const s = await simulation.run({ borrower_id: bid, amount: amt, interest_rate: rate, duration_months: dur }, token);
      setSim(s);
    } catch (e) { toast.error("Simulation failed: " + e.message); }
  }, [bid, amt, rate, dur, token]);

  useEffect(() => { runSim(); }, [runSim]);

  return (
    <div>
      <Card>
        <CardHeader><CardTitle>Loan Recommendation</CardTitle><CardDescription>{r?.rationale}</CardDescription></CardHeader>
        <CardContent>
          <div className="rec-grid">
            <div className="rec-cell"><small>Recommended loan</small><b>{inr(r?.recommended_amount)}</b></div>
            <div className="rec-cell"><small>Interest rate</small><b>{r?.interest_rate}%</b></div>
            <div className="rec-cell"><small>Duration</small><b>{r?.duration_months} mo</b></div>
            <div className="rec-cell"><small>Monthly payment</small><b>{inr(r?.monthly_payment)}</b></div>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
            Total repayment {inr(r?.total_repayment)} · burden {((r?.repayment_burden || 0) * 100).toFixed(0)}% of monthly income
          </p>
          <div className="decision-banner" style={{ marginTop: 12 }}><DecisionBadge decision={r?.decision} /><span style={{ marginLeft: 8 }}>{r?.rationale}</span></div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>What-If Simulator</CardTitle><CardDescription>Drag the controls — payment, burden and decision update immediately</CardDescription></CardHeader>
        <CardContent>
          <div className="sim-grid">
            <div className="sim-controls">
              <label className="sim-label">Loan amount · <b>{inr(amt)}</b><input type="range" min={5000} max={Math.max(100000, b.requested_amount)} step={1000} value={amt} onChange={(e) => setAmt(+e.target.value)} className="sim-range" /></label>
              <label className="sim-label">Interest rate · <b>{rate}%</b><input type="range" min={5} max={28} step={0.5} value={rate} onChange={(e) => setRate(+e.target.value)} className="sim-range" /></label>
              <label className="sim-label">Duration · <b>{dur} months</b><input type="range" min={1} max={36} step={1} value={dur} onChange={(e) => setDur(+e.target.value)} className="sim-range" /></label>
            </div>
            <div className="sim-results">
              <div className="rec-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <div className="rec-cell"><small>Monthly payment</small><b className="sim-big">{sim ? inr(sim.monthly_payment) : "—"}</b></div>
                <div className="rec-cell"><small>Total repayment</small><b>{sim ? inr(sim.total_repayment) : "—"}</b></div>
                <div className="rec-cell"><small>Repayment burden</small><b style={{ color: sim && sim.repayment_burden * 100 <= 30 ? "var(--success)" : sim && sim.repayment_burden * 100 <= 50 ? "var(--warning)" : "var(--danger)" }}>{sim ? `${(sim.repayment_burden * 100).toFixed(0)}%` : "—"}</b></div>
                <div className="rec-cell"><small>Decision</small><div>{sim ? <DecisionBadge decision={sim.decision} /> : "—"}</div></div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function AuditTab({ bid, token }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    borrowers.audit(bid, token).then(setEvents).catch(() => {}).finally(() => setLoading(false));
  }, [bid, token]);

  if (loading) return <SkeletonCard />;
  return (
    <Card>
      <CardHeader><CardTitle>Audit Trail</CardTitle></CardHeader>
      <CardContent>
        <AuditTimeline events={events} />
      </CardContent>
    </Card>
  );
}
