import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import Logo from "../components/ui/Logo";
import "./Auth.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Auth() {
  const { session, loading: authLoading, signIn } = useAuth();
  const navigate = useNavigate();
  // Already signed in? Skip the form.
  useEffect(() => {
    if (!authLoading && session) navigate("/dashboard", { replace: true });
  }, [authLoading, session, navigate]);

  // "Sign in required" (bounced from a protected route) + idle-timeout notices.
  const [requiredPath, setRequiredPath] = useState("");
  const [idleNotice, setIdleNotice] = useState(false);
  useEffect(() => {
    try {
      const p = sessionStorage.getItem("ls_login_required");
      if (p && p !== "/auth" && p !== "/") {
        setRequiredPath(p);
        sessionStorage.removeItem("ls_login_required");
      }
      if (sessionStorage.getItem("ls_expired")) {
        setIdleNotice(true);
        sessionStorage.removeItem("ls_expired");
      }
    } catch {}
  }, []);

  const [mode, setMode] = useState("signin"); // signin | signup | guest
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [guestName, setGuestName] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  const switchMode = (m) => {
    setMode(m); setError("");
  };

  // ---- Sign in: Gmail + password, straight in, stays signed in ----
  const handleSignIn = async () => {
    if (!EMAIL_RE.test(email.trim())) { setError("Enter a valid email address"); return; }
    if (!password) { setError("Enter your password"); return; }
    setError(""); setLoading(true);
    try {
      await signIn("email-login", { email: email.trim(), password });
      navigate("/dashboard");
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  // ---- Sign up: saves Gmail + password, then moves to Sign in ----
  const handleSignUp = async () => {
    if (!name.trim()) { setError("Tell us your name"); return; }
    if (!EMAIL_RE.test(email.trim())) { setError("Enter a valid email address"); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
      setError("Password needs at least one letter and one number"); return;
    }
    setError(""); setInfo(""); setLoading(true);
    try {
      await signIn("register", { name: name.trim(), email: email.trim(), password });
      // Account saved — switch to Sign in and check the password there.
      setMode("signin");
      setPassword("");
      setInfo("Account created. Sign in with your email and password.");
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  // ---- Guest ----
  const handleGuest = async () => {
    setError(""); setLoading(true);
    try {
      await signIn("guest", { name: guestName || "Guest" });
      navigate("/dashboard");
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  return (
    <div className="zev-auth">
      {/* ---------- Brand panel ---------- */}
      <aside className="zev-brand">
        <div className="zev-brand-top">
          <Link to="/" className="zev-brand-link" title="Back to home page">
            <span className="zev-brand-mark"><Logo size={26} /></span>
            <span className="zev-brand-name">LendSure</span>
          </Link>
          <span className="zev-brand-tag">Decision-support for lenders</span>
        </div>

        <h1 className="zev-headline">
          Small steps.<br />Visible <span className="zev-headline-accent">evidence.</span>
        </h1>
        <p className="zev-sub">
          Every lending decision explained, audited and backed by live borrower data.
        </p>

        <div className="zev-cards">
          <div className="zev-card zev-card-lime">
            <div className="zev-card-logo">Ls <span>zev-style</span></div>
            <div className="zev-card-title">Small steps.<br />Visible progress.</div>
            <div className="zev-progress">
              <div className="zev-progress-track">
                <div className="zev-progress-fill" style={{ width: "76%" }} />
                <div className="zev-progress-knob" style={{ left: "76%" }} />
              </div>
              <span className="zev-progress-pct">76%</span>
            </div>
            <div className="zev-card-foot">Trust-weighted recommendations</div>
          </div>

          <div className="zev-card zev-card-pale">
            <div className="zev-card-logo">Ls <span>lendsure</span></div>
            <div className="zev-card-title">Your money.<br />In perspective.</div>
            <div className="zev-circles" aria-hidden="true">
              <span className="zev-circle zev-c1" />
              <span className="zev-circle zev-c2" />
              <span className="zev-circle zev-c3" />
            </div>
            <div className="zev-card-foot">Understand today. Plan the next move.</div>
          </div>

          <div className="zev-card zev-card-dark">
            <div className="zev-card-logo">Ls <span>lendsure</span></div>
            <div className="zev-card-title">A clearer view.<br />A better next move.</div>
            <div className="zev-dots" aria-hidden="true" />
            <div className="zev-card-foot">Risk, fraud &amp; recovery intel</div>
          </div>
        </div>

        <div className="zev-chips">
          <span>Explainable</span><span>Auditable</span><span>Evidence-backed</span>
        </div>
      </aside>

      {/* ---------- Form panel ---------- */}
      <main className="zev-form-side">
        <div className="zev-form-card">
          <Link to="/" className="zev-form-logo zev-brand-link" title="Back to home page">
            <Logo size={34} /> LendSure
          </Link>
          <h2 className="zev-form-title">Welcome to your workspace</h2>
          <p className="zev-form-sub">Sign in, create an account, or explore as a guest.</p>

          {requiredPath && (
            <div className="zev-notice">
              Sign in required to view <b>{requiredPath}</b> — pick any option below.
            </div>
          )}
          {idleNotice && (
            <div className="zev-notice">Signed out after 5 minutes of inactivity. Please sign in again.</div>
          )}

          <div className="zev-tabs" role="tablist">
            {["signin", "signup", "guest"].map((m) => (
              <button key={m} role="tab" aria-selected={mode === m}
                className={`zev-tab ${mode === m ? "zev-tab-active" : ""}`}
                onClick={() => switchMode(m)}>
                {m === "signin" ? "Sign in" : m === "signup" ? "Sign up" : "Guest"}
              </button>
            ))}
          </div>

          {mode === "signin" && (
            <div className="zev-form fade-in">
              <label className="zev-label">Email</label>
              <input type="email" placeholder="you@gmail.com" value={email}
                onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignIn()}
                className={`zev-input ${error ? "zev-input-error" : ""}`} autoComplete="email" />
              <label className="zev-label">Password</label>
              <input type="password" placeholder="••••••••" value={password}
                onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignIn()}
                className={`zev-input ${error ? "zev-input-error" : ""}`} autoComplete="current-password" />
              {error && <div className="zev-error">{error}</div>}
              {info && <div className="zev-info">{info}</div>}
              <Button variant="primary" className="zev-btn" onClick={handleSignIn} disabled={loading}>
                {loading ? "Signing in… (up to ~60s on cold start)" : "Sign in →"}
              </Button>
              <p className="zev-hint">Stays signed in on this device — sign up once, use it forever.</p>
            </div>
          )}

          {mode === "signup" && (
            <div className="zev-form fade-in">
              <label className="zev-label">Full name</label>
              <input type="text" placeholder="e.g. Priya Sharma" value={name}
                onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignUp()}
                className="zev-input" autoComplete="name" />
              <label className="zev-label">Email</label>
              <input type="email" placeholder="you@gmail.com" value={email}
                onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignUp()}
                className={`zev-input ${error ? "zev-input-error" : ""}`} autoComplete="email" />
              <label className="zev-label">Password</label>
              <input type="password" placeholder="Min 8 characters, letter + number" value={password}
                onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignUp()}
                className={`zev-input ${error ? "zev-input-error" : ""}`} autoComplete="new-password" />
              {error && <div className="zev-error">{error}</div>}
                  <Button variant="primary" className="zev-btn" onClick={handleSignUp} disabled={loading}>
                    {loading ? "Creating… (up to ~60s on cold start)" : "Create account →"}
                  </Button>
              <p className="zev-hint">Account is ready instantly — no codes, no waiting. Same email + password signs you in forever.</p>
            </div>
          )}

          {mode === "guest" && (
            <div className="zev-form fade-in">
              <label className="zev-label">Display name</label>
              <input type="text" placeholder="Guest Explorer" value={guestName}
                onChange={(e) => setGuestName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleGuest()}
                className="zev-input" />
              {error && <div className="zev-error">{error}</div>}
              <Button variant="secondary" className="zev-btn" onClick={handleGuest} disabled={loading}>
                {loading ? "Entering…" : "Continue as Guest →"}
              </Button>
              <p className="zev-hint">Read-only for 24 hours · labelled in the audit trail · no password needed.</p>
            </div>
          )}

          <p className="zev-foot">
            Have a complaint? <Link to="/grievance" className="link-btn">File it here</Link>
            {" · "}<Link to="/grievance/track" className="link-btn">Track a ticket</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
