import { useState, useRef, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { auth as authApi } from "../lib/api";
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
  const [step, setStep] = useState("form"); // form | otp
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [guestName, setGuestName] = useState("");
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [demoOtp, setDemoOtp] = useState(null);
  const [pendingEmail, setPendingEmail] = useState("");
  const [otpPurpose, setOtpPurpose] = useState("verify"); // verify (signup) | login (new device)
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [timer, setTimer] = useState(0);
  const otpRefs = useRef([]);

  useEffect(() => {
    if (timer <= 0) return;
    const t = setTimeout(() => setTimer(timer - 1), 1000);
    return () => clearTimeout(t);
  }, [timer]);

  const switchMode = (m) => {
    setMode(m); setStep("form"); setError(""); setInfo("");
    setOtp(["", "", "", "", "", ""]); setDemoOtp(null);
  };

  const startOtpStep = (mail, purpose, demo) => {
    setPendingEmail(mail);
    setOtpPurpose(purpose);
    setOtp(["", "", "", "", "", ""]);
    setDemoOtp(demo || null);
    setStep("otp");
    setTimer(60);
    setTimeout(() => otpRefs.current[0]?.focus(), 100);
  };

  // ---- Sign in (email + password; OTP only on a new device) ----
  const handleSignIn = async () => {
    if (!EMAIL_RE.test(email.trim())) { setError("Enter a valid email address"); return; }
    if (!password) { setError("Enter your password"); return; }
    setError(""); setInfo(""); setLoading(true);
    try {
      const r = await signIn("email-login", { email: email.trim(), password });
      if (r && r.otp_required) {
        startOtpStep(r.email || email.trim(), "login", r.demo_otp);
        setInfo("New device — enter the verification code sent to your email.");
      } else {
        navigate("/dashboard");
      }
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  // ---- Sign up (email + password, then OTP to verify) ----
  const handleSignUp = async () => {
    if (!name.trim()) { setError("Tell us your name"); return; }
    if (!EMAIL_RE.test(email.trim())) { setError("Enter a valid email address"); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
      setError("Password needs at least one letter and one number"); return;
    }
    setError(""); setInfo(""); setLoading(true);
    try {
      const r = await signIn("register", { name: name.trim(), email: email.trim(), password });
      startOtpStep(r.email || email.trim(), "verify", r.demo_otp);
      if (!r.demo_otp) setInfo("If the account is eligible, check your inbox for the code.");
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  const handleVerifyOtp = async () => {
    const code = otp.join("");
    if (code.length < 4) { setError("Enter the verification code"); return; }
    setError(""); setLoading(true);
    try {
      if (otpPurpose === "verify") await signIn("verify-email", { email: pendingEmail, otp: code });
      else await signIn("verify-login", { email: pendingEmail, otp: code });
      navigate("/dashboard");
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  const handleResend = async () => {
    setError(""); setLoading(true);
    try {
      const r = await authApi.resendCode(pendingEmail);
      if (r.demo_otp) setDemoOtp(r.demo_otp);
      setInfo("A fresh code was sent.");
      setTimer(60);
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  // Unverified account tried to sign in? Jump straight to verification.
  const handleVerifyInstead = async () => {
    setError(""); setInfo(""); setLoading(true);
    try {
      const r = await authApi.resendCode(email.trim());
      startOtpStep(email.trim(), "verify", r.demo_otp);
      setMode("signup");
      setInfo("Verify your email to activate the account, then sign in.");
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

  const handleOtpInput = (i, val) => {
    const d = val.replace(/\D/g, "").slice(0, 1);
    const next = [...otp]; next[i] = d; setOtp(next);
    if (d && i < 5) otpRefs.current[i + 1]?.focus();
  };

  const handleOtpKey = (i, e) => {
    if (e.key === "Backspace" && !otp[i] && i > 0) otpRefs.current[i - 1]?.focus();
    if (e.key === "Enter") handleVerifyOtp();
  };

  const showVerifyShortcut = /not verified/i.test(error || "");

  return (
    <div className="zev-auth">
      {/* ---------- Brand panel ---------- */}
      <aside className="zev-brand">
        <div className="zev-brand-top">
          <span className="zev-brand-mark"><Logo size={26} /></span>
          <span className="zev-brand-name">LendSure</span>
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
          <div className="zev-form-logo"><Logo size={34} /> LendSure</div>
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

          {step === "form" && (
            <>
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
                  {showVerifyShortcut && (
                    <button className="link-btn" onClick={handleVerifyInstead}>
                      Account not verified yet? Verify it now →
                    </button>
                  )}
                  <Button variant="primary" className="zev-btn" onClick={handleSignIn} disabled={loading}>
                    {loading ? "Signing in…" : "Sign in →"}
                  </Button>
                  <p className="zev-hint">Stays signed in on this device — sign up once, use it forever.</p>
                </div>
              )}

              {mode === "signup" && (
                <div className="zev-form fade-in">
                  <label className="zev-label">Full name</label>
                  <input type="text" placeholder="e.g. Priya Sharma" value={name}
                    onChange={(e) => setName(e.target.value)} className="zev-input" autoComplete="name" />
                  <label className="zev-label">Email</label>
                  <input type="email" placeholder="you@gmail.com" value={email}
                    onChange={(e) => setEmail(e.target.value)} className={`zev-input ${error ? "zev-input-error" : ""}`} autoComplete="email" />
                  <label className="zev-label">Password</label>
                  <input type="password" placeholder="Min 8 characters, letter + number" value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={`zev-input ${error ? "zev-input-error" : ""}`} autoComplete="new-password" />
                  {error && <div className="zev-error">{error}</div>}
                  {info && <div className="zev-info">{info}</div>}
                  <Button variant="primary" className="zev-btn" onClick={handleSignUp} disabled={loading}>
                    {loading ? "Creating…" : "Create account →"}
                  </Button>
                  <p className="zev-hint">Next: we’ll open a verification-code step to activate your account.</p>
                </div>
              )}

              {mode === "guest" && (
                <div className="zev-form fade-in">
                  <label className="zev-label">Display name</label>
                  <input type="text" placeholder="Guest Explorer" value={guestName}
                    onChange={(e) => setGuestName(e.target.value)} className="zev-input" />
                  {error && <div className="zev-error">{error}</div>}
                  <Button variant="secondary" className="zev-btn" onClick={handleGuest} disabled={loading}>
                    {loading ? "Entering…" : "Continue as Guest →"}
                  </Button>
                  <p className="zev-hint">Read-only for 24 hours · labelled in the audit trail · no password needed.</p>
                </div>
              )}
            </>
          )}

          {step === "otp" && (
            <div className="zev-form fade-in">
              <p className="zev-otp-label">
                {otpPurpose === "verify" ? "Verify" : "Confirm it’s you"} — code sent to <b>{pendingEmail}</b>
              </p>
              <div className="zev-otp-boxes">
                {otp.map((v, i) => (
                  <input key={i} ref={(el) => (otpRefs.current[i] = el)} maxLength={1} value={v}
                    inputMode="numeric" onChange={(e) => handleOtpInput(i, e.target.value)}
                    onKeyDown={(e) => handleOtpKey(i, e)}
                    className={`zev-otp ${v ? "zev-otp-filled" : ""}`} aria-label={`Digit ${i + 1}`} />
                ))}
              </div>
              {error && <div className="zev-error">{error}</div>}
              {info && <div className="zev-info">{info}</div>}
              {demoOtp && <div className="zev-demo-otp">Demo code · <b>{demoOtp}</b></div>}
              <Button variant="primary" className="zev-btn" onClick={handleVerifyOtp} disabled={loading}>
                {loading ? "Verifying…" : otpPurpose === "verify" ? "Verify & create account" : "Verify & sign in"}
              </Button>
              <div className="zev-resend">
                {timer > 0
                  ? <span className="zev-timer">Resend in 0:{String(timer).padStart(2, "0")}</span>
                  : <button className="link-btn" onClick={handleResend}>Resend code</button>}
                <button className="link-btn" onClick={() => { setStep("form"); setError(""); }}>← Back</button>
              </div>
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
