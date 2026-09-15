import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { auth } from "../lib/api";

const AuthContext = createContext(null);
const PROFILE_KEY = "ls_profile";
// Legacy cleanup: sessions used to live in localStorage as bearer tokens.
// Anything that can authenticate must never sit in JS storage — drop it.
try { localStorage.removeItem("ls_session"); } catch {}

function toProfile(me) {
  if (!me) return null;
  return {
    display_name: me.display_name || "",
    phone: me.phone || "",
    email: me.email || "",
    role: me.role || "guest",
  };
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    auth.me()
      .then((me) => {
        if (!live) return;
        const p = toProfile(me);
        setSession(p);
        try {
          if (p) localStorage.setItem(PROFILE_KEY, JSON.stringify(p));
          else localStorage.removeItem(PROFILE_KEY);
        } catch {}
      })
      .catch(() => {
        if (!live) return;
        setSession(null);
        try { localStorage.removeItem(PROFILE_KEY); } catch {}
      })
      .finally(() => { if (live) setLoading(false); });
    const onExpired = () => {
      setSession(null);
      try { localStorage.removeItem(PROFILE_KEY); } catch {}
    };
    window.addEventListener("lendsure:session-expired", onExpired);
    return () => {
      live = false;
      window.removeEventListener("lendsure:session-expired", onExpired);
    };
  }, []);

  const saveProfile = useCallback((result) => {
    // Only real sessions carry display_name (register/forgot/OTP-request
    // answers don't) — never synthesize a session from those.
    const p = toProfile(result);
    if (p && p.display_name) {
      setSession(p);
      try { localStorage.setItem(PROFILE_KEY, JSON.stringify(p)); } catch {}
    }
    return result;
  }, []);

  const signIn = useCallback(async (method, data) => {
    let result;
    if (method === "otp") result = await auth.requestOtp(data.phone, data.name);
    else if (method === "verify") result = await auth.verifyOtp(data.phone, data.otp, data.name);
    else if (method === "guest") result = await auth.guest(data.name);
    else if (method === "register") result = await auth.register(data.name, data.email, data.password);
    else if (method === "verify-email") result = await auth.verifyEmail(data.email, data.otp);
    else if (method === "email-login") result = await auth.emailLogin(data.email, data.password);
    else if (method === "verify-login") result = await auth.verifyLogin(data.email, data.otp);
    else if (method === "forgot") result = await auth.forgotPassword(data.email);
    else if (method === "reset") result = await auth.resetPassword(data.email, data.otp, data.new_password);
    else throw new Error("Unknown auth method");
    // email-login on a new device answers {otp_required: true} with NO
    // session — the caller must complete verify-login first.
    if (result && result.otp_required) return result;
    if (result && result.ok) saveProfile(result);
    return result;
  }, [saveProfile]);

  const signOut = useCallback(async () => {
    try { await auth.logout(); } catch {}
    setSession(null);
    try { localStorage.removeItem(PROFILE_KEY); } catch {}
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be within AuthProvider");
  return ctx;
}

/** Guests are read-only: governance mutations need a lender (phone OTP) session. */
export const isGuest = (session) => !session || session.role === "guest";

export function guardLender(session, toast) {
  if (isGuest(session)) {
    toast?.error?.("Guests are read-only — sign in as a lender for these actions");
    return false;
  }
  return true;
}
