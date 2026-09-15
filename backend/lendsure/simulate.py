"""Controlled Simulation Center: scripted scenarios that execute the REAL
backend services (analysis, requests, approvals, loans, repayments, docs,
graph) against synthetic borrowers namespaced SIM-*. Every record is
flagged SIMULATION and excluded from portfolio/production aggregates.
Cleanup wipes the SIM namespace. Nothing here fabricates outcomes — each
step result comes from the actual service call."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ls", tags=["simulation"])

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


def _actor(authorization: Optional[str], x_api_key: Optional[str] = None) -> str:
    from .api import actor_of
    return actor_of(authorization, x_api_key)


class ScenarioIn(BaseModel):
    scenario: str = Field(pattern="^(healthy_approval|high_risk_review|missed_repayment|doc_mismatch|network_risk)$")


def _clone_borrower(conn, template_bid: str, tag: str, tweaks: dict | None = None) -> str:
    """Copy a real borrower row + financials into the SIM namespace."""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(ls_borrowers)").fetchall()]
    src = conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?", (template_bid,)).fetchone()
    if not src:
        raise HTTPException(422, f"template borrower {template_bid} not found")
    src = dict(src)
    bid = f"SIM-{tag}-{int(time.time()) % 100000:05d}"
    vals = {}
    for c in cols:
        if c == "borrower_id":
            vals[c] = bid
        elif c == "name":
            vals[c] = f"Sim {src['name'].split()[0]} [{tag}]"
        elif c == "created_at":
            vals[c] = now()
        else:
            vals[c] = src.get(c)
    for k, v in (tweaks or {}).items():
        if k in vals:
            vals[k] = v
    conn.execute(f"INSERT INTO ls_borrowers ({','.join(vals)}) VALUES ({','.join('?' * len(vals))})",
                 [vals[c] for c in vals])
    for f in conn.execute("SELECT * FROM ls_financials WHERE borrower_id=? ORDER BY month",
                          (template_bid,)).fetchall():
        f = dict(f)
        conn.execute("INSERT INTO ls_financials (borrower_id,month,label,income,expenses,debt,"
                     "transactions,bounced,disputed) VALUES (?,?,?,?,?,?,?,?,?)",
                     (bid, f["month"], f["label"], f["income"], f["expenses"], f["debt"],
                      f["transactions"], f["bounced"], f["disputed"]))
    from .notify import audit as _audit_log
    _audit_log(conn, bid, None, "simulator", "simulation_created",
               {"template": template_bid, "scenario": tag})
    return bid


def _analyze(conn, bid: str, actor: str) -> dict:
    from .engines import full_analysis
    from .api import cfg_all, _persist_analysis, merge_perf
    from .intel import log_prediction
    b = dict(conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone())
    b = merge_perf(conn, bid, b)
    snaps = [dict(r) for r in conn.execute(
        "SELECT * FROM ls_financials WHERE borrower_id=? ORDER BY month", (bid,))]
    docs = [dict(r) for r in conn.execute("SELECT * FROM ls_documents WHERE borrower_id=?", (bid,))]
    res = full_analysis(b, snaps, docs, False, cfg_all(conn))
    aid = _persist_analysis(conn, bid, res, actor)
    log_prediction(conn, bid, aid, res.get("model_version", ""), res.get("ml_proba"))
    return {"analysis_id": aid, **{k: v for k, v in res.items() if k != "input_snapshot"}}


def _request(conn, bid: str, aid: int, actor: str, amount=None, rate=None, months=None) -> dict:
    b = dict(conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone())
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ls_loan_requests (borrower_id,analysis_id,amount,interest_rate,duration_months,"
        "purpose,status,requested_by,created_at,updated_at) VALUES (?,?,?,?,?,'','DRAFT',?,?,?)",
        (bid, aid, amount or b["requested_amount"], rate or 11.0,
         months or b["tenure_months"] or 12, actor, now(), now()))
    rid = cur.lastrowid
    return dict(conn.execute("SELECT * FROM ls_loan_requests WHERE id=?", (rid,)).fetchone())


def _template(conn, want: str) -> str:
    """A real borrower whose latest analysis matches the wanted risk level."""
    r = conn.execute(
        """SELECT a.borrower_id FROM ls_analyses a JOIN
           (SELECT borrower_id, MAX(id) m FROM ls_analyses GROUP BY borrower_id) x
           ON x.borrower_id=a.borrower_id AND x.m=a.id
           WHERE a.risk_level=? AND a.borrower_id NOT LIKE 'SIM-%' LIMIT 1""", (want,)).fetchone()
    if not r:
        raise HTTPException(422, f"no {want}-risk template borrower available")
    return r["borrower_id"]


def _run(conn, actor: str, scenario: str) -> dict:
    from .loans import _transition, _approve_txn, refresh_loan_state
    from .jobs import enqueue
    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str = "", link: str = ""):
        steps.append({"step": name, "ok": ok, "detail": detail, "link": link})
        if not ok:
            raise RuntimeError(f"scenario step failed: {name} — {detail}")

    if scenario == "healthy_approval":
        bid = _clone_borrower(conn, _template(conn, "LOW"), "healthy")
        step("REGISTER (SIMULATION)", True, f"borrower {bid} cloned from a low-risk profile", f"/borrower/{bid}")
        a = _analyze(conn, bid, actor)
        step("RISK ANALYSIS", True,
             f"trust {a['trust']['trust_score']} · risk {a['risk']['risk_level']} → {a['recommendation']['decision']}",
             f"/borrower/{bid}")
        req = _request(conn, bid, a["analysis_id"], actor)
        req = _transition(conn, req, "submit", actor)
        step("LOAN REQUEST", True, f"request #{req['id']} SUBMITTED ₹{req['amount']:,.0f}", f"/loan-requests/{req['id']}")
        req, loan_id, payment = _approve_txn(conn, req, req["amount"], req["interest_rate"],
                                             req["duration_months"], "sim: healthy approval", actor)
        loan = refresh_loan_state(conn, loan_id, actor)
        step("APPROVAL + DISBURSAL", True, f"loan #{loan_id}, EMI ₹{payment:,.0f}", f"/loans/{loan_id}")

    elif scenario == "high_risk_review":
        bid = _clone_borrower(conn, _template(conn, "HIGH"), "highrisk")
        step("REGISTER (SIMULATION)", True, f"borrower {bid} cloned from a high-risk profile", f"/borrower/{bid}")
        a = _analyze(conn, bid, actor)
        step("RISK ANALYSIS", True,
             f"risk {a['risk']['risk_level']} ({a['risk']['risk_score']}) → engine {a['recommendation']['decision']}",
             f"/borrower/{bid}")
        req = _request(conn, bid, a["analysis_id"], actor)
        req = _transition(conn, req, "submit", actor)
        req = _transition(conn, req, "reject", actor, "sim: debt burden exceeds policy")
        conn.execute("UPDATE ls_loan_requests SET reviewer=?, review_note=?, decided_at=? WHERE id=?",
                     (actor, "sim: debt burden exceeds policy", now(), req["id"]))
        step("LENDER REJECTION", True, f"request #{req['id']} REJECTED with reason", f"/loan-requests/{req['id']}")

    elif scenario == "missed_repayment":
        bid = _clone_borrower(conn, _template(conn, "LOW"), "missed")
        step("REGISTER (SIMULATION)", True, f"borrower {bid}", f"/borrower/{bid}")
        a0 = _analyze(conn, bid, actor)
        before = a0["risk"]["risk_score"]
        req = _request(conn, bid, a0["analysis_id"], actor, months=3)
        req = _transition(conn, req, "submit", actor)
        backdate = (datetime.utcnow() - timedelta(days=75)).date().isoformat()
        req, loan_id, payment = _approve_txn(conn, req, req["amount"], req["interest_rate"],
                                             req["duration_months"], "sim: backdated 75d (SIMULATION only)",
                                             actor, disbursed_on=backdate)
        loan = refresh_loan_state(conn, loan_id, actor)
        missed = sum(1 for s in loan["schedule"] if s["status"] == "MISSED")
        step("BACKDATED LOAN (SIMULATION)", True,
             f"loan #{loan_id} disbursed {backdate} → {missed} installment(s) MISSED", f"/loans/{loan_id}")
        a1 = _analyze(conn, bid, actor)
        step("RISK RECALCULATION", True,
             f"risk {before} → {a1['risk']['risk_score']} after missed repayment(s)", f"/borrower/{bid}")

    elif scenario == "doc_mismatch":
        bid = _clone_borrower(conn, _template(conn, "LOW"), "docmismatch")
        step("REGISTER (SIMULATION)", True, f"borrower {bid}", f"/borrower/{bid}")
        cur = conn.cursor()
        for i in (1, 2):
            cur.execute(
                "INSERT INTO ls_documents (borrower_id,doc_type,file_name,status,pipeline_status,content_hash,created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (bid, "identity", "sim_aadhaar.pdf", "needs_review", "PENDING", "", now()))
            did = cur.lastrowid
            enqueue(conn, "document.verify", "document", did, {"doc_id": did},
                    idempotency_key=f"sim-docverify-{did}")
        conn.commit()
        # wait for the worker (up to 30s)
        final = "PENDING"
        for _ in range(30):
            time.sleep(1)
            st = conn.execute("SELECT pipeline_status FROM ls_documents WHERE borrower_id=? ORDER BY id DESC LIMIT 1",
                              (bid,)).fetchone()["pipeline_status"]
            if st != "PENDING" and st != "PROCESSING":
                final = st
                break
        step("DUPLICATE DOCUMENT CHECK", final in ("REVIEW", "FAILED", "VERIFIED"), f"second identical file → pipeline {final}",
             f"/borrower/{bid}?tab=documents")

    elif scenario == "network_risk":
        t = _template(conn, "LOW")
        b1 = _clone_borrower(conn, t, "netA")
        b2 = _clone_borrower(conn, t, "netB")
        conn.execute("UPDATE ls_borrowers SET phone=? WHERE borrower_id IN (?,?)",
                     ("+91-90000-SIM01", b1, b2))
        from .notify import emit
        for b in (b1, b2):
            emit(conn, "BorrowerAttributeChanged", "borrower", b, actor,
                 {"field": "phone", "old": "", "new": "+91-90000-SIM01"})
        step("SHARED PHONE (SIMULATION)", True, f"{b1} ↔ {b2} share +91-90000-SIM01", f"/borrower/{b1}?tab=network")
        summ = conn.execute("SELECT COUNT(*) c FROM ls_borrowers WHERE phone='+91-90000-SIM01'").fetchone()["c"]
        step("GRAPH LINK", summ == 2, f"{summ} borrowers share the identifier (exposure, not fraud)",
             f"/borrower/{b1}?tab=network")

    conn.commit()
    return {"scenario": scenario, "steps": steps,
            "note": "All records are SIMULATION-flagged (SIM-*) and excluded from portfolio metrics."}


@router.post("/admin/simulate/scenario")
def run_scenario(body: ScenarioIn, authorization: Optional[str] = Header(default=None),
                 x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "simulation.run")
    conn = _DB()
    try:
        return _run(conn, actor, body.scenario)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.get("/admin/simulate/scenarios")
def list_scenarios(authorization: Optional[str] = Header(default=None),
                   x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "simulation.run")
    return [
        {"id": "healthy_approval", "title": "Healthy Approval",
         "desc": "Strong borrower → analysis → request → approval → disbursed loan with schedule."},
        {"id": "high_risk_review", "title": "High-Risk Review → Reject",
         "desc": "High-debt borrower → analysis → request → lender rejection with reason."},
        {"id": "missed_repayment", "title": "Missed Repayment → Risk Recalc",
         "desc": "Backdated SIM loan goes MISSED, then risk is recalculated showing the delta."},
        {"id": "doc_mismatch", "title": "Document Mismatch → Review",
         "desc": "Duplicate identity file triggers the verification worker → REVIEW."},
        {"id": "network_risk", "title": "Shared Identifier → Graph Link",
         "desc": "Two SIM borrowers share one phone; graph shows exposure (not fraud)."},
    ]


@router.post("/admin/simulate/cleanup")
def cleanup(authorization: Optional[str] = Header(default=None),
            x_api_key: Optional[str] = Header(default=None)):
    """Wipe the SIM namespace. Lender-only (destructive). Job history rows are kept."""
    _need(authorization, x_api_key, "jobs.manage")
    conn = _DB()
    try:
        counts: dict[str, int] = {}

        def wipe(table: str, col: str = "borrower_id"):
            cur = conn.execute(f"DELETE FROM {table} WHERE {col} LIKE 'SIM-%'")
            counts[table] = (counts.get(table, 0) + cur.rowcount)

        wipe("ls_financials")
        # documents + files
        dids = [r["id"] for r in conn.execute(
            "SELECT id FROM ls_documents WHERE borrower_id LIKE 'SIM-%'").fetchall()]
        if dids:
            q = ",".join("?" * len(dids))
            conn.execute(f"DELETE FROM ls_doc_files WHERE doc_id IN ({q})", dids)
            counts["ls_doc_files"] = len(dids)
        wipe("ls_documents")
        # analyses + children
        aids = [r["id"] for r in conn.execute(
            "SELECT id FROM ls_analyses WHERE borrower_id LIKE 'SIM-%'").fetchall()]
        if aids:
            q = ",".join("?" * len(aids))
            for t in ("ls_recommendations", "ls_evidence"):
                col = "analysis_id"
                counts[t] = conn.execute(f"DELETE FROM {t} WHERE {col} IN ({q})", aids).rowcount
        wipe("ls_analyses")
        # requests + loans + schedules + repayments
        rids = [r["id"] for r in conn.execute(
            "SELECT id FROM ls_loan_requests WHERE borrower_id LIKE 'SIM-%'").fetchall()]
        lids = [r["id"] for r in conn.execute(
            "SELECT id FROM ls_loans WHERE borrower_id LIKE 'SIM-%'").fetchall()]
        if lids:
            q = ",".join("?" * len(lids))
            counts["ls_schedule"] = conn.execute(f"DELETE FROM ls_schedule WHERE loan_id IN ({q})", lids).rowcount
            counts["ls_repayments"] = conn.execute(f"DELETE FROM ls_repayments WHERE loan_id IN ({q})", lids).rowcount
        wipe("ls_loans")
        wipe("ls_loan_requests")
        wipe("ls_borrower_perf")
        wipe("ls_predictions")
        # events + audit + cases tied to SIM entities
        counts["ls_events"] = conn.execute(
            "DELETE FROM ls_events WHERE entity_id LIKE 'SIM-%'").rowcount
        counts["ls_audit"] = conn.execute(
            "DELETE FROM ls_audit WHERE borrower_id LIKE 'SIM-%'").rowcount
        conn.execute("DELETE FROM ls_cases WHERE borrower_id LIKE 'SIM-%'")
        counts["ls_cases"] = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
        return {"ok": True, "deleted": counts}
    finally:
        conn.close()
