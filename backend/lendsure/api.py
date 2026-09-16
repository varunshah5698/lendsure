"""LendSure REST API — borrowers, analysis, evidence, documents, audit, admin."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .engines import RecommendationEngine, emi, full_analysis
from .notify import audit as _audit_log
from .schema import DEFAULT_CONFIG

router = APIRouter(prefix="/api/ls", tags=["lendsure"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def now() -> str:
    return datetime.utcnow().isoformat()


def cfg_all(conn) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    for r in conn.execute("SELECT key, value FROM ls_config"):
        try:
            cfg[r["key"]] = json.loads(r["value"])
        except Exception:
            pass
    return cfg


def verification_bucket(b: dict, docs: list[dict]) -> str:
    statuses = [d["status"] for d in docs]
    if "suspicious" in statuses or b["id_verification"] == 0:
        return "suspicious"
    if b["id_verification"] == 2 and b["address_verification"] == 2 and b["phone_verification"] == 2 \
            and docs and all(s == "verified" for s in statuses):
        return "verified"
    return "needs_review"


def merge_perf(conn, bid: str, b: dict) -> dict:
    """Fold recorded repayment performance into analysis input (shared by the
    analyze endpoint and the simulator so both apply the identical feedback)."""
    perf = conn.execute("SELECT * FROM ls_borrower_perf WHERE borrower_id=?", (bid,)).fetchone()
    perf = dict(perf) if perf else None
    if perf and (perf["repayments_missed"] or perf["repayments_on_time"] or perf["loans_completed"]):
        b = dict(b)
        b["late_payments"] = (b.get("late_payments") or 0) + (perf["repayments_missed"] or 0)
        b["loans_repaid"] = (b.get("loans_repaid") or 0) + (perf["loans_completed"] or 0)
        if perf["repayments_missed"]:
            b["ontime_streak_months"] = 0
            b["max_days_past_due"] = max(b.get("max_days_past_due") or 0, 30)
        else:
            b["ontime_streak_months"] = (b.get("ontime_streak_months") or 0) + (perf["repayments_on_time"] or 0)
        b["_perf_applied"] = {"missed": perf["repayments_missed"], "on_time": perf["repayments_on_time"],
                              "completed": perf["loans_completed"]}
    return b


def latest_analyses(conn) -> dict:
    out = {}
    for r in conn.execute(
            "SELECT a.* FROM ls_analyses a JOIN (SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x "
            "ON x.borrower_id=a.borrower_id AND x.m=a.id"):
        out[r["borrower_id"]] = dict(r)
    return out


def actor_of(authorization: Optional[str], x_api_key: Optional[str] = None) -> str:
    s = _RESOLVE(authorization) if authorization else None
    if s:
        return f"{s['display_name']} ({s['phone']})"
    if x_api_key:
        import hashlib
        h = hashlib.sha256(x_api_key.encode()).hexdigest()
        conn = _DB()
        try:
            row = conn.execute("SELECT * FROM ls_api_keys WHERE key_hash=? AND revoked=0", (h,)).fetchone()
            if row:
                conn.execute("UPDATE ls_api_keys SET last_used=? WHERE id=?", (now(), row["id"]))
                conn.commit()
                return f"{row['name']} [api-key {row['prefix']}]"
        finally:
            conn.close()
    return "anonymous"


# ---------------- authorization (centralized RBAC) ----------------
# Guests may explore, analyze and simulate (demo-safe). Governance mutations
# (policy, reviews, keys, sessions, document verification) require the lender
# or service (API-key) role. Every check below goes through require_perm —
# never inline `role == ...` comparisons in endpoints.
ROLE_PERMS = {
    # Guests are heavily restrained: read-only view of borrowers, their
    # analyses and market data. No runs, no loans, no governance, no assistant bots.
    "guest": {"borrower.read", "analysis.read", "finance.read", "graph.read"},
    "lender": {"borrower.read", "borrower.create", "analysis.read", "analysis.run",
               "simulation.run", "finance.read", "admin.read", "loan.read", "graph.read",
               "documents.write", "policy.update", "review.decide",
               "keys.manage", "sessions.revoke",
               "loan_request.create", "loan_request.decide", "repayment.record",
               "jobs.manage", "cases.manage", "officer.manage",
               "grievance.read", "grievance.manage"},
    "service": {"borrower.read", "borrower.create", "analysis.read", "analysis.run",
                "simulation.run", "finance.read", "admin.read", "loan.read", "graph.read",
                 "documents.write", "policy.update", "review.decide",
                "keys.manage", "sessions.revoke",
                "loan_request.create", "loan_request.decide", "repayment.record",
                "jobs.manage", "cases.manage", "officer.manage",
                "grievance.read", "grievance.manage"},
}


def role_of(authorization: Optional[str], x_api_key: Optional[str] = None) -> str:
    if x_api_key and _api_key_row(x_api_key) is not None:
        return "service"
    s = _RESOLVE(authorization) if authorization else None
    if s:
        return s.get("role") or "guest"
    return "guest"


def _api_key_row(x_api_key: str | None):
    """Valid, unrevoked, unexpired key row — else None. Expiry is enforced
    here so every caller (role_of, require_perm) honors it identically."""
    if not x_api_key:
        return None
    import hashlib
    from datetime import datetime
    h = hashlib.sha256(x_api_key.encode()).hexdigest()
    conn = _DB()
    try:
        row = conn.execute("SELECT * FROM ls_api_keys WHERE key_hash=? AND revoked=0", (h,)).fetchone()
        if not row:
            return None
        row = dict(row)
        if row.get("expires_at") and row["expires_at"] <= datetime.utcnow().isoformat():
            return None
        return row
    finally:
        conn.close()


_ALL_PERMS = {p for perms in ROLE_PERMS.values() for p in perms}
SCOPE_PERMS = {
    "read": {p for p in _ALL_PERMS if p.endswith(".read")},
    "write": {p for p in _ALL_PERMS if p.endswith(".read")}
             | {"borrower.create", "analysis.run", "simulation.run",
                "documents.write", "loan_request.create", "loan_request.decide",
                "repayment.record", "cases.manage", "review.decide", "grievance.manage"},
    "admin": _ALL_PERMS,
}
VALID_SCOPES = ("read", "write", "admin")


def require_perm(authorization: Optional[str], x_api_key: Optional[str], *perms: str) -> str:
    key = _api_key_row(x_api_key)
    if key is not None:
        allowed: set = set()
        for s in (key.get("scopes") or "read").split(","):
            allowed |= SCOPE_PERMS.get(s.strip(), set())
        if not all(p in allowed for p in perms):
            raise HTTPException(403, f"API key scopes ({key.get('scopes') or 'read'}) do not cover: {', '.join(perms)}")
        return "service"
    role = role_of(authorization, x_api_key)
    if not any(p in ROLE_PERMS.get(role, set()) for p in perms):
        # A presented credential that resolves to nothing = dead session
        # (expired, idle-timed-out, revoked): 401 so clients re-authenticate.
        # No credential at all, or a valid session lacking the perm: 403.
        # (The middleware injects cookie sessions as Bearer, so presence of
        # the header alone proves nothing — only resolution counts.)
        presented = bool((authorization or "").strip() or (x_api_key or "").strip())
        alive = False
        if presented:
            try:
                alive = _RESOLVE(authorization) is not None
            except Exception:
                alive = False
        if presented and not alive:
            raise HTTPException(401, "Session expired. Please sign in again.")
        raise HTTPException(403, f"Insufficient permissions for role '{role}' (needs: {', '.join(perms)})")
    return role


# Guests see the product, never the person. These borrower columns stay
# server-side for role == "guest" (applied to lists AND detail views).
GUEST_HIDDEN_BORROWER_FIELDS = {"phone", "email", "address_line", "bank_account", "device_id"}


def _scrub_borrower(b: dict, role: str) -> dict:
    if role != "guest":
        return b
    return {k: v for k, v in b.items() if k not in GUEST_HIDDEN_BORROWER_FIELDS}


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    expires_days: int = Field(default=90, ge=1, le=365)
    scopes: str = "read"


@router.get("/admin/keys")
def list_keys(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    # Key metadata (prefix, never the secret) is readable with admin.read;
    # creating/revoking still requires keys.manage.
    require_perm(authorization, x_api_key, "keys.manage", "admin.read")
    from datetime import datetime
    conn = _DB()
    try:
        rows = []
        for r in conn.execute(
                "SELECT id, prefix, name, created_at, last_used, revoked, expires_at, scopes"
                " FROM ls_api_keys ORDER BY id DESC"):
            r = dict(r)
            r["expired"] = bool(r.get("expires_at") and r["expires_at"] <= datetime.utcnow().isoformat())
            rows.append(r)
        return rows
    finally:
        conn.close()


@router.post("/admin/keys")
def create_key(item: ApiKeyIn, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "keys.manage")
    scopes = sorted({s.strip() for s in (item.scopes or "").split(",") if s.strip()})
    if not scopes or any(s not in VALID_SCOPES for s in scopes):
        raise HTTPException(400, f"scopes must be a comma list of: {', '.join(VALID_SCOPES)}")
    import hashlib
    import secrets
    from datetime import datetime, timedelta
    raw = "ls_" + secrets.token_urlsafe(32)
    h = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(days=item.expires_days)).isoformat()
    conn = _DB()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO ls_api_keys (key_hash, prefix, name, created_at, revoked, expires_at, scopes)"
                    " VALUES (?,?,?,?,0,?,?)",
                    (h, raw[:10] + "…", item.name.strip(), now(), expires_at, ",".join(scopes)))
        conn.commit()
        return {"id": cur.lastrowid, "key": raw, "expires_at": expires_at, "scopes": ",".join(scopes),
                "warning": "Copy now — the full key is never stored and cannot be shown again."}
    finally:
        conn.close()


@router.post("/admin/keys/{key_id}/revoke")
def revoke_key(key_id: int, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "keys.manage")
    conn = _DB()
    try:
        conn.execute("UPDATE ls_api_keys SET revoked=1 WHERE id=?", (key_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------------- dashboard ----------------

@router.get("/dashboard/metrics")
def dashboard_metrics():
    conn = _DB()
    try:
        borrowers = [dict(r) for r in conn.execute("SELECT * FROM ls_borrowers")]
        if not borrowers:
            return {"empty": True}
        analyses = latest_analyses(conn)
        docs_by: dict[str, list] = {}
        for d in conn.execute("SELECT * FROM ls_documents"):
            docs_by.setdefault(d["borrower_id"], []).append(dict(d))
        risks = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
        ver = {"verified": 0, "needs_review": 0, "suspicious": 0}
        fraud_high = 0
        buckets = []
        for b in borrowers:
            a = analyses.get(b["borrower_id"], {})
            rl = a.get("risk_level", "MEDIUM")
            risks[rl] = risks.get(rl, 0) + 1
            vb = verification_bucket(b, docs_by.get(b["borrower_id"], []))
            ver[vb] += 1
            if a.get("fraud_risk") == "HIGH":
                fraud_high += 1
            buckets.append((b, a, vb))
        n = len(borrowers)
        trust_vals = [a.get("trust_score") for a in analyses.values() if a.get("trust_score") is not None]
        conf_vals = [a.get("confidence") for a in analyses.values() if a.get("confidence") is not None]
        recent = sorted(
            ((b, analyses[b["borrower_id"]]) for b in borrowers if b["borrower_id"] in analyses),
            key=lambda t: t[1]["id"], reverse=True)[:8]
        return {
            "borrowers": n,
            "low_risk": risks["LOW"], "medium_risk": risks["MEDIUM"], "high_risk": risks["HIGH"],
            "fraud_high": fraud_high,
            "pending_verification": ver["needs_review"] + ver["suspicious"],
            "avg_trust": round(sum(trust_vals) / len(trust_vals), 1) if trust_vals else 0,
            "avg_confidence": round(sum(conf_vals) / len(conf_vals), 1) if conf_vals else 0,
            "risk_distribution": risks, "verification": ver,
            "avg_income": round(sum(b["avg_income_6m"] for b in borrowers) / n),
            "avg_expenses": round(sum(b["avg_expenses_6m"] for b in borrowers) / n),
            "avg_debt": round(sum(b["avg_debt_6m"] for b in borrowers) / n),
            "total_transactions": sum(b["total_transactions_6m"] for b in borrowers),
            "recent": [{
                "borrower_id": b["borrower_id"], "name": b["name"],
                "trust": a.get("trust_score"), "risk": a.get("risk_level"),
                "fraud": a.get("fraud_risk"), "requested": b["requested_amount"],
                "recommended": a.get("recommended_amount"), "decision": a.get("decision"),
                "confidence": a.get("confidence")} for b, a in recent],
        }
    finally:
        conn.close()


@router.get("/dashboard/trends")
def dashboard_trends():
    """Portfolio monthly averages across all borrowers — powers animated charts."""
    conn = _DB()
    try:
        rows = [dict(r) for r in conn.execute(
            """SELECT label, AVG(income) income, AVG(expenses) expenses, AVG(debt) debt,
                      AVG(transactions) txns, SUM(bounced) bounced, SUM(disputed) disputed,
                      COUNT(*) n
               FROM ls_financials GROUP BY month ORDER BY month""")]
        return rows
    finally:
        conn.close()


# ---------------- borrowers ----------------
@router.get("/borrowers")
def list_borrowers(q: str = "", risk: str = "all", verification: str = "all",
                   city: str = "all", employment: str = "all",
                   sort: str = "trust_desc", page: int = 1, page_size: int = 12,
                   authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "borrower.read")
    page_size = max(1, min(page_size, 50))
    conn = _DB()
    try:
        borrowers = [dict(r) for r in conn.execute("SELECT * FROM ls_borrowers")]
        analyses = latest_analyses(conn)
        docs_by: dict[str, list] = {}
        for d in conn.execute("SELECT * FROM ls_documents"):
            docs_by.setdefault(d["borrower_id"], []).append(dict(d))
        rows = []
        ql = q.strip().lower()
        for b in borrowers:
            a = analyses.get(b["borrower_id"], {})
            vb = verification_bucket(b, docs_by.get(b["borrower_id"], []))
            if ql and ql not in f"{b['borrower_id']} {b['name']} {b['city']}".lower():
                continue
            if risk != "all" and a.get("risk_level") != risk:
                continue
            if verification != "all" and vb != verification:
                continue
            if city != "all" and b["city"] != city:
                continue
            if employment != "all" and b["employment_type"] != employment:
                continue
            rows.append({
                "borrower_id": b["borrower_id"], "name": b["name"], "age": b["age"],
                "city": b["city"], "employment": b["employment_type"], "income": b["avg_income_6m"],
                "requested": b["requested_amount"], "trust": a.get("trust_score"),
                "risk": a.get("risk_level"), "fraud": a.get("fraud_risk"),
                "verification": vb, "decision": a.get("decision")})
        keys = {"trust_desc": (lambda r: -(r["trust"] or -1)), "trust_asc": (lambda r: (r["trust"] if r["trust"] is not None else 999)),
                "requested_desc": (lambda r: -r["requested"]), "requested_asc": (lambda r: r["requested"]),
                "name_asc": (lambda r: r["name"])}
        rows.sort(key=keys.get(sort, keys["trust_desc"]))
        total = len(rows)
        page = max(1, page)
        return {"total": total, "page": page, "page_size": page_size,
                "rows": rows[(page - 1) * page_size: page * page_size],
                "facets": {"cities": sorted({b["city"] for b in borrowers}),
                           "employments": sorted({b["employment_type"] for b in borrowers})}}
    finally:
        conn.close()


@router.get("/borrowers/{bid}")
def get_borrower(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    role = require_perm(authorization, x_api_key, "borrower.read")
    conn = _DB()
    try:
        b = conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone()
        if not b:
            raise HTTPException(404, "Borrower not found")
        b = _scrub_borrower(dict(b), role)
        docs = [dict(r) for r in conn.execute("SELECT * FROM ls_documents WHERE borrower_id=?", (bid,))]
        b["verification_bucket"] = verification_bucket(b, docs)
        b["documents"] = docs
        return b
    finally:
        conn.close()


@router.get("/borrowers/{bid}/financials")
def get_financials(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "borrower.read")
    conn = _DB()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM ls_financials WHERE borrower_id=? ORDER BY month", (bid,))]
        if not rows:
            raise HTTPException(404, "Borrower not found")
        return rows
    finally:
        conn.close()


@router.get("/borrowers/{bid}/cashflow")
def get_cashflow(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    """Per-borrower cash flow: monthly money in/out from financial snapshots
    plus loan-obligation timeline (due vs actually paid per month) and a
    computed summary. Powers the interactive bar/line charts."""
    require_perm(authorization, x_api_key, "borrower.read")
    conn = _DB()
    try:
        b = conn.execute("SELECT borrower_id FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone()
        if not b:
            raise HTTPException(404, "Borrower not found")
        snaps = [dict(r) for r in conn.execute(
            "SELECT month, label, income, expenses, debt, transactions, bounced"
            " FROM ls_financials WHERE borrower_id=? ORDER BY month", (bid,))]
        loans = [dict(r) for r in conn.execute(
            "SELECT id, principal, emi, status, disbursed_at FROM ls_loans WHERE borrower_id=?", (bid,))]
        loan_ids = [l["id"] for l in loans]
        sched = []
        reps = []
        if loan_ids:
            q = ",".join("?" for _ in loan_ids)
            sched = [dict(r) for r in conn.execute(
                f"SELECT loan_id, n, due_date, total_due, paid, status FROM ls_schedule"
                f" WHERE loan_id IN ({q}) ORDER BY due_date", loan_ids)]
            reps = [dict(r) for r in conn.execute(
                f"SELECT loan_id, amount, created_at FROM ls_repayments WHERE loan_id IN ({q})", loan_ids)]
        # Bucket obligations + actuals by calendar month.
        obl: dict[str, dict] = {}
        for s in sched:
            m = (s["due_date"] or "")[:7]
            if len(m) != 7:
                continue
            o = obl.setdefault(m, {"month": m, "due": 0.0, "paid_due": 0.0, "missed": 0})
            o["due"] += s["total_due"] or 0
            o["paid_due"] += s["paid"] or 0
            if (s["status"] or "") in ("MISSED", "LATE"):
                o["missed"] += 1
        pay: dict[str, float] = {}
        for r in reps:
            m = (r["created_at"] or "")[:7]
            if len(m) == 7:
                pay[m] = pay.get(m, 0.0) + (r["amount"] or 0)
        months = sorted(set(obl) | set(pay))
        monthly = [{"month": m, "due": round(obl.get(m, {}).get("due", 0.0), 2),
                    "paid_scheduled": round(obl.get(m, {}).get("paid_due", 0.0), 2),
                    "paid_actual": round(pay.get(m, 0.0), 2),
                    "missed": obl.get(m, {}).get("missed", 0)} for m in months]
        tot_in = round(sum((s.get("income") or 0) for s in snaps), 2)
        tot_out = round(sum((s.get("expenses") or 0) for s in snaps), 2)
        tot_due = round(sum(m["due"] for m in monthly), 2)
        tot_paid = round(sum(m["paid_actual"] for m in monthly), 2)
        overdue = round(sum(m["due"] - m["paid_scheduled"] for m in monthly
                            if m["due"] > m["paid_scheduled"]), 2)
        upcoming = [s for s in sched if (s["status"] or "") == "UPCOMING"]
        nxt = min(upcoming, key=lambda s: s["due_date"]) if upcoming else None
        return {
            "borrower_id": bid,
            "snapshots": snaps,
            "monthly_obligations": monthly,
            "loans": [{"id": l["id"], "principal": l["principal"], "emi": l["emi"],
                       "status": l["status"], "disbursed_at": l["disbursed_at"]} for l in loans],
            "summary": {
                "total_income": tot_in, "total_expenses": tot_out,
                "net": round(tot_in - tot_out, 2),
                "total_due": tot_due, "total_paid_actual": tot_paid,
                "overdue": overdue, "months_covered": len(months),
                "next_due": ({"date": nxt["due_date"],
                              "amount": round((nxt["total_due"] or 0) - (nxt["paid"] or 0), 2)}
                             if nxt else None),
            },
        }
    finally:
        conn.close()


# ---------------- analysis ----------------

def _persist_analysis(conn, bid: str, res: dict, actor: str) -> int:
    r, fr, t, rec = res["risk"], res["fraud"], res["trust"], res["recommendation"]
    cur = conn.cursor()
    ts = now()
    cur.execute(
        """INSERT INTO ls_analyses (borrower_id, model_version, risk_score, risk_level, fraud_score,
           fraud_risk, trust_score, confidence, decision, recommended_amount, interest_rate,
           duration_months, monthly_payment, ml_score, risk_factors, fraud_signals, trust_factors,
           input_snapshot, created_at, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bid, res.get("model_version", DEFAULT_CONFIG["model_version"]), r["risk_score"], r["risk_level"], fr["fraud_score"],
         fr["fraud_risk"], t["trust_score"], rec["confidence"], rec["decision"], rec["recommended_amount"],
         rec["interest_rate"], rec["duration_months"], rec["monthly_payment"], res.get("ml_proba"),
         json.dumps(r["factors"]), json.dumps(fr["signals"]), json.dumps(t["trust_factors"]),
         res["input_snapshot"], ts, actor))
    aid = cur.lastrowid
    cur.execute(
        """INSERT INTO ls_recommendations (analysis_id, borrower_id, recommended_amount, interest_rate,
           duration_months, monthly_payment, total_repayment, decision, rationale, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (aid, bid, rec["recommended_amount"], rec["interest_rate"], rec["duration_months"],
         rec["monthly_payment"], rec["total_repayment"], rec["decision"], rec["rationale"], ts))
    for e in res["evidence"]:
        cur.execute("INSERT INTO ls_evidence (analysis_id, category, label, value, sort) VALUES (?,?,?,?,?)",
                    (aid, e["category"], e["label"], e["value"], e["sort"]))
    _audit_log(conn, bid, aid, actor, "analysis_completed",
               {"risk": r["risk_level"], "fraud": fr["fraud_risk"], "trust": t["trust_score"],
                "decision": rec["decision"], "model": DEFAULT_CONFIG["model_version"]})
    conn.commit()
    return aid


@router.post("/borrowers/{bid}/analyze")
def analyze_borrower(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "analysis.run")
    conn = _DB()
    try:
        b = conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone()
        if not b:
            raise HTTPException(404, "Borrower not found")
        b = dict(b)
        snaps = [dict(r) for r in conn.execute("SELECT * FROM ls_financials WHERE borrower_id=? ORDER BY month", (bid,))]
        docs = [dict(r) for r in conn.execute("SELECT * FROM ls_documents WHERE borrower_id=?", (bid,))]
        # Repayment feedback loop: real recorded performance adjusts the
        # baseline counters, so missed/on-time repayments genuinely move
        # the next risk score (visible in the analysis + audit trail).
        b = merge_perf(conn, bid, b)
        dup = conn.execute("SELECT COUNT(*) c FROM ls_borrowers WHERE borrower_id != ? AND borrower_id IN "
                           "(SELECT borrower_id FROM ls_borrowers GROUP BY borrower_id HAVING COUNT(*)>1)",
                           (bid,)).fetchone()["c"] > 0
        res = full_analysis(b, snaps, docs, dup, cfg_all(conn))
        aid = _persist_analysis(conn, bid, res, actor_of(authorization, x_api_key))
        try:
            from .intel import log_prediction
            log_prediction(conn, bid, aid, res.get("model_version", ""), res.get("ml_proba"))
            conn.commit()
        except Exception:
            pass
        return {"analysis_id": aid, **{k: v for k, v in res.items() if k != "input_snapshot"}}
    finally:
        conn.close()


def _latest_full(conn, bid: str) -> dict:
    a = conn.execute("SELECT * FROM ls_analyses WHERE borrower_id=? ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
    if not a:
        raise HTTPException(404, "No analysis yet — run analysis first")
    a = dict(a)
    rec = conn.execute("SELECT * FROM ls_recommendations WHERE analysis_id=?", (a["id"],)).fetchone()
    ev = [dict(r) for r in conn.execute(
        "SELECT category, label, value FROM ls_evidence WHERE analysis_id=? ORDER BY category, sort", (a["id"],))]
    snap = json.loads(a["input_snapshot"])
    fin = {k: snap.get(k) for k in ("avg_income_6m", "avg_expenses_6m", "avg_debt_6m")}
    inc = fin["avg_income_6m"] or 1
    out = dict(a)
    rec_d = dict(rec) if rec else None
    if rec_d is not None:
        # confidence lives on the analysis; burden is derived from stored inputs
        rec_d["confidence"] = a["confidence"]
        _inc = (snap.get("avg_income_6m") or snap.get("monthly_income") or 0) or 1
        rec_d["repayment_burden"] = round((rec_d.get("monthly_payment") or 0) / _inc, 3)
    out["recommendation"] = rec_d
    out["evidence"] = ev
    out["ml_proba"] = a["ml_score"]
    try:
        out["factors"] = json.loads(a["risk_factors"] or "[]")
        out["signals"] = json.loads(a["fraud_signals"] or "[]")
        out["trust_factors"] = json.loads(a["trust_factors"] or "[]")
    except Exception:
        out["factors"], out["signals"], out["trust_factors"] = [], [], []
    out["financial"] = {
        "avg_income": fin["avg_income_6m"], "avg_expenses": fin["avg_expenses_6m"], "avg_debt": fin["avg_debt_6m"],
        "dti": round(fin["avg_debt_6m"] / inc, 3), "lti": round(snap.get("requested_amount", 0) / inc, 2),
        "repayment_capacity": round((fin["avg_income_6m"] - fin["avg_expenses_6m"]) / inc, 3)}
    return out


@router.get("/borrowers/{bid}/analysis")
def get_analysis(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    role = require_perm(authorization, x_api_key, "analysis.read")
    conn = _DB()
    try:
        out = _latest_full(conn, bid)
        if role == "guest":
            # The stored input snapshot is the raw borrower row (incl. PII).
            out.pop("input_snapshot", None)
        return out
    finally:
        conn.close()


@router.get("/borrowers/{bid}/evidence")
def get_evidence(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "analysis.read")
    conn = _DB()
    try:
        a = conn.execute("SELECT id FROM ls_analyses WHERE borrower_id=? ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
        if not a:
            raise HTTPException(404, "No analysis yet")
        rows = [dict(r) for r in conn.execute(
            "SELECT category, label, value FROM ls_evidence WHERE analysis_id=? ORDER BY category, sort", (a["id"],))]
        grouped: dict[str, list] = {}
        for r in rows:
            grouped.setdefault(r["category"], []).append({"label": r["label"], "value": r["value"]})
        return {"analysis_id": a["id"], "groups": grouped}
    finally:
        conn.close()


@router.get("/borrowers/{bid}/recommendation")
def get_recommendation(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "analysis.read")
    conn = _DB()
    try:
        a = conn.execute("SELECT id FROM ls_analyses WHERE borrower_id=? ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
        if not a:
            raise HTTPException(404, "No analysis yet")
        r = conn.execute("SELECT * FROM ls_recommendations WHERE analysis_id=?", (a["id"],)).fetchone()
        return dict(r)
    finally:
        conn.close()


class SimulateIn(BaseModel):
    borrower_id: str
    amount: float = Field(gt=0)
    interest_rate: float = Field(ge=0, le=60)
    duration_months: int = Field(ge=1, le=60)


@router.post("/recommendations/simulate")
def simulate(sim: SimulateIn, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "simulation.run")
    conn = _DB()
    try:
        b = conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?", (sim.borrower_id,)).fetchone()
        if not b:
            raise HTTPException(404, "Borrower not found")
        b = dict(b)
        snaps = [dict(r) for r in conn.execute("SELECT * FROM ls_financials WHERE borrower_id=? ORDER BY month", (sim.borrower_id,))]
        docs = [dict(r) for r in conn.execute("SELECT * FROM ls_documents WHERE borrower_id=?", (sim.borrower_id,))]
        res = full_analysis(b, snaps, docs, False, cfg_all(conn))
        rec = RecommendationEngine.run(b, res["risk"], res["fraud"], res["trust"], cfg_all(conn),
                                       amount=sim.amount, rate=sim.interest_rate, duration=sim.duration_months)
        pay = emi(sim.amount, sim.interest_rate, sim.duration_months)
        inc = b["avg_income_6m"] or 1
        _audit_log(conn, sim.borrower_id, None, actor_of(authorization, x_api_key), "simulation",
                     {"amount": sim.amount, "rate": sim.interest_rate, "duration": sim.duration_months,
                      "decision": rec["decision"]})
        conn.commit()
        return {**rec, "monthly_payment": pay, "total_repayment": round(pay * sim.duration_months, 2),
                "base_risk": res["risk"]["risk_level"], "base_trust": res["trust"]["trust_score"]}
    finally:
        conn.close()


@router.get("/borrowers/{bid}/audit")
def get_audit(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "analysis.read")
    conn = _DB()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM ls_audit WHERE borrower_id=? ORDER BY id DESC LIMIT 50", (bid,))]
    finally:
        conn.close()


# ---------------- documents ----------------

class DocIn(BaseModel):
    doc_type: str
    file_name: str
    status: str = "needs_review"
    quality_score: int = 70
    note: str = ""


@router.get("/borrowers/{bid}/documents")
def get_documents(bid: str, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "borrower.read")
    conn = _DB()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM ls_documents WHERE borrower_id=?", (bid,))]
    finally:
        conn.close()


@router.post("/borrowers/{bid}/documents")
def add_document(bid: str, doc: DocIn, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "documents.write")
    if doc.status not in ("verified", "needs_review", "suspicious"):
        raise HTTPException(400, "Invalid status")
    if doc.doc_type not in ("identity", "bank_statement", "income_document", "salary_slip", "business_document"):
        raise HTTPException(400, "Unknown document type")
    if not doc.file_name.strip():
        raise HTTPException(400, "File name is required")
    if not (0 <= doc.quality_score <= 100):
        raise HTTPException(400, "Quality score must be 0-100")
    conn = _DB()
    try:
        if not conn.execute("SELECT 1 FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone():
            raise HTTPException(404, "Borrower not found")
        cur = conn.cursor()
        cur.execute("INSERT INTO ls_documents (borrower_id, doc_type, file_name, status, quality_score, note, created_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (bid, doc.doc_type, doc.file_name, doc.status, doc.quality_score, doc.note, now()))
        did = cur.lastrowid
        _audit_log(conn, bid, None, actor_of(authorization, x_api_key), "document_uploaded",
                     {"doc_id": did, "type": doc.doc_type, "file": doc.file_name})
        from .jobs import enqueue
        enqueue(conn, "document.verify", "document", did, {"doc_id": did},
                idempotency_key=f"docverify-{did}")
        conn.commit()
        return {"id": did, **doc.model_dump()}
    finally:
        conn.close()


class DocPatch(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None


@router.post("/borrowers/{bid}/documents/upload")
def upload_document(bid: str, doc_type: str = Form(...), file: UploadFile = File(...),
                    authorization: str | None = Header(default=None),
                    x_api_key: str | None = Header(default=None)):
    """Real file upload: bytes stored privately (lender-only reads), sha256
    recorded, then an async verification job runs the deterministic checks.
    2MB cap. OCR/malware-scan are NOT_AVAILABLE in this deployment and are
    reported as such — never fabricated."""
    from .api import require_perm as _rp  # local alias (same module)
    _rp(authorization, x_api_key, "documents.write")
    if doc_type not in ("identity", "bank_statement", "income_document", "salary_slip", "business_document"):
        raise HTTPException(400, "Unknown document type")
    data = file.file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "File exceeds 2MB cap")
    if not data:
        raise HTTPException(400, "Empty file")
    import hashlib as _hl
    digest = _hl.sha256(data).hexdigest()
    conn = _DB()
    try:
        if not conn.execute("SELECT 1 FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone():
            raise HTTPException(404, "Borrower not found")
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ls_documents (borrower_id, doc_type, file_name, status, quality_score, note,"
            " pipeline_status, content_hash, created_at) VALUES (?,?,?,?,?,?,?, ?,?)",
            (bid, doc_type, file.filename or "upload", "needs_review", 70, "",
             "PENDING", digest, now()))
        did = cur.lastrowid
        cur.execute("INSERT INTO ls_doc_files (doc_id, sha256, size_bytes, mime, data, created_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (did, digest, len(data), file.content_type or "", data, now()))
        _audit_log(conn, bid, None, actor_of(authorization, x_api_key), "document_uploaded",
                     {"doc_id": did, "type": doc_type, "file": file.filename,
                      "sha256": digest[:16], "bytes": len(data)})
        from .jobs import enqueue
        jid = enqueue(conn, "document.verify", "document", did, {"doc_id": did},
                      idempotency_key=f"docverify-{did}")
        conn.commit()
        return {"id": did, "sha256": digest, "bytes": len(data), "job_id": jid,
                "pipeline": "PENDING",
                "note": "Verification runs asynchronously; poll the document row or jobs API."}
    finally:
        conn.close()


@router.get("/documents/{doc_id}/file")
def download_document(doc_id: int, authorization: str | None = Header(default=None),
                      x_api_key: str | None = Header(default=None)):
    """Private document bytes — lender role only, never public."""
    from fastapi.responses import Response as _Response
    require_perm(authorization, x_api_key, "documents.write")
    conn = _DB()
    try:
        doc = conn.execute("SELECT borrower_id, file_name FROM ls_documents WHERE id=?",
                           (doc_id,)).fetchone()
        f = conn.execute("SELECT * FROM ls_doc_files WHERE doc_id=?", (doc_id,)).fetchone()
        if not doc or not f:
            raise HTTPException(404, "File not found")
        return _Response(content=bytes(f["data"]),
                         media_type=f["mime"] or "application/octet-stream",
                         headers={"Content-Disposition": f'attachment; filename="{doc["file_name"]}"'})
    finally:
        conn.close()


@router.patch("/documents/{doc_id}")
def patch_document(doc_id: int, patch: DocPatch, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "documents.write")
    if patch.status and patch.status not in ("verified", "needs_review", "suspicious"):
        raise HTTPException(400, "Invalid status")
    conn = _DB()
    try:
        d = conn.execute("SELECT * FROM ls_documents WHERE id=?", (doc_id,)).fetchone()
        if not d:
            raise HTTPException(404, "Document not found")
        d = dict(d)
        if patch.status:
            conn.execute("UPDATE ls_documents SET status=? WHERE id=?", (patch.status, doc_id))
        if patch.note is not None:
            conn.execute("UPDATE ls_documents SET note=? WHERE id=?", (patch.note, doc_id))
        _audit_log(conn, d["borrower_id"], None, actor_of(authorization, x_api_key), "document_reviewed",
                     {"doc_id": doc_id, "status": patch.status or d["status"]})
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------------- admin ----------------

@router.get("/admin/stats")
def admin_stats(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    conn = _DB()
    try:
        nb = conn.execute("SELECT COUNT(*) c FROM ls_borrowers").fetchone()["c"]
        na = conn.execute("SELECT COUNT(*) c FROM ls_analyses").fetchone()["c"]
        avg_t = conn.execute("SELECT COALESCE(AVG(trust_score),0) v FROM ls_analyses a JOIN "
                             "(SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x "
                             "ON x.borrower_id=a.borrower_id AND x.m=a.id").fetchone()["v"]
        mix = {r["decision"]: r["c"] for r in conn.execute(
            "SELECT decision, COUNT(*) c FROM ls_analyses a JOIN "
            "(SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x "
            "ON x.borrower_id=a.borrower_id AND x.m=a.id GROUP BY decision")}
        return {"borrowers": nb, "analyses": na, "avg_trust": round(avg_t or 0, 1),
                "decision_mix": mix, "model_version": _active_model_version()}
    finally:
        conn.close()


@router.get("/admin/config")
def get_config(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    conn = _DB()
    try:
        return cfg_all(conn)
    finally:
        conn.close()


class ConfigIn(BaseModel):
    key: str
    value: Any


@router.put("/admin/config")
def put_config(item: ConfigIn, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "policy.update")
    if item.key not in DEFAULT_CONFIG or item.key == "model_version":
        raise HTTPException(400, "Unknown or locked config key")
    conn = _DB()
    try:
        conn.execute("INSERT INTO ls_config (key, value, updated_at) VALUES (?,?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                     (item.key, json.dumps(item.value), now()))
        _audit_log(conn, "*", None, actor_of(authorization, x_api_key), "config_changed",
                     {"key": item.key, "value": item.value})
        conn.commit()
        return {"ok": True, "key": item.key, "value": item.value}
    finally:
        conn.close()


@router.get("/admin/model")
def admin_model(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    from . import ml as _ml
    m = _ml.metrics()
    m["loaded"] = _ml.loaded()
    m["artifact"] = "models/risk_model.joblib"
    return m


def _active_model_version() -> str:
    from . import ml as _ml
    from .schema import MODEL_VERSION as _rules
    try:
        return _ml.MODEL_ID if _ml.loaded() else _rules
    except Exception:
        return _rules


@router.get("/admin/audit")
def admin_audit(limit: int = 50, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    conn = _DB()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM ls_audit ORDER BY id DESC LIMIT ?", (min(limit, 200),))]
    finally:
        conn.close()


@router.get("/admin/audit/verify")
def admin_audit_verify(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    """Walk the tamper-evident hash chain. ok=false names the first bad row."""
    require_perm(authorization, x_api_key, "admin.read")
    from .notify import verify_audit_chain
    conn = _DB()
    try:
        return verify_audit_chain(conn)
    finally:
        conn.close()


# ---------------- admin: backups ----------------
# SQLite file snapshots for the single-file deployment. Kept beside the live
# DB (NOT in git). Render's free disk survives restarts but not redeploys —
# download copies off-host on a schedule; Postgres remains the real answer.

BACKUP_KEEP = 7


def _backup_dir() -> "Path":
    from pathlib import Path as _P
    conn = _DB()
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        live = _P(row["file"]).resolve()
    finally:
        conn.close()
    d = live.parent / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_name_ok(name: str) -> bool:
    import re
    return re.fullmatch(r"lending-\d{8}T\d{6}\.db", name or "") is not None


@router.post("/admin/backup")
def create_backup(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "jobs.manage")
    import sqlite3
    from pathlib import Path as _P
    d = _backup_dir()
    name = f"lending-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.db"
    dest = d / name
    src = _DB()
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    kept = sorted(p.name for p in d.glob("lending-*.db"))
    for old in kept[:-BACKUP_KEEP]:
        try:
            (d / old).unlink()
        except Exception:
            pass
    kept = sorted(p.name for p in d.glob("lending-*.db"))
    return {"ok": True, "file": name, "bytes": dest.stat().st_size,
            "kept": kept, "note": "Download off-host on a schedule — free-tier disk does not survive redeploys."}


@router.get("/admin/backups")
def list_backups(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "jobs.manage")
    d = _backup_dir()
    out = []
    for p in sorted(d.glob("lending-*.db"), reverse=True):
        out.append({"file": p.name, "bytes": p.stat().st_size,
                    "created_at": datetime.utcfromtimestamp(p.stat().st_mtime).isoformat()})
    return out


@router.get("/admin/backups/{name}")
def download_backup(name: str, authorization: str | None = Header(default=None),
                    x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "jobs.manage")
    from fastapi.responses import FileResponse
    if not _backup_name_ok(name):
        raise HTTPException(400, "Invalid backup name")
    p = _backup_dir() / name
    if not p.exists():
        raise HTTPException(404, "Backup not found")
    return FileResponse(str(p), media_type="application/x-sqlite3", filename=name)


# ---------------- admin: command center ----------------

REVIEW_DECISIONS = ("APPROVE", "APPROVE_WITH_CONDITIONS", "REDUCE_AMOUNT", "MANUAL_REVIEW", "REJECT")


def _ensure_review_cols(conn):
    for _col, _typ in (("review_decision", "TEXT"), ("review_note", "TEXT"),
                       ("reviewed_by", "TEXT"), ("reviewed_at", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE ls_analyses ADD COLUMN {_col} {_typ}")
        except Exception:
            pass  # already exists


_LATEST_JOIN = ("ls_analyses a JOIN (SELECT borrower_id, MAX(id) m FROM ls_analyses "
                "GROUP BY borrower_id) x ON x.borrower_id=a.borrower_id AND x.m=a.id")


@router.get("/admin/overview")
def admin_overview(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    conn = _DB()
    try:
        _ensure_review_cols(conn)
        nb = conn.execute("SELECT COUNT(*) c FROM ls_borrowers").fetchone()["c"]
        na = conn.execute("SELECT COUNT(*) c FROM ls_analyses").fetchone()["c"]
        latest = conn.execute(
            f"SELECT a.* FROM {_LATEST_JOIN}").fetchall()
        latest = [dict(r) for r in latest]
        mix: dict[str, int] = {}
        trust_vals, conf_vals = [], []
        pending = reviewed = high_risk = high_fraud = 0
        for a in latest:
            d = a.get("decision") or "UNKNOWN"
            mix[d] = mix.get(d, 0) + 1
            if a.get("trust_score") is not None:
                trust_vals.append(a["trust_score"])
            if a.get("confidence") is not None:
                conf_vals.append(a["confidence"])
            if (a.get("risk_level") or "") == "HIGH":
                high_risk += 1
            if (a.get("fraud_risk") or "") == "HIGH":
                high_fraud += 1
            if a.get("review_decision"):
                reviewed += 1
            elif d == "MANUAL_REVIEW":
                pending += 1
        # 14-day analysis volume
        series = [{"day": r["day"], "count": r["c"]} for r in conn.execute(
            "SELECT substr(created_at,1,10) day, COUNT(*) c FROM ls_analyses "
            "WHERE created_at >= datetime('now','-14 days') GROUP BY day ORDER BY day")]
        # recent activity with borrower names
        recent = [dict(r) for r in conn.execute(
            "SELECT au.*, b.name borrower_name FROM ls_audit au "
            "LEFT JOIN ls_borrowers b ON b.borrower_id=au.borrower_id "
            "ORDER BY au.id DESC LIMIT 8")]
        nkeys = conn.execute("SELECT COUNT(*) c FROM ls_api_keys WHERE revoked=0").fetchone()["c"]
        return {
            "borrowers": nb, "analyses": na,
            "decision_mix": mix, "pending_review": pending, "reviewed": reviewed,
            "high_risk": high_risk, "high_fraud": high_fraud,
            "avg_trust": round(sum(trust_vals) / len(trust_vals), 1) if trust_vals else 0,
            "avg_confidence": round(sum(conf_vals) / len(conf_vals), 1) if conf_vals else 0,
            "series_14d": series, "recent_activity": recent,
            "active_api_keys": nkeys, "model_version": _active_model_version(),
        }
    finally:
        conn.close()


# ---------------- admin: approvals ----------------

@router.get("/admin/approvals")
def admin_approvals(decision: str = "all", q: str = "", page: int = 1, page_size: int = 12,
                    authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    page_size = max(1, min(page_size, 50))
    q = (q or "")[:80]
    conn = _DB()
    try:
        _ensure_review_cols(conn)
        rows = [dict(r) for r in conn.execute(
            "SELECT a.*, b.name borrower_name, b.city, b.requested_amount, b.monthly_income "
            "FROM ls_analyses a LEFT JOIN ls_borrowers b ON b.borrower_id=a.borrower_id "
            "ORDER BY a.id DESC")]
        ql = (q or "").strip().lower()
        out = []
        for a in rows:
            if ql and ql not in f"{a.get('borrower_id','')} {a.get('borrower_name') or ''}".lower():
                continue
            rev = a.get("review_decision")
            if decision == "pending":
                if rev or a.get("decision") != "MANUAL_REVIEW":
                    continue
            elif decision == "reviewed":
                if not rev:
                    continue
            elif decision != "all" and a.get("decision") != decision:
                continue
            out.append({k: a.get(k) for k in (
                "id", "borrower_id", "borrower_name", "city", "requested_amount", "monthly_income",
                "model_version", "risk_score", "risk_level", "fraud_score", "fraud_risk",
                "trust_score", "confidence", "decision", "recommended_amount", "interest_rate",
                "duration_months", "monthly_payment", "created_at", "created_by",
                "review_decision", "review_note", "reviewed_by", "reviewed_at")})
        total = len(out)
        page = max(1, page)
        return {"total": total, "page": page, "page_size": page_size,
                "rows": out[(page - 1) * page_size: page * page_size]}
    finally:
        conn.close()


class ReviewIn(BaseModel):
    decision: str
    note: str = ""


@router.post("/admin/approvals/{aid}/review")
def review_approval(aid: int, item: ReviewIn,
                    authorization: str | None = Header(default=None),
                    x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "review.decide")
    if item.decision not in REVIEW_DECISIONS:
        raise HTTPException(400, f"Decision must be one of {', '.join(REVIEW_DECISIONS)}")
    if item.decision == "REJECT" and len((item.note or "").strip()) < 5:
        raise HTTPException(400, "A reason (min 5 characters) is required to reject")
    conn = _DB()
    try:
        _ensure_review_cols(conn)
        a = conn.execute("SELECT * FROM ls_analyses WHERE id=?", (aid,)).fetchone()
        if not a:
            raise HTTPException(404, "Analysis not found")
        a = dict(a)
        actor = actor_of(authorization, x_api_key)
        ts = now()
        conn.execute("UPDATE ls_analyses SET review_decision=?, review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?",
                     (item.decision, (item.note or "").strip(), actor, ts, aid))
        _audit_log(conn, a["borrower_id"], aid, actor, "review_decision",
                      {"from": a["decision"], "to": item.decision,
                       "note": (item.note or "").strip()})
        conn.commit()
        return {"ok": True, "analysis_id": aid, "from": a["decision"], "to": item.decision}
    finally:
        conn.close()


# ---------------- admin: sessions ----------------

@router.get("/admin/sessions")
def admin_sessions(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    mine = (authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else "")
    # sessions table lives in the app DB, not the lendsure module DB handle —
    # both point at the same file, so query through this connection.
    conn = _DB()
    try:
        try:
            rows = conn.execute(
                "SELECT rowid AS sid, token, phone, display_name, role, created_at, expires_at FROM sessions ORDER BY created_at DESC LIMIT 100").fetchall()
        except Exception:
            return []
        # NEVER return live tokens: only the prefix (for display) plus the
        # internal row id, which is what revocation resolves server-side.
        return [{"id": r["sid"], "token_prefix": r["token"][:8] + "…",
                 "phone": r["phone"], "display_name": r["display_name"], "role": r["role"],
                 "created_at": r["created_at"], "expires_at": r["expires_at"],
                 "current": r["token"] == mine,
                 "expired": r["expires_at"] < now()} for r in rows]
    finally:
        conn.close()


@router.delete("/admin/sessions/{ref}")
def revoke_session(ref: str, authorization: str | None = Header(default=None),
                   x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "sessions.revoke")
    conn = _DB()
    try:
        cur = conn.cursor()
        # Prefer the opaque row id; a full token still works for callers that
        # already hold one (e.g. signing out your own other device).
        row = None
        if ref.isdigit():
            row = cur.execute("SELECT * FROM sessions WHERE rowid=?", (int(ref),)).fetchone()
        if row is None:
            row = cur.execute("SELECT * FROM sessions WHERE token=?", (ref,)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        cur.execute("DELETE FROM sessions WHERE token=?", (row["token"],))
        _audit_log(conn, "*", None, actor_of(authorization, x_api_key), "session_revoked",
                     {"phone": row["phone"], "display_name": row["display_name"]})
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------------- admin: feature registry + model registry ----------------

def _ensure_registry(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS ls_model_registry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL,
        metrics_json TEXT DEFAULT '{}', approved_by TEXT DEFAULT '',
        created_at TEXT NOT NULL, deployed_at TEXT)""")
    if conn.execute("SELECT COUNT(*) c FROM ls_model_registry").fetchone()["c"] == 0:
        from . import ml as _ml
        m = _ml.metrics()
        conn.execute("INSERT INTO ls_model_registry (name, version, status, metrics_json, approved_by, created_at, deployed_at)"
                     " VALUES (?,?,?,?,?,?,?)",
                     ("repayment-risk", m.get("model_id", "unknown"), "DEPLOYED",
                      json.dumps({k: m.get(k) for k in
                                  ("test_auc", "test_ap", "test_accuracy", "test_precision", "test_recall",
                                   "label_rate", "brier_score", "cv_auc_mean")}),
                      "training-pipeline", m.get("trained_at", now()), m.get("trained_at", now())))
        conn.commit()


@router.get("/admin/features")
def admin_features(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    from .feature_dict import ENGINEERED_DICT, FEATURES, GROUPS
    return {"groups": GROUPS, "features": FEATURES, "engineered": ENGINEERED_DICT,
            "count_raw": len(FEATURES), "count_engineered": len(ENGINEERED_DICT)}


@router.get("/admin/registry")
def admin_registry(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
    require_perm(authorization, x_api_key, "admin.read")
    conn = _DB()
    try:
        _ensure_registry(conn)
        return [dict(r) for r in conn.execute("SELECT * FROM ls_model_registry ORDER BY id DESC")]
    finally:
        conn.close()
