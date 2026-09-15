"""Loan lifecycle: requests -> review -> approval -> loan + schedule -> repayments.

State machine (requests):
  DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED -> (loan created)
                                    -> REJECTED | MORE_INFORMATION_REQUIRED
  MORE_INFORMATION_REQUIRED -> SUBMITTED (resubmit) | WITHDRAWN
  DRAFT | SUBMITTED | UNDER_REVIEW -> WITHDRAWN
Terminal: APPROVED, REJECTED, WITHDRAWN, EXPIRED.

Approval creates the loan + full amortization schedule in ONE transaction.
Repayments apply FIFO across schedules, are idempotent, and update the
borrower's performance counters (which genuinely feed the next risk
analysis). Every transition emits a domain event, an audit row and a
notification. Money math is deterministic and rounded to paise.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .engines import emi

router = APIRouter(prefix="/api/ls", tags=["loans"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def now() -> str:
    return datetime.utcnow().isoformat()


def today() -> str:
    return datetime.utcnow().date().isoformat()


def _actor(authorization: Optional[str], x_api_key: Optional[str] = None) -> str:
    from .api import actor_of
    return actor_of(authorization, x_api_key)


def _need(authorization: Optional[str], x_api_key: Optional[str], *perms: str) -> str:
    from .api import require_perm
    return require_perm(authorization, x_api_key, *perms)


# ── state machine ──

TRANSITIONS = {
    "DRAFT": {"submit": "SUBMITTED", "withdraw": "WITHDRAWN"},
    "SUBMITTED": {"start_review": "UNDER_REVIEW", "approve": "APPROVED",
                  "reject": "REJECTED", "request_info": "MORE_INFORMATION_REQUIRED",
                  "withdraw": "WITHDRAWN"},
    "UNDER_REVIEW": {"approve": "APPROVED", "reject": "REJECTED",
                     "request_info": "MORE_INFORMATION_REQUIRED", "withdraw": "WITHDRAWN"},
    "MORE_INFORMATION_REQUIRED": {"submit": "SUBMITTED", "withdraw": "WITHDRAWN"},
}
TERMINAL = {"APPROVED", "REJECTED", "WITHDRAWN", "EXPIRED"}

EVENT_FOR = {
    ("DRAFT", "SUBMITTED"): "LoanRequestSubmitted",
    ("SUBMITTED", "UNDER_REVIEW"): "LoanRequestReviewStarted",
    ("*", "APPROVED"): "LoanApproved",
    ("*", "REJECTED"): "LoanRejected",
    ("*", "MORE_INFORMATION_REQUIRED"): "InformationRequested",
    ("*", "WITHDRAWN"): "LoanRequestWithdrawn",
}


def _transition(conn, req: dict, action: str, actor: str, note: str = "") -> dict:
    allowed = TRANSITIONS.get(req["status"], {})
    if action not in allowed:
        raise HTTPException(409, f"Cannot '{action}' a request in status {req['status']}")
    to = allowed[action]
    conn.execute("UPDATE ls_loan_requests SET status=?, updated_at=? WHERE id=?",
                 (to, now(), req["id"]))
    from .notify import emit, audit
    ev = EVENT_FOR.get((req["status"], to)) or EVENT_FOR.get(("*", to), "LoanRequestUpdated")
    emit(conn, ev, "loan_request", req["id"], actor,
         {"from": req["status"], "to": to, "note": note,
          "borrower_id": req["borrower_id"], "amount": req["amount"]})
    audit(conn, req["borrower_id"], req.get("analysis_id"), actor,
          f"loan_request_{action}", {"request_id": req["id"], "from": req["status"], "to": to, "note": note})
    req = dict(req)
    req["status"] = to
    return req


def _notify_both(conn, kind: str, title: str, body: str, link: str):
    from .notify import notify
    notify(conn, "role:lender", kind, title, body, link)
    notify(conn, "role:guest", kind, title, body, link)


# ── money helpers ──

def _add_months(date_str: str, n: int) -> str:
    y, m, d = map(int, date_str.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    import calendar
    d = min(d, calendar.monthrange(y, m)[1])
    return f"{y:04d}-{m:02d}-{d:02d}"


def build_schedule(principal: float, annual_rate: float, months: int, start_date: str) -> list[dict]:
    payment = emi(principal, annual_rate, months)
    r = annual_rate / 1200.0
    bal = round(principal, 2)
    rows = []
    for n in range(1, months + 1):
        interest = round(bal * r, 2)
        princ = round(payment - interest, 2) if n < months else bal
        if n == months:
            princ = bal
        bal = round(bal - princ, 2)
        rows.append({"n": n, "due_date": _add_months(start_date, n),
                     "principal": princ, "interest": interest,
                     "total_due": round(princ + interest, 2)})
    return rows


def refresh_loan_state(conn, loan_id: int, actor: str = "system") -> dict:
    """Recompute schedule statuses, loan aggregates and borrower perf.
    Materializes LATE/MISSED transitions with events (idempotent per status)."""
    from .notify import emit, notify
    loan = conn.execute("SELECT * FROM ls_loans WHERE id=?", (loan_id,)).fetchone()
    if not loan:
        raise HTTPException(404, "Loan not found")
    loan = dict(loan)
    tdy = today()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM ls_schedule WHERE loan_id=? ORDER BY n", (loan_id,)).fetchall()]
    for s in rows:
        if s["status"] == "PAID":
            continue
        prev = s["status"]
        paid, due = s["paid"], s["total_due"]
        if paid >= due - 0.005:
            new, paid_at = "PAID", now()
            conn.execute("UPDATE ls_schedule SET status='PAID', paid_at=? WHERE id=?",
                         (paid_at, s["id"]))
        elif s["due_date"] < tdy:
            new = "LATE" if paid > 0 else "MISSED"
            conn.execute("UPDATE ls_schedule SET status=? WHERE id=?", (new, s["id"]))
            if new != prev and new in ("LATE", "MISSED"):
                emit(conn, "RepaymentMissed" if new == "MISSED" else "RepaymentLate",
                     "schedule", s["id"], actor,
                     {"loan_id": loan_id, "n": s["n"], "due": due, "paid": paid,
                      "borrower_id": loan["borrower_id"]})
                notify(conn, "role:lender", "repayment_missed" if new == "MISSED" else "repayment_late",
                       f"{'Missed' if new == 'MISSED' else 'Late'} repayment — {loan['borrower_id']}",
                       f"Installment {s['n']} of loan #{loan_id}: due ₹{due:,.0f}, paid ₹{paid:,.0f}.",
                       f"/loans/{loan_id}")
        elif s["due_date"] <= _add_months(tdy, 1):
            # due within ~30 days -> DUE, else UPCOMING
            new = "DUE"
            if new != prev:
                conn.execute("UPDATE ls_schedule SET status=? WHERE id=?", (new, s["id"]))
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM ls_schedule WHERE loan_id=? ORDER BY n", (loan_id,)).fetchall()]
    princ_paid = sum(max(0.0, min(r["paid"], r["principal"])) for r in rows)
    total_paid = sum(r["paid"] for r in rows)
    outstanding = round(max(0.0, loan["principal"] - princ_paid), 2)
    missed = sum(1 for r in rows if r["status"] == "MISSED")
    status = loan["status"]
    if all(r["status"] == "PAID" for r in rows) and rows:
        if status != "COMPLETED":
            status = "COMPLETED"
            emit(conn, "LoanCompleted", "loan", loan_id, actor,
                 {"borrower_id": loan["borrower_id"]})
            notify(conn, "role:lender", "loan_completed",
                   f"Loan #{loan_id} fully repaid", "", f"/loans/{loan_id}")
    elif missed >= 3 and status == "ACTIVE":
        status = "DEFAULTED"
        emit(conn, "LoanDefaulted", "loan", loan_id, actor,
             {"borrower_id": loan["borrower_id"], "missed": missed})
        notify(conn, "role:lender", "loan_defaulted",
               f"Loan #{loan_id} defaulted ({missed} missed)",
               f"Borrower {loan['borrower_id']} missed {missed} installments.", f"/loans/{loan_id}")
    conn.execute("UPDATE ls_loans SET outstanding_principal=?, total_paid=?, status=? WHERE id=?",
                 (outstanding, round(total_paid, 2), status, loan_id))
    # borrower performance (drives the next risk analysis — real feedback loop)
    on_time = sum(1 for r in rows
                  if r["status"] == "PAID" and (r["paid_at"] or "")[:10] <= _add_months(r["due_date"], 0)
                  or (r["status"] == "PAID" and (r["paid_at"] or "")[:10] <= r["due_date"]))
    completed = 1 if status == "COMPLETED" else 0
    conn.execute(
        "INSERT INTO ls_borrower_perf (borrower_id,loans_completed,repayments_on_time,repayments_missed,amount_repaid,updated_at)"
        " VALUES (?,?,?,?,?,?) ON CONFLICT(borrower_id) DO UPDATE SET loans_completed=?, repayments_on_time=?,"
        " repayments_missed=?, amount_repaid=?, updated_at=?",
        (loan["borrower_id"], completed, on_time, missed, round(total_paid, 2), now(),
         completed, on_time, missed, round(total_paid, 2), now()))
    conn.commit()
    loan = dict(conn.execute("SELECT * FROM ls_loans WHERE id=?", (loan_id,)).fetchone())
    loan["schedule"] = rows
    return loan


# ── request models ──

class RequestIn(BaseModel):
    borrower_id: str = Field(min_length=1, max_length=32)
    analysis_id: Optional[int] = None
    amount: float = Field(gt=0, le=100_000_00)
    interest_rate: float = Field(ge=0, le=60)
    duration_months: int = Field(ge=1, le=84)
    purpose: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=120)
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT|APPROVE_WITH_CONDITIONS)$")
    note: str = Field(default="", max_length=1000)


class InfoIn(BaseModel):
    note: str = Field(min_length=5, max_length=1000)


class ApproveIn(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0, le=100_000_00)
    interest_rate: Optional[float] = Field(default=None, ge=0, le=60)
    duration_months: Optional[int] = Field(default=None, ge=1, le=84)
    note: str = Field(default="", max_length=1000)


class RepayIn(BaseModel):
    schedule_id: Optional[int] = None
    amount: float = Field(gt=0, le=100_000_00)
    method: str = Field(default="manual", max_length=40)
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class CaseIn(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    kind: str = Field(default="investigation", max_length=60)
    borrower_id: str = Field(default="", max_length=32)
    evidence: dict = Field(default_factory=dict)


# ── loan requests ──

@router.post("/loan-requests")
def create_request(body: RequestIn, authorization: Optional[str] = Header(default=None),
                   x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "loan_request.create")
    conn = _DB()
    try:
        b = conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?",
                         (body.borrower_id,)).fetchone()
        if not b:
            raise HTTPException(404, "Borrower not found")
        b = dict(b)
        if body.idempotency_key:
            row = conn.execute("SELECT * FROM ls_loan_requests WHERE idempotency_key=?",
                               (body.idempotency_key,)).fetchone()
            if row:
                return {**dict(row), "duplicate": True}
        # Server-minted when the client omits one: persisted + returned so a
        # retry can reuse it instead of minting a duplicate request.
        idem = body.idempotency_key or f"req-{uuid.uuid4().hex[:16]}"
        aid = body.analysis_id
        if aid is None:
            r = conn.execute("SELECT id FROM ls_analyses WHERE borrower_id=? ORDER BY id DESC LIMIT 1",
                             (body.borrower_id,)).fetchone()
            aid = r["id"] if r else None
        # confirmed contact identifiers update the profile (audited, feeds the graph)
        from .notify import emit, audit
        for field in ("phone", "email"):
            val = (getattr(body, field) or "").strip()
            if val and not (b.get(field) or "").strip():
                conn.execute(f"UPDATE ls_borrowers SET {field}=? WHERE borrower_id=?",
                             (val, body.borrower_id))
                emit(conn, "BorrowerAttributeChanged", "borrower", body.borrower_id, actor,
                     {"field": field, "old": "", "new": val})
                audit(conn, body.borrower_id, aid, actor, "borrower_attribute_changed",
                      {"field": field, "value": val})
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ls_loan_requests (borrower_id,analysis_id,amount,interest_rate,duration_months,"
            "purpose,status,idempotency_key,requested_by,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,'DRAFT',?,?,?,?)",
            (body.borrower_id, aid, body.amount, body.interest_rate, body.duration_months,
             body.purpose, idem, _actor(authorization, x_api_key), now(), now()))
        rid = cur.lastrowid
        emit(conn, "LoanRequestCreated", "loan_request", rid, _actor(authorization, x_api_key),
             {"borrower_id": body.borrower_id, "amount": body.amount})
        audit(conn, body.borrower_id, aid, _actor(authorization, x_api_key), "loan_request_created",
              {"request_id": rid, "amount": body.amount})
        conn.commit()
        return dict(conn.execute("SELECT * FROM ls_loan_requests WHERE id=?", (rid,)).fetchone())
    finally:
        conn.close()


@router.get("/loan-requests")
def list_requests(status: str = "", borrower_id: str = "", limit: int = 50,
                  authorization: Optional[str] = Header(default=None),
                  x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "loan.read")
    conn = _DB()
    try:
        q = ("SELECT r.*, b.name AS borrower_name, b.city FROM ls_loan_requests r "
             "LEFT JOIN ls_borrowers b ON b.borrower_id=r.borrower_id WHERE 1=1")
        params: list = []
        if status:
            q += " AND r.status=?"
            params.append(status.upper())
        if borrower_id:
            q += " AND r.borrower_id=?"
            params.append(borrower_id)
        q += " ORDER BY r.id DESC LIMIT ?"
        params.append(min(limit, 200))
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        agg = conn.execute("SELECT status, COUNT(*) c FROM ls_loan_requests GROUP BY status").fetchall()
        return {"rows": rows, "by_status": {r["status"]: r["c"] for r in agg}}
    finally:
        conn.close()


@router.get("/loan-requests/{rid}")
def get_request(rid: int, authorization: Optional[str] = Header(default=None),
                x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "loan.read")
    from .notify import emit  # noqa
    conn = _DB()
    try:
        r = conn.execute(
            "SELECT r.*, b.name AS borrower_name, b.city FROM ls_loan_requests r "
            "LEFT JOIN ls_borrowers b ON b.borrower_id=r.borrower_id WHERE r.id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "Loan request not found")
        out = dict(r)
        out["timeline"] = [dict(e) for e in conn.execute(
            "SELECT * FROM ls_events WHERE entity='loan_request' AND entity_id=? ORDER BY id",
            (str(rid),)).fetchall()]
        loan = conn.execute("SELECT id FROM ls_loans WHERE request_id=?", (rid,)).fetchone()
        out["loan_id"] = loan["id"] if loan else None
        return out
    finally:
        conn.close()


def _get_req(conn, rid: int) -> dict:
    r = conn.execute("SELECT * FROM ls_loan_requests WHERE id=?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "Loan request not found")
    return dict(r)


@router.post("/loan-requests/{rid}/submit")
def submit_request(rid: int, authorization: Optional[str] = Header(default=None),
                   x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "loan_request.create")
    conn = _DB()
    try:
        req = _transition(conn, _get_req(conn, rid), "submit", actor)
        _notify_both(conn, "loan_submitted", f"Loan request #{rid} submitted",
                     f"{req['borrower_id']} asks ₹{req['amount']:,.0f} @ {req['interest_rate']}% × {req['duration_months']}m.",
                     f"/loan-requests/{rid}")
        conn.commit()
        return req
    finally:
        conn.close()


@router.post("/loan-requests/{rid}/withdraw")
def withdraw_request(rid: int, authorization: Optional[str] = Header(default=None),
                     x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "loan_request.create")
    conn = _DB()
    try:
        req = _transition(conn, _get_req(conn, rid), "withdraw", actor)
        conn.commit()
        return req
    finally:
        conn.close()


@router.post("/loan-requests/{rid}/review")
def start_review(rid: int, authorization: Optional[str] = Header(default=None),
                 x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "loan_request.decide")
    conn = _DB()
    try:
        req = _transition(conn, _get_req(conn, rid), "start_review", actor)
        conn.commit()
        return req
    finally:
        conn.close()


@router.post("/loan-requests/{rid}/request-info")
def request_info(rid: int, body: InfoIn, authorization: Optional[str] = Header(default=None),
                 x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "loan_request.decide")
    conn = _DB()
    try:
        req = _transition(conn, _get_req(conn, rid), "request_info", actor, body.note)
        _notify_both(conn, "info_requested", f"More information needed — request #{rid}",
                     body.note, f"/loan-requests/{rid}")
        conn.commit()
        return req
    finally:
        conn.close()


@router.post("/loan-requests/{rid}/reject")
def reject_request(rid: int, body: InfoIn, authorization: Optional[str] = Header(default=None),
                   x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "loan_request.decide")
    conn = _DB()
    try:
        req = _get_req(conn, rid)
        req = _transition(conn, req, "reject", actor, body.note)
        conn.execute("UPDATE ls_loan_requests SET reviewer=?, review_note=?, decided_at=? WHERE id=?",
                     (actor, body.note, now(), rid))
        _notify_both(conn, "loan_rejected", f"Loan request #{rid} rejected", body.note,
                     f"/loan-requests/{rid}")
        conn.commit()
        return dict(conn.execute("SELECT * FROM ls_loan_requests WHERE id=?", (rid,)).fetchone())
    finally:
        conn.close()


@router.post("/loan-requests/{rid}/approve")
def approve_request(rid: int, body: ApproveIn, authorization: Optional[str] = Header(default=None),
                    x_api_key: Optional[str] = Header(default=None)):
    """Approve AND disburse: creates the loan + full schedule atomically.
    Idempotent: re-approving an APPROVED request returns the existing loan."""
    actor = _need(authorization, x_api_key, "loan_request.decide")
    conn = _DB()
    try:
        req = _get_req(conn, rid)
        if req["status"] == "APPROVED":
            loan = conn.execute("SELECT * FROM ls_loans WHERE request_id=?", (rid,)).fetchone()
            return {"request": req, "loan": dict(loan) if loan else None, "duplicate": True}
        amount = body.amount or req["amount"]
        rate = body.interest_rate if body.interest_rate is not None else req["interest_rate"]
        months = body.duration_months or req["duration_months"]
        if not (0 < amount <= 100_000_00 and 0 <= rate <= 60 and 1 <= months <= 84):
            raise HTTPException(422, "Adjusted terms out of bounds")
        req, loan_id, payment = _approve_txn(conn, req, amount, rate, months, body.note, actor)
        conn.commit()
        loan = refresh_loan_state(conn, loan_id, actor)
        return {"request": dict(conn.execute("SELECT * FROM ls_loan_requests WHERE id=?", (rid,)).fetchone()),
                "loan": loan}
    finally:
        conn.close()


def _approve_txn(conn, req: dict, amount: float, rate: float, months: int,
                 note: str, actor: str, disbursed_on: str | None = None) -> tuple[dict, int, float]:
    """Shared approve-and-disburse transaction (endpoint + simulator).
    disbursed_on backdating is simulator-only and always SIM-flagged."""
    from .notify import emit, audit
    req = _transition(conn, req, "approve", actor, note)
    payment = emi(amount, rate, months)
    disb = disbursed_on or today()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ls_loans (request_id,borrower_id,principal,interest_rate,duration_months,"
        "emi,disbursed_at,status,outstanding_principal,total_paid,created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (req["id"], req["borrower_id"], amount, rate, months, payment, disb, "ACTIVE",
         round(amount, 2), 0.0, now()))
    loan_id = cur.lastrowid
    for s in build_schedule(amount, rate, months, disb):
        cur.execute(
            "INSERT INTO ls_schedule (loan_id,n,due_date,principal,interest,total_due) VALUES (?,?,?,?,?,?)",
            (loan_id, s["n"], s["due_date"], s["principal"], s["interest"], s["total_due"]))
    conn.execute("UPDATE ls_loan_requests SET reviewer=?, review_note=?, decided_at=?,"
                 " amount=?, interest_rate=?, duration_months=? WHERE id=?",
                 (actor, note, now(), amount, rate, months, req["id"]))
    emit(conn, "LoanCreated", "loan", loan_id, actor,
         {"request_id": req["id"], "borrower_id": req["borrower_id"], "principal": amount,
          "emi": payment, "months": months})
    audit(conn, req["borrower_id"], req.get("analysis_id"), actor, "loan_approved_disbursed",
          {"request_id": req["id"], "loan_id": loan_id, "principal": amount, "rate": rate,
           "months": months, "emi": payment, "note": note})
    _notify_both(conn, "loan_approved", f"Loan #{loan_id} approved & disbursed",
                 f"₹{amount:,.0f} @ {rate}% × {months}m — EMI ₹{payment:,.0f} for {req['borrower_id']}.",
                 f"/loans/{loan_id}")
    return req, loan_id, payment


# ── loans & repayments ──

@router.get("/loans")
def list_loans(status: str = "", borrower_id: str = "", limit: int = 50,
               authorization: Optional[str] = Header(default=None),
               x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "loan.read")
    conn = _DB()
    try:
        q = ("SELECT l.*, b.name AS borrower_name FROM ls_loans l "
             "LEFT JOIN ls_borrowers b ON b.borrower_id=l.borrower_id WHERE 1=1")
        params: list = []
        if status:
            q += " AND l.status=?"
            params.append(status.upper())
        if borrower_id:
            q += " AND l.borrower_id=?"
            params.append(borrower_id)
        q += " ORDER BY l.id DESC LIMIT ?"
        params.append(min(limit, 200))
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        agg = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(principal),0) principal, "
            "COALESCE(SUM(outstanding_principal),0) outstanding, COALESCE(SUM(total_paid),0) repaid "
            "FROM ls_loans").fetchone()
        return {"rows": rows, "portfolio": dict(agg)}
    finally:
        conn.close()


@router.get("/loans/{loan_id}")
def get_loan(loan_id: int, authorization: Optional[str] = Header(default=None),
             x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "loan.read")
    conn = _DB()
    try:
        loan = refresh_loan_state(conn, loan_id, _actor(authorization, x_api_key))
        loan["repayments"] = [dict(r) for r in conn.execute(
            "SELECT * FROM ls_repayments WHERE loan_id=? ORDER BY id", (loan_id,)).fetchall()]
        loan["timeline"] = [dict(e) for e in conn.execute(
            "SELECT * FROM ls_events WHERE (entity='loan' AND entity_id=?) OR "
            "(entity='schedule' AND entity_id IN (SELECT id FROM ls_schedule WHERE loan_id=?)) "
            "ORDER BY id", (str(loan_id), loan_id)).fetchall()]
        b = conn.execute("SELECT borrower_id, name, city FROM ls_borrowers WHERE borrower_id=?",
                         (loan["borrower_id"],)).fetchone()
        loan["borrower"] = dict(b) if b else None
        return loan
    finally:
        conn.close()


@router.post("/loans/{loan_id}/repayments")
def record_repayment(loan_id: int, body: RepayIn,
                     authorization: Optional[str] = Header(default=None),
                     x_api_key: Optional[str] = Header(default=None)):
    """Record a repayment. FIFO across unpaid schedules unless schedule_id is
    given. Idempotent via idempotency_key. Transactional."""
    actor = _need(authorization, x_api_key, "repayment.record")
    conn = _DB()
    try:
        if body.idempotency_key:
            row = conn.execute("SELECT * FROM ls_repayments WHERE idempotency_key=?",
                               (body.idempotency_key,)).fetchone()
            if row:
                return {**dict(row), "duplicate": True}
        loan = conn.execute("SELECT * FROM ls_loans WHERE id=?", (loan_id,)).fetchone()
        if not loan:
            raise HTTPException(404, "Loan not found")
        loan = dict(loan)
        if loan["status"] != "ACTIVE":
            raise HTTPException(409, f"Loan is {loan['status']}, not ACTIVE")
        if body.schedule_id:
            targets = [dict(r) for r in conn.execute(
                "SELECT * FROM ls_schedule WHERE id=? AND loan_id=?", (body.schedule_id, loan_id)).fetchall()]
            if not targets:
                raise HTTPException(404, "Schedule installment not found for this loan")
        else:
            targets = [dict(r) for r in conn.execute(
                "SELECT * FROM ls_schedule WHERE loan_id=? AND status!='PAID' ORDER BY n",
                (loan_id,)).fetchall()]
            if not targets:
                raise HTTPException(409, "Nothing due — loan fully paid")
        remaining = round(body.amount, 2)
        applied: list[dict] = []
        cur = conn.cursor()
        for s in targets:
            if remaining <= 0:
                break
            due_left = round(s["total_due"] - s["paid"], 2)
            if due_left <= 0:
                continue
            chunk = min(remaining, due_left)
            conn.execute("UPDATE ls_schedule SET paid=ROUND(paid+?,2) WHERE id=?", (chunk, s["id"]))
            applied.append({"schedule_id": s["id"], "n": s["n"], "applied": chunk})
            remaining = round(remaining - chunk, 2)
        cur.execute(
            "INSERT INTO ls_repayments (loan_id,schedule_id,amount,method,idempotency_key,recorded_by,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (loan_id, targets[0]["id"], body.amount, body.method,
             body.idempotency_key or f"rp-{uuid.uuid4().hex[:12]}", actor, now()))
        rid = cur.lastrowid
        from .notify import emit, audit, notify
        emit(conn, "RepaymentCreated", "repayment", rid, actor,
             {"loan_id": loan_id, "amount": body.amount, "method": body.method,
              "applied": applied, "overpay": remaining, "borrower_id": loan["borrower_id"]})
        audit(conn, loan["borrower_id"], None, actor, "repayment_recorded",
              {"repayment_id": rid, "loan_id": loan_id, "amount": body.amount})
        notify(conn, "role:lender", "repayment_recorded",
               f"Repayment ₹{body.amount:,.0f} — loan #{loan_id}",
               f"{loan['borrower_id']} paid ₹{body.amount:,.0f}" +
               (f" (₹{remaining:,.0f} overpay credit)" if remaining > 0 else "") + ".",
               f"/loans/{loan_id}")
        conn.commit()
        loan = refresh_loan_state(conn, loan_id, actor)
        return {"repayment_id": rid, "applied": applied, "overpay": remaining, "loan": loan}
    finally:
        conn.close()


# ── investigation cases ──

@router.post("/cases")
def create_case(body: CaseIn, authorization: Optional[str] = Header(default=None),
                x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "cases.manage")
    conn = _DB()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ls_cases (title,kind,status,borrower_id,evidence,created_by,created_at)"
            " VALUES (?,?, 'OPEN',?,?,?,?)",
            (body.title, body.kind, body.borrower_id, json.dumps(body.evidence), actor, now()))
        cid = cur.lastrowid
        from .notify import emit, audit
        emit(conn, "CaseCreated", "case", cid, actor,
             {"title": body.title, "kind": body.kind, "borrower_id": body.borrower_id})
        if body.borrower_id:
            audit(conn, body.borrower_id, None, actor, "case_created",
                  {"case_id": cid, "title": body.title})
        conn.commit()
        return dict(conn.execute("SELECT * FROM ls_cases WHERE id=?", (cid,)).fetchone())
    finally:
        conn.close()


@router.get("/cases")
def list_cases(status: str = "", limit: int = 50,
               authorization: Optional[str] = Header(default=None),
               x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "cases.manage", "admin.read")
    conn = _DB()
    try:
        q = "SELECT * FROM ls_cases WHERE 1=1"
        params: list = []
        if status:
            q += " AND status=?"
            params.append(status.upper())
        q += " ORDER BY id DESC LIMIT ?"
        params.append(min(limit, 200))
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()


@router.get("/cases/{cid}")
def get_case(cid: int, authorization: Optional[str] = Header(default=None),
             x_api_key: Optional[str] = Header(default=None)):
    _need(authorization, x_api_key, "cases.manage", "admin.read")
    conn = _DB()
    try:
        c = conn.execute("SELECT * FROM ls_cases WHERE id=?", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Case not found")
        out = dict(c)
        out["timeline"] = [dict(e) for e in conn.execute(
            "SELECT * FROM ls_events WHERE entity='case' AND entity_id=? ORDER BY id",
            (str(cid),)).fetchall()]
        return out
    finally:
        conn.close()


@router.post("/cases/{cid}/resolve")
def resolve_case(cid: int, authorization: Optional[str] = Header(default=None),
                 x_api_key: Optional[str] = Header(default=None)):
    actor = _need(authorization, x_api_key, "cases.manage")
    conn = _DB()
    try:
        c = conn.execute("SELECT * FROM ls_cases WHERE id=?", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Case not found")
        if c["status"] == "RESOLVED":
            return {**dict(c), "duplicate": True}
        conn.execute("UPDATE ls_cases SET status='RESOLVED', resolved_at=? WHERE id=?",
                     (now(), cid))
        from .notify import emit
        emit(conn, "CaseResolved", "case", cid, actor, {})
        conn.commit()
        return dict(conn.execute("SELECT * FROM ls_cases WHERE id=?", (cid,)).fetchone())
    finally:
        conn.close()
