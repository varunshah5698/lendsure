const BASE = "/api";
// Serverless + free-tier backends sleep when idle: the FIRST request wakes
// them (cold start, up to ~90s on Render Docker) and gets one automatic
// retry. Later requests use the normal budget. Retried at most once each —
// no infinite loops. Settles to a clear, safe message otherwise.
const FIRST_TIMEOUT_MS = 90000;
const REQUEST_TIMEOUT_MS = 45000;
let firstRequestDone = false;

// Authentication rides the HttpOnly session cookie (same-origin, sent
// automatically). NOTHING that can authenticate is ever kept in JS memory
// or storage — the `token` argument below is accepted for call-site
// compatibility and deliberately ignored.
function flagExpired() {
  try { sessionStorage.setItem("ls_expired", "1"); } catch {}
  try { window.dispatchEvent(new Event("lendsure:session-expired")); } catch {}
}

async function fetchOnce(path, opts, timeoutMs) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const cancel = () => ctrl.abort();
  opts.signal?.addEventListener("abort", cancel, { once: true });
  if (opts.signal?.aborted) ctrl.abort();
  try {
    return await fetch(`${BASE}${path}`, {
      ...opts,
      signal: ctrl.signal,
      headers: {
        "Content-Type": "application/json",
        ...(opts.headers || {}),
      },
    });
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", cancel);
  }
}

export async function api(path, opts = {}, token = null) {
  const { timeoutMs, privateIntelligence = false, ...fetchOpts } = opts || {};
  const first = !firstRequestDone;
  const firstBudget = timeoutMs || FIRST_TIMEOUT_MS;
  const normalBudget = timeoutMs || REQUEST_TIMEOUT_MS;
  let r;
  try {
    try {
      r = await fetchOnce(path, fetchOpts, first ? firstBudget : normalBudget);
    } catch (e) {
      // One automatic retry for the waking-server case only.
      if (first && !privateIntelligence && !fetchOpts.signal?.aborted && (e?.name === "AbortError" || e instanceof TypeError)) {
        r = await fetchOnce(path, fetchOpts, firstBudget);
      } else {
        throw e;
      }
    } finally {
      firstRequestDone = true;
    }
  } catch (e) {
    if (fetchOpts.signal?.aborted) throw e;
    if (e?.name === "AbortError") {
      throw new Error(
        "Server is waking up (cold start). Wait 30 seconds and try again."
      );
    }
    throw new Error(
      "Cannot reach the LendSure server. Start it first by running " +
      "`./start.sh` in the project folder (or: python3 -m uvicorn app:app --host 127.0.0.1 --port 8000 in backend/)."
    );
  }
  if (r.status === 401) {
    flagExpired();
    throw new Error("SESSION_EXPIRED");
  }
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const body = await r.json();
      msg = body.detail || msg;
    } catch {}
    if (privateIntelligence) {
      const message = r.status === 503 ? "Provider unavailable. Authorized production integration is not connected." : r.status >= 500 ? "Intelligence request failed. Please retry." : typeof msg === "string" ? msg : "Invalid intelligence request; check the fields and limits.";
      throw Object.assign(new Error(message), { status: r.status });
    }
    if (r.status >= 500) {
      // Never show stack traces / SQL / paths to users — log for devs only.
      try { console.error(`[api] ${r.status} ${path}:`, msg); } catch {}
      // 502/503/504 almost always means a sleeping/free-tier backend or a
      // brief deploy restart — say that instead of a dead-end error.
      if (r.status === 502 || r.status === 503 || r.status === 504) {
        throw new Error("Server is waking up or restarting. Wait 30 seconds and try again.");
      }
      throw new Error("Something went wrong. Please try again.");
    }
    throw new Error(msg);
  }
  return r.json();
}

// Auth (generous timeouts: Render free-tier cold starts + SMTP delivery
// can take 30-60s on the first request after idle — never fail those fast)
const AUTH_TIMEOUT_MS = 120000;
export const auth = {
  requestOtp: (phone, name) =>
    api("/auth/request-otp", { method: "POST", body: JSON.stringify({ phone, name }), timeoutMs: AUTH_TIMEOUT_MS }),
  verifyOtp: (phone, otp, name) =>
    api("/auth/verify-otp", { method: "POST", body: JSON.stringify({ phone, otp, name }), timeoutMs: AUTH_TIMEOUT_MS }),
  guest: (name) =>
    api("/auth/guest", { method: "POST", body: JSON.stringify({ name }), timeoutMs: AUTH_TIMEOUT_MS }),
  register: (name, email, password) =>
    api("/auth/register", { method: "POST", body: JSON.stringify({ name, email, password }), timeoutMs: AUTH_TIMEOUT_MS }),
  verifyEmail: (email, otp) =>
    api("/auth/verify-email", { method: "POST", body: JSON.stringify({ email, otp }), timeoutMs: AUTH_TIMEOUT_MS }),
  resendCode: (email) =>
    api("/auth/resend-code", { method: "POST", body: JSON.stringify({ email }), timeoutMs: AUTH_TIMEOUT_MS }),
  otpConfig: () =>
    api("/auth/otp-config"),
  emailLogin: (email, password) =>
    api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }), timeoutMs: AUTH_TIMEOUT_MS }),
  verifyLogin: (email, otp) =>
    api("/auth/verify-login", { method: "POST", body: JSON.stringify({ email, otp }), timeoutMs: AUTH_TIMEOUT_MS }),
  forgotPassword: (email) =>
    api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }), timeoutMs: AUTH_TIMEOUT_MS }),
  resetPassword: (email, otp, new_password) =>
    api("/auth/reset-password", { method: "POST", body: JSON.stringify({ email, otp, new_password }), timeoutMs: AUTH_TIMEOUT_MS }),
  me: (token) => api("/auth/me", {}, token),
  logout: (token) => api("/auth/logout", { method: "POST" }, token),
  sessions: (token) => api("/auth/sessions", {}, token),
  revokeAllSessions: (token) => api("/auth/sessions/revoke-all", { method: "POST" }, token),
};

// Dashboard
export const dashboard = {
  metrics: (token) => api("/ls/dashboard/metrics", {}, token),
  trends: (token) => api("/ls/dashboard/trends", {}, token),
};

// Borrowers
export const borrowers = {
  list: (params = {}, token) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v && v !== "all") q.set(k, v); });
    const qs = q.toString();
    return api(`/ls/borrowers${qs ? `?${qs}` : ""}`, {}, token);
  },
  get: (id, token) => api(`/ls/borrowers/${id}`, {}, token),
  financials: (id, token) => api(`/ls/borrowers/${id}/financials`, {}, token),
  analyze: (id, token) => api(`/ls/borrowers/${id}/analyze`, { method: "POST" }, token),
  analysis: (id, token) => api(`/ls/borrowers/${id}/analysis`, {}, token),
  cashflow: (id, token) => api(`/ls/borrowers/${id}/cashflow`, {}, token),
  evidence: (id, token) => api(`/ls/borrowers/${id}/evidence`, {}, token),
  audit: (id, token) => api(`/ls/borrowers/${id}/audit`, {}, token),
};

// Documents
export const documents = {
  list: (bid, token) => api(`/ls/borrowers/${bid}/documents`, {}, token),
  create: (bid, data, token) =>
    api(`/ls/borrowers/${bid}/documents`, { method: "POST", body: JSON.stringify(data) }, token),
  patch: (docId, data, token) =>
    api(`/ls/documents/${docId}`, { method: "PATCH", body: JSON.stringify(data) }, token),
};

// Simulation
export const simulation = {
  run: (data, token) =>
    api("/ls/recommendations/simulate", { method: "POST", body: JSON.stringify(data) }, token),
};

// Admin
export const admin = {
  stats: (token) => api("/ls/admin/stats", {}, token),
  config: (token) => api("/ls/admin/config", {}, token),
  updateConfig: (key, value, token) =>
    api("/ls/admin/config", { method: "PUT", body: JSON.stringify({ key, value }) }, token),
  model: (token) => api("/ls/admin/model", {}, token),
  audit: (limit, token) => api(`/ls/admin/audit?limit=${limit || 50}`, {}, token),
  keys: (token) => api("/ls/admin/keys", {}, token),
  createKey: (name, token, opts = {}) =>
    api("/ls/admin/keys", { method: "POST", body: JSON.stringify({ name, scopes: opts.scopes || "read", expires_days: opts.expires_days || 90 }) }, token),
  revokeKey: (id, token) =>
    api(`/ls/admin/keys/${id}/revoke`, { method: "POST" }, token),
  overview: (token) => api("/ls/admin/overview", {}, token),
  approvals: (params = {}, token) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") q.set(k, v); });
    const qs = q.toString();
    return api(`/ls/admin/approvals${qs ? `?${qs}` : ""}`, {}, token);
  },
  reviewApproval: (id, data, token) =>
    api(`/ls/admin/approvals/${id}/review`, { method: "POST", body: JSON.stringify(data) }, token),
  sessions: (token) => api("/ls/admin/sessions", {}, token),
  revokeSession: (sessionToken, token) =>
    api(`/ls/admin/sessions/${sessionToken}`, { method: "DELETE" }, token),
};

// Financial Intelligence
export const finance = {
  overview: (token) => api("/finance/overview", {}, token),
  markets: (params = {}, token) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v && v !== "all") q.set(k, v); });
    const qs = q.toString();
    return api(`/finance/markets${qs ? `?${qs}` : ""}`, {}, token);
  },
  marketDetail: (symbol, range_ = "3M", token) =>
    api(`/finance/markets/${encodeURIComponent(symbol)}?range=${range_}`, {}, token),
  news: (params = {}, token) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v && v !== "all" && v !== "") q.set(k, v); });
    const qs = q.toString();
    return api(`/finance/news${qs ? `?${qs}` : ""}`, {}, token);
  },
  newsArticle: (id, token) => api(`/finance/news/${id}`, {}, token),
  economy: (token) => api("/finance/economy", {}, token),
  creditEnvironment: (token) => api("/finance/credit-environment", {}, token),
  watchlist: (token) => api("/finance/watchlist", {}, token),
  addToWatchlist: (symbol, token) =>
    api(`/finance/watchlist/add?symbol=${encodeURIComponent(symbol)}`, { method: "POST" }, token),
  removeFromWatchlist: (symbol, token) =>
    api(`/finance/watchlist/remove?symbol=${encodeURIComponent(symbol)}`, { method: "POST" }, token),
  alerts: (params = {}, token) => {
    const q = new URLSearchParams();
    if (params.unread_only) q.set("unread_only", "true");
    const qs = q.toString();
    return api(`/finance/alerts${qs ? `?${qs}` : ""}`, {}, token);
  },
  markAlertRead: (id, token) => api(`/finance/alerts/${id}/read`, { method: "POST" }, token),
  ticker: (token) => api("/finance/ticker", {}, token),
  briefing: (token) => api("/finance/briefing", {}, token),
  portfolioImpact: (token) => api("/finance/portfolio-impact", {}, token),
  sources: (token) => api("/finance/sources", {}, token),
  newsTicker: (token) => api("/finance/news/ticker", {}, token),
};

// Loan lifecycle
export const loans = {
  requests: (params = {}, token) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") q.set(k, v); });
    const qs = q.toString();
    return api(`/ls/loan-requests${qs ? `?${qs}` : ""}`, {}, token);
  },
  getRequest: (id, token) => api(`/ls/loan-requests/${id}`, {}, token),
  createRequest: (data, token) =>
    api("/ls/loan-requests", { method: "POST", body: JSON.stringify({ ...data, idempotency_key: data.idempotency_key || `req-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }) }, token),
  transition: (id, action, body = {}, token) =>
    api(`/ls/loan-requests/${id}/${action}`, { method: "POST", body: JSON.stringify(body) }, token),
  approve: (id, body = {}, token) =>
    api(`/ls/loan-requests/${id}/approve`, { method: "POST", body: JSON.stringify(body) }, token),
  list: (params = {}, token) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") q.set(k, v); });
    const qs = q.toString();
    return api(`/ls/loans${qs ? `?${qs}` : ""}`, {}, token);
  },
  get: (id, token) => api(`/ls/loans/${id}`, {}, token),
  repay: (id, body, token) =>
    api(`/ls/loans/${id}/repayments`, { method: "POST", body: JSON.stringify({ ...body, idempotency_key: body.idempotency_key || `pay-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }) }, token),
};

// Graph intelligence
export const graph = {
  neighborhood: (bid, hops = 2, token) => api(`/ls/borrowers/${bid}/graph?hops=${hops}`, {}, token),
  summary: (bid, token) => api(`/ls/borrowers/${bid}/network-summary`, {}, token),
  path: (from_borrower, to_borrower, token) =>
    api("/ls/graph/path", { method: "POST", body: JSON.stringify({ from_borrower, to_borrower }) }, token),
  clusters: (token) => api("/ls/graph/clusters", {}, token),
  stats: (token) => api("/ls/graph/stats", {}, token),
};

// Background jobs
export const jobs = {
  list: (params = {}, token) => {
    const q = new URLSearchParams(params).toString();
    return api(`/ls/admin/jobs${q ? `?${q}` : ""}`, {}, token);
  },
  retry: (id, token) => api(`/ls/admin/jobs/${id}/retry`, { method: "POST" }, token),
};

// Notifications + live stream
export const notify = {
  list: (token) => api("/ls/notifications", {}, token),
  unread: (token) => api("/ls/notifications/unread-count", {}, token),
  markRead: (id, token) => api(`/ls/notifications/${id}/read`, { method: "POST" }, token),
  ticket: (token) => api("/ls/events/ticket", { method: "POST" }, token),
};

// Credit-risk ML v4 (trained model — real predictions, never placeholders)
export const mlCredit = {
  predict: (borrower_id, token) =>
    api("/ls/ml/credit/predict", { method: "POST", body: JSON.stringify({ borrower_id }) }, token),
  predictBatch: (borrower_ids, token) =>
    api("/ls/ml/credit/predict-batch", { method: "POST", body: JSON.stringify({ borrower_ids }) }, token),
  model: (token) => api("/ls/ml/credit/model", {}, token),
};

// AI Recovery Intelligence (real LLM, tool-grounded — never mocked)
export const assistant = {
  status: (token) => api("/ls/assistant/status", {}, token),
  chat: (message, history, token) =>
    api("/ls/assistant/chat",
      { method: "POST", body: JSON.stringify({ message, history }), timeoutMs: 95000 }, token),
};

// Investigation cases
export const cases = {
  list: (params = {}, token) => {
    const q = new URLSearchParams(params).toString();
    return api(`/ls/cases${q ? `?${q}` : ""}`, {}, token);
  },
  get: (id, token) => api(`/ls/cases/${id}`, {}, token),
  create: (data, token) => api("/ls/cases", { method: "POST", body: JSON.stringify(data) }, token),
  resolve: (id, token) => api(`/ls/cases/${id}/resolve`, { method: "POST" }, token),
  assign: (id, officer_phone, token) =>
    api(`/ls/cases/${id}/assign`, { method: "POST", body: JSON.stringify({ officer_phone }) }, token),
  transferRequest: (id, data, token) =>
    api(`/ls/cases/${id}/transfer-request`, { method: "POST", body: JSON.stringify(data) }, token),
  transferReview: (id, data, token) =>
    api(`/ls/cases/${id}/transfer-review`, { method: "POST", body: JSON.stringify(data) }, token),
  transfers: (id, token) => api(`/ls/cases/${id}/transfers`, {}, token),
  transferQueue: (params = {}, token) => {
    const q = new URLSearchParams(params).toString();
    return api(`/ls/transfers${q ? `?${q}` : ""}`, {}, token);
  },
};

// Recovery officers + territories
export const officers = {
  list: (token) => api("/ls/officers", {}, token),
  create: (data, token) =>
    api("/ls/officers", { method: "POST", body: JSON.stringify(data) }, token),
  update: (id, data, token) =>
    api(`/ls/officers/${id}`, { method: "PATCH", body: JSON.stringify(data) }, token),
  me: (token) => api("/ls/officers/me", {}, token),
  territory: (token) => api("/ls/territory/summary", {}, token),
};

// Borrower grievance portal
export const grievances = {
  create: (data) =>
    api("/ls/grievances", { method: "POST", body: JSON.stringify(data) }),
  track: (ticket_id, phone) =>
    api(`/ls/grievances/track?ticket_id=${encodeURIComponent(ticket_id)}&phone=${encodeURIComponent(phone)}`),
  list: (params = {}, token) => {
    const q = new URLSearchParams(params).toString();
    return api(`/ls/grievances${q ? `?${q}` : ""}`, {}, token);
  },
  get: (id, token) => api(`/ls/grievances/${id}`, {}, token),
  note: (id, note, token) =>
    api(`/ls/grievances/${id}/notes`, { method: "POST", body: JSON.stringify({ note }) }, token),
  assign: (id, officer_phone, token) =>
    api(`/ls/grievances/${id}/assign`, { method: "POST", body: JSON.stringify({ officer_phone }) }, token),
  setStatus: (id, status, note, token) =>
    api(`/ls/grievances/${id}/status`, { method: "POST", body: JSON.stringify({ status, note: note || "" }) }, token),
};

// Intelligence: health, monitoring, history, warnings, portfolio
const intelligenceRequest = (bid, suffix, data, signal) => api(
  `/ls/borrowers/${encodeURIComponent(bid)}/intelligence${suffix}`,
  { privateIntelligence: true, cache: "no-store", signal,
    ...(data === undefined ? {} : { method: "POST", body: JSON.stringify(data) }) }
);

export const intelligence = {
  get: (bid, signal) => intelligenceRequest(bid, "", undefined, signal),
  consent: (bid, data, signal) => intelligenceRequest(bid, "/consents", data, signal),
  revoke: (bid, id, signal) => intelligenceRequest(bid, `/consents/${encodeURIComponent(id)}/revoke`, {}, signal),
  fetchCredit: (bid, consent_id, signal) => intelligenceRequest(bid, "/credit/fetch", { consent_id }, signal),
  demo: (bid, consent_id, signal) => intelligenceRequest(bid, "/cashflow/demo", { consent_id }, signal),
  records: (bid, data, signal) => intelligenceRequest(bid, "/cashflow/records", data, signal),
  statement: (bid, data, signal) => intelligenceRequest(bid, "/cashflow/statement", data, signal),
};

export const intel = {
  health: (part, token) => api(`/api/health/${part}`, {}, token),
  monitoring: (token) => api("/api/ls/admin/model/monitoring", {}, token),
  riskHistory: (bid, token) => api(`/ls/borrowers/${bid}/risk-history`, {}, token),
  warnings: (token) => api("/ls/intel/warnings", {}, token),
  portfolio: (token) => api("/ls/intel/portfolio", {}, token),
};

// Simulation center
export const sim = {
  scenarios: (token) => api("/ls/admin/simulate/scenarios", {}, token),
  run: (scenario, token) =>
    api("/ls/admin/simulate/scenario", { method: "POST", body: JSON.stringify({ scenario }) }, token),
  cleanup: (token) => api("/ls/admin/simulate/cleanup", { method: "POST" }, token),
};

// Utility
export const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
