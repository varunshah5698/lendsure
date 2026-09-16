import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import SafeRiskCore from "../components/landing/SafeRiskCore";
import SafeApprovalWave from "../components/landing/SafeApprovalWave";
import Logo from "../components/ui/Logo";
import Icon from "../components/ui/Icon";
import "./Landing.css";

const fadeUp = { initial: { opacity: 0, y: 30 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-80px" }, transition: { duration: 0.7, ease: "easeOut" } };
const stagger = { initial: { opacity: 0, y: 20 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true } };

function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { session } = useAuth();
  const app = session ? "/dashboard" : "/auth";
  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);
  return (
    <nav className={`lp-nav ${scrolled ? "lp-nav-scrolled" : ""}`}>
      <div className="lp-nav-inner">
        <Link to="/" className="lp-nav-brand">
          <Logo size={36} />
          <div>
            <span className="lp-nav-name">LendSure</span>
            <span className="lp-nav-tag">TRUST & RISK INTELLIGENCE</span>
          </div>
        </Link>
        <div className={`lp-nav-links ${mobileOpen ? "lp-nav-open" : ""}`}>
          <a href="#product">Product</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#risk-engine">Risk Engine</a>
          <a href="#explainability">Explainability</a>
          <a href="#security">Security</a>
        </div>
        <div className="lp-nav-actions">
          {session ? (
            <Link to="/dashboard" className="lp-btn-primary">Open Dashboard →</Link>
          ) : (
            <>
              <Link to="/auth" className="lp-btn-ghost">Sign In</Link>
              <Link to="/auth" className="lp-btn-primary">Get Started →</Link>
            </>
          )}
        </div>
        <button className="lp-nav-mobile" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Menu">
          <Icon name={mobileOpen ? "x" : "menu"} size={18} />
        </button>
      </div>
    </nav>
  );
}

function Hero() {
  const { session } = useAuth();
  const app = session ? "/dashboard" : "/auth";
  return (
    <section className="lp-hero">
      <div className="lp-hero-bg">
        <div className="lp-hero-grid" />
        <div className="lp-hero-glow" />
      </div>
      <div className="lp-hero-content">
        <motion.div initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: "easeOut" }}>
          <h1 className="lp-hero-title">
            <span className="lp-hero-line">KNOW THE RISK</span>
            <span className="lp-hero-line">BEFORE YOU <span className="lp-hero-accent">LEND.</span></span>
          </h1>
        </motion.div>
        <motion.p className="lp-hero-sub" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4, duration: 0.8 }}>
          LendSure transforms borrower data into explainable trust, risk, and lending intelligence — so you can make decisions backed by evidence, not assumptions.
        </motion.p>
        <motion.div className="lp-hero-ctas" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6, duration: 0.7 }}>
          <Link to={app} className="lp-btn-primary lp-btn-lg">{session ? "Open Dashboard →" : "Analyze a Borrower →"}</Link>
          <a href="#how-it-works" className="lp-btn-outline lp-btn-lg">Explore the Intelligence</a>
        </motion.div>
        <motion.div className="lp-hero-badges" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1, duration: 0.8 }}>
          <span className="lp-badge">AI-powered</span>
          <span className="lp-badge">Explainable</span>
          <span className="lp-badge">Auditable</span>
        </motion.div>
      </div>
      <div className="lp-hero-3d">
        <div className="lp-hero-scene-wrap">
          <SafeRiskCore className="lp-hero-scene" />
        </div>
      </div>
    </section>
  );
}

function DataToDecision() {
  const stages = [
    { num: "01", title: "BORROWER", desc: "Income ₹1,20,000 · Debt ₹28,000 · History: Strong", icon: "user" },
    { num: "02", title: "LENDSURE ANALYZES", desc: "Income Stability · Repayment History · Debt Burden · Fraud Signals", icon: "search" },
    { num: "03", title: "INTELLIGENCE", desc: "Trust Score 96 · Repayment Risk LOW · Fraud Risk LOW · Confidence 97%", icon: "cpu" },
    { num: "04", title: "DECISION", desc: "APPROVE — Recommended ₹35,000 at 10% for 3 months", icon: "check-circle" },
  ];
  return (
    <section className="lp-section" id="how-it-works">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">FROM DATA<br />TO DECISION.</h2>
        <p className="lp-section-sub">One connected intelligence pipeline — from raw borrower data to explainable lending decisions.</p>
      </motion.div>
      <div className="lp-pipeline">
        {stages.map((s, i) => (
          <motion.div key={s.num} className="lp-pipeline-stage" {...stagger} transition={{ delay: i * 0.15, duration: 0.6 }}>
            <div className="lp-pipeline-num">{s.num}</div>
            <div className="lp-pipeline-icon"><Icon name={s.icon} size={30} /></div>
            <h3 className="lp-pipeline-title">{s.title}</h3>
            <p className="lp-pipeline-desc">{s.desc}</p>
            {i < stages.length - 1 && <div className="lp-pipeline-arrow">→</div>}
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function TrustScoreSection() {
  return (
    <section className="lp-section lp-section-dark" id="product">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">A SCORE ISN'T ENOUGH.<br />YOU NEED TO KNOW <span className="lp-hero-accent">WHY.</span></h2>
      </motion.div>
      <div className="lp-trust-layout">
        <motion.div className="lp-trust-score-card" {...fadeUp}>
          <div className="lp-trust-ring">
            <svg viewBox="0 0 120 120" className="lp-trust-svg">
              <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(25,26,35,0.15)" strokeWidth="6" />
              <circle cx="60" cy="60" r="52" fill="none" stroke="#191a23" strokeWidth="6"
                strokeDasharray={`${0.96 * 327} 327`} strokeLinecap="round"
                transform="rotate(-90 60 60)" />
            </svg>
            <div className="lp-trust-score-value">96</div>
          </div>
          <div className="lp-trust-score-label">Trust Score</div>
          <div className="lp-trust-score-grade">Excellent</div>
        </motion.div>
        <motion.div className="lp-trust-factors" {...fadeUp} transition={{ delay: 0.2 }}>
          <h3>Contributing Signals</h3>
          {[
            { label: "Stable income", impact: "+12", color: "var(--success)" },
            { label: "Strong repayment history", impact: "+15", color: "var(--success)" },
            { label: "Low debt burden", impact: "+8", color: "var(--success)" },
            { label: "Consistent behavior", impact: "+6", color: "var(--success)" },
            { label: "Verified documents", impact: "+7", color: "var(--success)" },
            { label: "Community vouches", impact: "+5", color: "var(--success)" },
          ].map((f, i) => (
            <motion.div key={f.label} className="lp-trust-factor"
              initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }} transition={{ delay: 0.1 * i }}>
              <span className="lp-trust-factor-label">+ {f.label}</span>
              <span className="lp-trust-factor-impact" style={{ color: f.color }}>{f.impact}</span>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function RiskIntelligence() {
  const items = [
    { num: "01", title: "REPAYMENT RISK", desc: "Estimate the likelihood of repayment difficulty using financial health, debt burden, and income stability signals." },
    { num: "02", title: "FRAUD INTELLIGENCE", desc: "Identify suspicious or inconsistent signals across identity, documents, transactions, and behavioral patterns." },
    { num: "03", title: "FINANCIAL HEALTH", desc: "Understand income, expenses, debt, and repayment capacity through 6-month financial analysis." },
  ];
  return (
    <section className="lp-section" id="risk-engine">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">SEE THE RISK.<br />UNDERSTAND THE RISK.</h2>
      </motion.div>
      <div className="lp-risk-grid">
        {items.map((item, i) => (
          <motion.div key={item.num} className="lp-risk-card" {...stagger} transition={{ delay: i * 0.15 }}>
            <div className="lp-risk-num">{item.num}</div>
            <h3 className="lp-risk-title">{item.title}</h3>
            <p className="lp-risk-desc">{item.desc}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function ExplainableAI() {
  const factors = [
    { label: "Strong repayment history", type: "+" },
    { label: "Stable income", type: "+" },
    { label: "Low debt burden", type: "+" },
    { label: "Recent credit inquiry", type: "−" },
  ];
  return (
    <section className="lp-section lp-section-dark" id="explainability">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">NOT A BLACK BOX.</h2>
        <p className="lp-section-sub">LendSure doesn't just output a prediction. It explains the evidence behind every decision.</p>
      </motion.div>
      <div className="lp-explain-layout">
        <motion.div className="lp-explain-card" {...fadeUp}>
          <div className="lp-explain-header">LENDING DECISION</div>
          <div className="lp-explain-decision">APPROVE</div>
          <div className="lp-explain-conf">HIGH CONFIDENCE</div>
          <div className="lp-explain-divider" />
          <div className="lp-explain-why">WHY?</div>
          {factors.map((f, i) => (
            <motion.div key={f.label} className="lp-explain-factor"
              initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }} transition={{ delay: 0.15 * i }}>
              <span className={`lp-explain-sign ${f.type === "+" ? "lp-explain-positive" : "lp-explain-negative"}`}>{f.type}</span>
              <span>{f.label}</span>
            </motion.div>
          ))}
        </motion.div>
        <motion.div className="lp-explain-flow" {...fadeUp} transition={{ delay: 0.3 }}>
          <div className="lp-flow-step">FACTORS</div>
          <div className="lp-flow-arrow">↓</div>
          <div className="lp-flow-step">WEIGHTS</div>
          <div className="lp-flow-arrow">↓</div>
          <div className="lp-flow-step">RISK</div>
          <div className="lp-flow-arrow">↓</div>
          <div className="lp-flow-step lp-flow-final">DECISION</div>
        </motion.div>
      </div>
    </section>
  );
}

function LoanTerms() {
  const [amount, setAmount] = useState(35000);
  const rate = 10;
  const months = 3;
  const emi = Math.round((amount * (1 + rate / 100 * months / 12)) / months);
  const total = emi * months;
  return (
    <section className="lp-section">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">DON'T JUST DECIDE.<br />OPTIMIZE THE TERMS.</h2>
      </motion.div>
      <motion.div className="lp-loan-card" {...fadeUp}>
        <div className="lp-loan-grid">
          <div>
            <div className="lp-loan-label">Recommended Loan</div>
            <div className="lp-loan-value">₹{amount.toLocaleString("en-IN")}</div>
          </div>
          <div>
            <div className="lp-loan-label">Interest Rate</div>
            <div className="lp-loan-value">{rate}%</div>
          </div>
          <div>
            <div className="lp-loan-label">Duration</div>
            <div className="lp-loan-value">{months} months</div>
          </div>
          <div>
            <div className="lp-loan-label">Monthly Payment</div>
            <div className="lp-loan-value">₹{emi.toLocaleString("en-IN")}</div>
          </div>
          <div>
            <div className="lp-loan-label">Total Repayment</div>
            <div className="lp-loan-value">₹{total.toLocaleString("en-IN")}</div>
          </div>
          <div>
            <div className="lp-loan-label">Risk</div>
            <div className="lp-loan-value lp-loan-risk">LOW</div>
          </div>
        </div>
        <div className="lp-loan-slider">
          <div className="lp-loan-slider-label">Loan Amount</div>
          <input type="range" min={10000} max={200000} step={5000} value={amount}
            onChange={(e) => setAmount(Number(e.target.value))} className="lp-slider" />
          <div className="lp-loan-slider-range">
            <span>₹10K</span><span>₹2,00,000</span>
          </div>
        </div>
        <div className="lp-demo-label">DEMO — Illustrative calculation</div>
      </motion.div>
    </section>
  );
}

function WhatIf() {
  const scenarios = [
    { label: "Scenario A", amount: "₹35,000", risk: "LOW", color: "var(--success)" },
    { label: "Scenario B", amount: "₹60,000", risk: "MEDIUM", color: "var(--warning)" },
    { label: "Scenario C", amount: "₹80,000", risk: "HIGH", color: "var(--danger)" },
  ];
  return (
    <section className="lp-section lp-section-dark">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">WHAT IF?</h2>
        <p className="lp-section-sub">See how different scenarios affect risk. LendSure is decision intelligence, not a simple yes/no system.</p>
      </motion.div>
      <div className="lp-scenarios">
        {scenarios.map((s, i) => (
          <motion.div key={s.label} className="lp-scenario-card" {...stagger} transition={{ delay: i * 0.15 }}>
            <div className="lp-scenario-label">{s.label}</div>
            <div className="lp-scenario-amount">{s.amount}</div>
            <div className="lp-scenario-term">3 months · 10%</div>
            <div className="lp-scenario-risk" style={{ color: s.color }}>Risk: {s.risk}</div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function AuditTrail() {
  const steps = [
    "Application Received", "Identity Evaluated", "Financial Signals Analyzed",
    "Fraud Signals Checked", "Risk Calculated", "Recommendation Generated", "Decision Recorded",
  ];
  return (
    <section className="lp-section">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">EVERY DECISION<br />LEAVES A TRAIL.</h2>
      </motion.div>
      <div className="lp-audit-timeline">
        {steps.map((step, i) => (
          <motion.div key={step} className="lp-audit-step"
            initial={{ opacity: 0, x: -30 }} whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }} transition={{ delay: 0.1 * i }}>
            <div className="lp-audit-dot" />
            <div className="lp-audit-content">
              <div className="lp-audit-label">{step}</div>
              <div className="lp-audit-time">Step {i + 1} of {steps.length}</div>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function DashboardPreview() {
  const { session } = useAuth();
  const app = session ? "/dashboard" : "/auth";
  const [metrics, setMetrics] = useState(null);
  useEffect(() => {
    let live = true;
    Promise.all([
      api("/ls/dashboard/metrics").catch(() => null),
      api("/ls/ml/credit/public").catch(() => null),
    ]).then(([d, m]) => {
      if (!live || !d || !m) return;
      setMetrics([
        `${d.borrowers.toLocaleString()} Borrowers`,
        `${d.avg_trust} Avg Trust`,
        `PR-AUC ${m.pr_auc.toFixed(2)}`,
        `${m.n_features} Live Features`,
      ]);
    });
    return () => { live = false; };
  }, []);
  return (
    <section className="lp-section lp-section-dark">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">SEE IT IN ACTION.</h2>
        <p className="lp-section-sub">The full LendSure intelligence dashboard — real data, real decisions, real audit trails.</p>
      </motion.div>
      <motion.div className="lp-dashboard-frame" {...fadeUp}>
        <div className="lp-browser-bar">
          <span className="lp-browser-dot" style={{ background: "#ef4444" }} />
          <span className="lp-browser-dot" style={{ background: "#f59e0b" }} />
          <span className="lp-browser-dot" style={{ background: "#22c55e" }} />
          <span className="lp-browser-url">app.lendsure.ai/dashboard</span>
        </div>
        <div className="lp-dashboard-placeholder">
          <div className="lp-dash-metrics">
            {(metrics || ["Live Borrowers", "Live Trust Scores", "Live PR-AUC", "Live Features"]).map((m) => (
              <div key={m} className="lp-dash-metric">{m}</div>
            ))}
          </div>
          <div className="lp-dash-chart">
            <div className="lp-dash-bar" style={{ height: "80%" }} />
            <div className="lp-dash-bar" style={{ height: "60%" }} />
            <div className="lp-dash-bar" style={{ height: "40%" }} />
            <div className="lp-dash-bar" style={{ height: "90%" }} />
            <div className="lp-dash-bar" style={{ height: "55%" }} />
            <div className="lp-dash-bar" style={{ height: "70%" }} />
            <div className="lp-dash-bar" style={{ height: "45%" }} />
          </div>
        </div>
      </motion.div>
      <motion.div className="lp-dashboard-cta" {...fadeUp}>
        <Link to={app} className="lp-btn-primary lp-btn-lg">Explore the Dashboard →</Link>
      </motion.div>
    </section>
  );
}

function SecuritySection() {
  const items = ["Explainable", "Auditable", "Evidence-driven", "Human-in-the-loop"];
  return (
    <section className="lp-section" id="security">
      <motion.div {...fadeUp}>
        <h2 className="lp-section-title">BUILT FOR DECISIONS<br />THAT MATTER.</h2>
      </motion.div>
      <div className="lp-security-grid">
        {items.map((item, i) => (
          <motion.div key={item} className="lp-security-item" {...stagger} transition={{ delay: i * 0.1 }}>
            <div className="lp-security-icon">✓</div>
            <div className="lp-security-label">{item}</div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function FinalCTA() {
  const { session } = useAuth();
  const app = session ? "/dashboard" : "/auth";
  return (
    <section className="lp-section lp-final-cta">
      <motion.div className="lp-final-content" {...fadeUp}>
        <div className="lp-final-3d">
          <SafeApprovalWave className="lp-final-scene" />
        </div>
        <h2 className="lp-section-title">LEND WITH<br />CONFIDENCE.</h2>
        <p className="lp-section-sub">Turn borrower information into clear, explainable lending intelligence.</p>
        <div className="lp-hero-ctas">
          <Link to={app} className="lp-btn-primary lp-btn-lg">{session ? "Open Dashboard →" : "Analyze a Borrower →"}</Link>
          <Link to={app} className="lp-btn-outline lp-btn-lg">Explore LendSure →</Link>
        </div>
      </motion.div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="lp-footer">
      <div className="lp-footer-inner">
        <div className="lp-footer-brand">
          <Link to="/" title="Back to top" style={{ display: "inline-flex" }}><Logo size={30} /></Link>
          <div>
            <div className="lp-footer-name">LendSure</div>
            <div className="lp-footer-tag">AI-Powered Trust & Risk Intelligence</div>
          </div>
        </div>
        <div className="lp-footer-links">
          <div className="lp-footer-col">
            <div className="lp-footer-col-title">Product</div>
            <a href="#product">How It Works</a>
            <a href="#risk-engine">Risk Engine</a>
            <a href="#explainability">Explainability</a>
          </div>
          <div className="lp-footer-col">
            <div className="lp-footer-col-title">Resources</div>
            <a href="#product">Documentation</a>
            <a href="#security">Security</a>
            <Link to="/grievance" style={{ color: "inherit" }}>File a complaint</Link>
            <a href="#product">Contact</a>
          </div>
          <div className="lp-footer-col">
            <div className="lp-footer-col-title">Legal</div>
            <a href="#product">Privacy</a>
            <a href="#product">Terms</a>
          </div>
        </div>
      </div>
      <div className="lp-footer-bottom">
        <p>Financial intelligence provided by LendSure is for informational and decision-support purposes only and should not be treated as financial, investment, legal, or lending advice.</p>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="lp-root">
      <Navbar />
      <Hero />
      <DataToDecision />
      <TrustScoreSection />
      <RiskIntelligence />
      <ExplainableAI />
      <LoanTerms />
      <WhatIf />
      <AuditTrail />
      <DashboardPreview />
      <SecuritySection />
      <FinalCTA />
      <Footer />
    </div>
  );
}
