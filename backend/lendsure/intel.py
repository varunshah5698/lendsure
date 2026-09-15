"""Intelligence services: subsystem health, model monitoring, risk history,
early warnings and portfolio aggregates. Every number is a live database
aggregate or a recorded model output — never synthesized."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api", tags=["intelligence"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def now() -> str:
    return datetime.utcnow().isoformat()


def _need(authorization: Optional[str], x_api_key: Optional[str] = None, *perms: str) -> str:
    from .api import require_perm
    return require_perm(authorization, x_api_key, *perms)


def _session(authorization: Optional[str]):
    s = _RESOLVE(authorization) if authorization else None
    if not s:
        raise HTTPException(401, "Sign in required")
    return s


# SIMULATION namespace is always excluded from production aggregates.
NOT_SIM = "borrower_id NOT LIKE 'SIM-%'"


# ── subsystem health (real checks with latency) ──

@router.get("/health/db")
def health_db():
    t0 = time.time()
    try:
        conn = _DB()
        try:
            conn.execute("SELECT 1").fetchone()
            tables = conn.execute(
                "SELECT COUNT(*) c FROM sqlite_master WHERE type='table' AND name LIKE 'ls_%'"
            ).fetchone()["c"]
        finally:
            conn.close()
        return {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 1),
                "tables": tables}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/health/ml")
def health_ml():
    t0 = time.time()
    try:
        from . import ml as _ml
        loaded = bool(_ml.loaded())
        m = _ml.metrics()
        return {"ok": loaded, "latency_ms": round((time.time() - t0) * 1000, 1),
                "model_id": m.get("model_id"), "artifact": loaded,
                "note": None if loaded else "artifact missing or unloadable — engines use rules"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/health/graph")
def health_graph():
    t0 = time.time()
    try:
        conn = _DB()
        try:
            ev = conn.execute("SELECT COUNT(*) c FROM ls_events").fetchone()["c"]
        finally:
            conn.close()
        return {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 1),
                "mode": "relational-backed",
                "sync": "in_sync (recomputed per query; nothing to drift)",
                "domain_events": ev,
                "detail": "use /api/ls/graph/stats for counts"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/health/financial-data")
def health_financial():
    t0 = time.time()
    try:
        from . import finance as _f
        with _f._live_lock:
            st = dict(_f._live_status)
        conn = _DB()
        try:
            n_assets = conn.execute("SELECT COUNT(*) c FROM fi_market_assets").fetchone()["c"]
            n_news = conn.execute("SELECT COUNT(*) c FROM fi_news").fetchone()["c"]
            newest = conn.execute("SELECT MAX(updated_at) m FROM fi_market_assets").fetchone()["m"]
        finally:
            conn.close()
        return {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 1),
                "markets": st.get("markets"), "news": st.get("news"),
                "assets": n_assets, "articles": n_news,
                "newest_market_update": newest, "last_refresh_attempt": st.get("last_run")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── prediction logging + model monitoring ──

def log_prediction(conn, borrower_id: str, analysis_id, model_id: str, proba: float):
    if proba is None:
        return
    conn.execute(
        "INSERT INTO ls_predictions (borrower_id,analysis_id,model_id,proba,created_at)"
        " VALUES (?,?,?,?,?)", (borrower_id, analysis_id, model_id, float(proba), now()))


@router.get("/ls/admin/model/monitoring")
def model_monitoring(authorization: Optional[str] = Header(default=None),
                     x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "admin.read")
    from . import ml as _ml
    metrics = _ml.metrics()
    conn = _DB()
    try:
        vol_7 = conn.execute(
            "SELECT COUNT(*) c FROM ls_predictions WHERE created_at >= datetime('now','-7 days')"
        ).fetchone()["c"]
        vol_30 = conn.execute(
            "SELECT COUNT(*) c FROM ls_predictions WHERE created_at >= datetime('now','-30 days')"
        ).fetchone()["c"]
        recent = conn.execute(
            "SELECT AVG(proba) m, COUNT(*) c FROM ls_predictions WHERE created_at >= datetime('now','-30 days')"
        ).fetchone()
        by_model = conn.execute(
            "SELECT model_id, COUNT(*) c, AVG(proba) mean_p FROM ls_predictions GROUP BY model_id"
        ).fetchall()
        baseline = (metrics.get("label_rate")
                    if isinstance(metrics.get("label_rate"), (int, float)) else None)
        rmean = recent["m"]
        drift = None
        if rmean is not None and baseline is not None:
            drift = {"recent_mean_proba": round(rmean, 4), "training_label_rate": baseline,
                     "abs_gap": round(abs(rmean - baseline), 4),
                     "flag": "WATCH" if abs(rmean - baseline) > 0.05 else "OK",
                     "note": "Compares recent production mean P(default) to the training label rate. "
                             "WATCH means investigate, not a failure."}
        return {"model_id": metrics.get("model_id"),
                "training": {k: metrics.get(k) for k in
                             ("test_auc", "test_ap", "test_accuracy", "test_precision",
                              "test_recall", "brier_score", "log_loss", "cv_auc_mean",
                              "cv_auc_std", "decision_threshold", "calibration_method")},
                "production": {"predictions_7d": vol_7, "predictions_30d": vol_30,
                               "by_model": [dict(r) for r in by_model]},
                "drift": drift}
    finally:
        conn.close()


# ── risk history + what-changed (recorded analyses only) ──

@router.get("/ls/borrowers/{bid}/risk-history")
def risk_history(bid: str, authorization: Optional[str] = Header(default=None),
                 x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "analysis.read")
    conn = _DB()
    try:
        if not conn.execute("SELECT 1 FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone():
            raise HTTPException(404, "Borrower not found")
        rows = [dict(r) for r in conn.execute(
            "SELECT id, model_version, risk_score, risk_level, fraud_score, fraud_risk,"
            " trust_score, confidence, decision, ml_score, risk_factors, created_at"
            " FROM ls_analyses WHERE borrower_id=? ORDER BY id", (bid,)).fetchall()]
        for r in rows:
            try:
                r["factors"] = json.loads(r.pop("risk_factors") or "[]")
            except Exception:
                r["factors"] = []
        out: dict = {"borrower_id": bid, "snapshots": rows, "what_changed": None}
        if len(rows) >= 2:
            a, b = rows[-2], rows[-1]
            fa = {f.get("code"): f for f in (a.get("factors") or [])}
            fb = {f.get("code"): f for f in (b.get("factors") or [])}
            deltas = []
            for code, f2 in fb.items():
                f1 = fa.get(code, {})
                d = round((f2.get("score") or 0) - (f1.get("score") or 0), 1)
                if abs(d) >= 1:
                    deltas.append({"code": code, "title": f2.get("title", code),
                                   "before": f1.get("score"), "after": f2.get("score"),
                                   "delta": d})
            deltas.sort(key=lambda x: -abs(x["delta"]))
            out["what_changed"] = {
                "from_analysis": a["id"], "to_analysis": b["id"],
                "risk": {"before": a["risk_score"], "after": b["risk_score"],
                         "delta": round((b["risk_score"] or 0) - (a["risk_score"] or 0), 1)},
                "trust": {"before": a["trust_score"], "after": b["trust_score"]},
                "decision": {"before": a.get("decision"), "after": b.get("decision")},
                "top_factor_moves": deltas[:5],
            }
        return out
    finally:
        conn.close()


# ── early warnings (real signals only) ──

@router.get("/ls/intel/warnings")
def early_warnings(authorization: Optional[str] = Header(default=None),
                   x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "analysis.read")
    conn = _DB()
    try:
        out: list[dict] = []
        # 1. missed / late installments (materialized schedule state)
        for r in conn.execute(
                "SELECT s.loan_id, s.n, s.due_date, s.total_due, s.paid, s.status, l.borrower_id,"
                " b.name FROM ls_schedule s JOIN ls_loans l ON l.id=s.loan_id "
                "JOIN ls_borrowers b ON b.borrower_id=l.borrower_id "
                f"WHERE s.status IN ('MISSED','LATE') AND l.{NOT_SIM} "
                "ORDER BY s.due_date DESC LIMIT 25").fetchall():
            r = dict(r)
            out.append({"type": "MISSED_REPAYMENT" if r["status"] == "MISSED" else "LATE_REPAYMENT",
                        "severity": "high" if r["status"] == "MISSED" else "medium",
                        "borrower_id": r["borrower_id"], "borrower_name": r["name"],
                        "evidence": f"Installment {r['n']} of loan #{r['loan_id']}: due ₹{r['total_due']:,.0f} "
                                    f"on {r['due_date']}, paid ₹{r['paid']:,.0f}.",
                        "confidence": "observed fact", "link": f"/loans/{r['loan_id']}",
                        "timestamp": r["due_date"]})
        # 2. risk trajectory: >=15pt rise between last two analyses
        traj: dict[str, list] = {}
        for r in conn.execute(
                f"""SELECT a.borrower_id, b.name, a.risk_score, a.id, a.created_at FROM ls_analyses a
                    JOIN ls_borrowers b ON b.borrower_id=a.borrower_id
                    WHERE a.risk_score IS NOT NULL AND b.{NOT_SIM}
                    ORDER BY a.borrower_id, a.id""").fetchall():
            traj.setdefault(r["borrower_id"], []).append(dict(r))
        for bid, seq in traj.items():
            if len(seq) >= 2 and (seq[-1]["risk_score"] or 0) - (seq[-2]["risk_score"] or 0) >= 15:
                out.append({"type": "RISK_DETERIORATION", "severity": "high",
                            "borrower_id": bid, "borrower_name": seq[-1]["name"],
                            "evidence": f"Risk estimate {seq[-2]['risk_score']} → {seq[-1]['risk_score']} "
                                        f"(+{round(seq[-1]['risk_score']-seq[-2]['risk_score'],1)}) between analyses "
                                        f"#{seq[-2]['id']} and #{seq[-1]['id']}.",
                            "confidence": "model comparison", "link": f"/borrower/{bid}",
                            "timestamp": seq[-1]["created_at"]})
        # 3. latest fraud HIGH
        for r in conn.execute(
                f"""SELECT a.borrower_id, b.name, a.fraud_score, a.id, a.created_at FROM ls_analyses a
                    JOIN (SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x
                      ON x.borrower_id=a.borrower_id AND x.m=a.id
                    JOIN ls_borrowers b ON b.borrower_id=a.borrower_id
                    WHERE a.fraud_risk='HIGH' AND b.{NOT_SIM} LIMIT 25""").fetchall():
            r = dict(r)
            out.append({"type": "FRAUD_HIGH", "severity": "high",
                        "borrower_id": r["borrower_id"], "borrower_name": r["name"],
                        "evidence": f"Latest fraud screen HIGH (score {r['fraud_score']}). Review signals before lending.",
                        "confidence": "rules + signals", "link": f"/borrower/{r['borrower_id']}",
                        "timestamp": r["created_at"]})
        return {"warnings": out[:50], "count": len(out[:50])}
    finally:
        conn.close()


# ── portfolio intelligence (pure aggregates, SIM excluded) ──

@router.get("/ls/intel/portfolio")
def portfolio(authorization: Optional[str] = Header(default=None),
              x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "analysis.read")
    conn = _DB()
    try:
        loans = conn.execute(
            """SELECT COUNT(*) n, COALESCE(SUM(principal),0) principal,
                COALESCE(SUM(outstanding_principal),0) outstanding, COALESCE(SUM(total_paid),0) repaid,
                SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) active,
                SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) completed,
                SUM(CASE WHEN status='DEFAULTED' THEN 1 ELSE 0 END) defaulted
                FROM ls_loans WHERE borrower_id NOT LIKE 'SIM-%'""").fetchone()
        by_risk = conn.execute(
            """SELECT a.risk_level, COUNT(*) c, COALESCE(SUM(l.outstanding_principal),0) exposure FROM ls_loans l
                JOIN (SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x
                  ON x.borrower_id=l.borrower_id
                JOIN ls_analyses a ON a.id=x.m
                WHERE l.status='ACTIVE' AND l.borrower_id NOT LIKE 'SIM-%'
                GROUP BY a.risk_level""").fetchall()
        sched = conn.execute(
            "SELECT s.status AS status, COUNT(*) c FROM ls_schedule s JOIN ls_loans l ON l.id=s.loan_id "
            "WHERE l.borrower_id NOT LIKE 'SIM-%' GROUP BY s.status").fetchall()
        reqs = conn.execute(
            "SELECT status, COUNT(*) c FROM ls_loan_requests r JOIN ls_borrowers b ON b.borrower_id=r.borrower_id "
            "WHERE b.borrower_id NOT LIKE 'SIM-%' GROUP BY status").fetchall()
        return {"loans": dict(loans),
                "active_exposure_by_risk": [dict(r) for r in by_risk],
                "schedule_status": {r["status"]: r["c"] for r in sched},
                "requests_by_status": {r["status"]: r["c"] for r in reqs}}
    finally:
        conn.close()
