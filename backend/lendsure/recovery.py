"""Territory-based recovery: officers own a city, borrowers default to it,
and cases travel across cities with a request/review workflow.

Real collection shops work territories: each recovery officer owns the
borrowers in their city because field visits, local language and local
contacts only work locally. When a borrower moves (or a case lands in the
wrong territory), the case is *requested* into the borrower's city and a
supervisor approves the handoff — never silently reassigned. Every step
lands in the audit trail so ownership is always explainable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ls", tags=["recovery"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def now() -> str:
    return datetime.utcnow().isoformat()


def _need(authorization: Optional[str], x_api_key: Optional[str], *perms: str) -> str:
    from .api import require_perm
    return require_perm(authorization, x_api_key, *perms)


def _actor(authorization: Optional[str], x_api_key: Optional[str] = None) -> str:
    from .api import actor_of
    return actor_of(authorization, x_api_key)


def _session(authorization: Optional[str]) -> Optional[dict]:
    return _RESOLVE(authorization) if authorization else None


def _my_officer(conn, authorization: Optional[str]) -> Optional[dict]:
    """Officer record for the caller, matched by session phone."""
    s = _session(authorization)
    if not s or not s.get("phone"):
        return None
    row = conn.execute(
        "SELECT * FROM ls_officers WHERE phone=? AND active=1", (s["phone"],)).fetchone()
    return dict(row) if row else None


def _case_row(conn, cid: int) -> dict:
    c = conn.execute("SELECT * FROM ls_cases WHERE id=?", (cid,)).fetchone()
    if not c:
        raise HTTPException(404, "Case not found")
    return dict(c)


def _log(conn, case_id: int, borrower_id: str, actor: str, action: str, detail: dict):
    import json
    from .notify import emit, audit
    emit(conn, action[0].upper() + action[1:], "case", case_id, actor, detail)
    audit(conn, borrower_id or "*", None, actor, action, detail)


# ── officers ──

class OfficerIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=10, max_length=15)
    city: str = Field(min_length=2, max_length=60)


class OfficerPatch(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    active: Optional[int] = None


@router.get("/officers")
def list_officers(authorization: str | None = Header(default=None),
                  x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "officer.manage")
    conn = _DB()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM ls_officers ORDER BY city, name")]
        for o in rows:
            o["open_cases"] = conn.execute(
                "SELECT COUNT(*) c FROM ls_cases WHERE assigned_to=? AND status NOT IN ('RESOLVED','CLOSED')",
                (o["phone"],)).fetchone()["c"]
        return rows
    finally:
        conn.close()


@router.post("/officers")
def upsert_officer(body: OfficerIn, authorization: str | None = Header(default=None),
                   x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "officer.manage")
    phone = "".join(ch for ch in body.phone if ch.isdigit())[-10:]
    if len(phone) != 10:
        raise HTTPException(400, "Officer phone must be a 10-digit mobile number")
    conn = _DB()
    try:
        conn.execute(
            "INSERT INTO ls_officers (name, phone, city, active, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(phone) DO UPDATE SET name=excluded.name, city=excluded.city, active=1",
            (body.name.strip(), phone, body.city.strip(), 1, now()))
        conn.commit()
        return dict(conn.execute("SELECT * FROM ls_officers WHERE phone=?", (phone,)).fetchone())
    finally:
        conn.close()


@router.patch("/officers/{oid}")
def patch_officer(oid: int, body: OfficerPatch, authorization: str | None = Header(default=None),
                  x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "officer.manage")
    conn = _DB()
    try:
        o = conn.execute("SELECT * FROM ls_officers WHERE id=?", (oid,)).fetchone()
        if not o:
            raise HTTPException(404, "Officer not found")
        o = dict(o)
        name = (body.name or o["name"]).strip()
        city = (body.city or o["city"]).strip()
        active = o["active"] if body.active is None else (1 if body.active else 0)
        if len(name) < 2 or len(city) < 2:
            raise HTTPException(400, "Name and city are required")
        conn.execute("UPDATE ls_officers SET name=?, city=?, active=? WHERE id=?",
                     (name, city, active, oid))
        conn.commit()
        return dict(conn.execute("SELECT * FROM ls_officers WHERE id=?", (oid,)).fetchone())
    finally:
        conn.close()


@router.get("/officers/me")
def my_officer(authorization: str | None = Header(default=None)):
    """Who am I as a recovery officer — drives the territory default."""
    conn = _DB()
    try:
        o = _my_officer(conn, authorization)
        if not o:
            raise HTTPException(404, "No officer record for this login")
        o["open_cases"] = conn.execute(
            "SELECT COUNT(*) c FROM ls_cases WHERE assigned_to=? AND status NOT IN ('RESOLVED','CLOSED')",
            (o["phone"],)).fetchone()["c"]
        return o
    finally:
        conn.close()


@router.get("/territory/summary")
def territory_summary(authorization: str | None = Header(default=None),
                      x_api_key: str | None = Header(default=None)):
    """Portfolio snapshot for the caller's assigned city."""
    from .api import role_of
    conn = _DB()
    try:
        role = role_of(authorization, x_api_key)
        city = None
        if role == "guest":
            raise HTTPException(403, "Sign in to view territory data")
        o = _my_officer(conn, authorization)
        if o:
            city = o["city"]
        q = "SELECT COUNT(*) c FROM ls_borrowers"
        params: list = []
        if city:
            q += " WHERE city=?"
            params.append(city)
        borrowers = conn.execute(q, params).fetchone()["c"]
        open_cases = conn.execute(
            "SELECT COUNT(*) c FROM ls_cases WHERE status NOT IN ('RESOLVED','CLOSED')"
            + (" AND city=?" if city else ""), ([city] if city else [])).fetchone()["c"]
        pending_transfers = conn.execute(
            "SELECT COUNT(*) c FROM ls_case_transfers WHERE status='REQUESTED'"
            + (" AND to_city=?" if city else ""), ([city] if city else [])).fetchone()["c"]
        return {"city": city or "ALL", "borrowers": borrowers,
                "open_cases": open_cases, "pending_transfers": pending_transfers,
                "officer": o}
    finally:
        conn.close()


# ── case assignment + cross-city transfer ──

class AssignIn(BaseModel):
    officer_phone: str = Field(min_length=10, max_length=15)


class TransferRequestIn(BaseModel):
    to_city: str = Field(min_length=2, max_length=60)
    note: str = ""


class TransferReviewIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = ""
    assign_to: str = ""


@router.post("/cases/{cid}/assign")
def assign_case(cid: int, body: AssignIn, authorization: str | None = Header(default=None),
               x_api_key: str | None = Header(default=None)):
    actor = _need(authorization, x_api_key, "cases.manage")
    phone = "".join(ch for ch in body.officer_phone if ch.isdigit())[-10:]
    conn = _DB()
    try:
        c = _case_row(conn, cid)
        o = conn.execute("SELECT * FROM ls_officers WHERE phone=? AND active=1", (phone,)).fetchone()
        if not o:
            raise HTTPException(400, "No active officer with that phone")
        o = dict(o)
        conn.execute("UPDATE ls_cases SET assigned_to=? WHERE id=?", (phone, cid))
        _log(conn, cid, c["borrower_id"], actor, "case_assigned",
             {"case_id": cid, "officer": o["name"], "phone": phone, "city": o["city"]})
        conn.commit()
        return dict(conn.execute("SELECT * FROM ls_cases WHERE id=?", (cid,)).fetchone())
    finally:
        conn.close()


@router.post("/cases/{cid}/transfer-request")
def request_transfer(cid: int, body: TransferRequestIn,
                    authorization: str | None = Header(default=None),
                    x_api_key: str | None = Header(default=None)):
    actor = _need(authorization, x_api_key, "cases.manage")
    conn = _DB()
    try:
        c = _case_row(conn, cid)
        if c["status"] in ("RESOLVED", "CLOSED"):
            raise HTTPException(400, "Closed cases cannot be transferred")
        to_city = body.to_city.strip()
        if c.get("city") and c["city"].lower() == to_city.lower():
            raise HTTPException(400, "Case is already in that city")
        dup = conn.execute("SELECT id FROM ls_case_transfers WHERE case_id=? AND status='REQUESTED'",
                           (cid,)).fetchone()
        if dup:
            raise HTTPException(400, "A transfer request is already pending for this case")
        cur = conn.cursor()
        cur.execute("INSERT INTO ls_case_transfers (case_id, from_city, to_city, requested_by, status, note, created_at)"
                    " VALUES (?,?,?,?, 'REQUESTED',?,?)",
                    (cid, c.get("city") or "", to_city, actor, (body.note or "").strip(), now()))
        conn.execute("UPDATE ls_cases SET transfer_status='REQUESTED' WHERE id=?", (cid,))
        _log(conn, cid, c["borrower_id"], actor, "case_transfer_requested",
             {"case_id": cid, "from_city": c.get("city") or "", "to_city": to_city,
              "note": (body.note or "").strip()})
        conn.commit()
        return {"ok": True, "transfer_id": cur.lastrowid, "to_city": to_city}
    finally:
        conn.close()


@router.post("/cases/{cid}/transfer-review")
def review_transfer(cid: int, body: TransferReviewIn,
                   authorization: str | None = Header(default=None),
                   x_api_key: str | None = Header(default=None)):
    actor = _need(authorization, x_api_key, "cases.manage")
    conn = _DB()
    try:
        c = _case_row(conn, cid)
        t = conn.execute("SELECT * FROM ls_case_transfers WHERE case_id=? AND status='REQUESTED'"
                         " ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        if not t:
            raise HTTPException(400, "No pending transfer request for this case")
        t = dict(t)
        if body.decision == "REJECT":
            conn.execute("UPDATE ls_case_transfers SET status='REJECTED', decided_by=?, decided_at=?, note=? WHERE id=?",
                         (actor, now(), (body.note or t["note"]).strip(), t["id"]))
            conn.execute("UPDATE ls_cases SET transfer_status='NONE' WHERE id=?", (cid,))
            _log(conn, cid, c["borrower_id"], actor, "case_transfer_rejected",
                 {"case_id": cid, "to_city": t["to_city"], "note": (body.note or "").strip()})
        else:
            assign_phone = "".join(ch for ch in (body.assign_to or "") if ch.isdigit())[-10:] or ""
            if assign_phone:
                o = conn.execute("SELECT * FROM ls_officers WHERE phone=? AND active=1",
                                 (assign_phone,)).fetchone()
                if not o:
                    raise HTTPException(400, "No active officer with that phone")
            conn.execute("UPDATE ls_case_transfers SET status='TRANSFERRED', decided_by=?, decided_at=?, note=? WHERE id=?",
                         (actor, now(), (body.note or t["note"]).strip(), t["id"]))
            conn.execute("UPDATE ls_cases SET city=?, assigned_to=?, transfer_status='TRANSFERRED' WHERE id=?",
                         (t["to_city"], assign_phone, cid))
            _log(conn, cid, c["borrower_id"], actor, "case_transferred",
                 {"case_id": cid, "from_city": t["from_city"], "to_city": t["to_city"],
                  "assigned_to": assign_phone, "note": (body.note or "").strip()})
        conn.commit()
        out = dict(conn.execute("SELECT * FROM ls_cases WHERE id=?", (cid,)).fetchone())
        out["transfer"] = dict(conn.execute("SELECT * FROM ls_case_transfers WHERE id=?", (t["id"],)).fetchone())
        return out
    finally:
        conn.close()


@router.get("/cases/{cid}/transfers")
def case_transfers(cid: int, authorization: str | None = Header(default=None),
                   x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "cases.manage", "admin.read")
    conn = _DB()
    try:
        _case_row(conn, cid)
        return [dict(r) for r in conn.execute(
            "SELECT * FROM ls_case_transfers WHERE case_id=? ORDER BY id", (cid,)).fetchall()]
    finally:
        conn.close()


@router.get("/transfers")
def transfer_queue(status: str = "", authorization: str | None = Header(default=None),
                   x_api_key: str | None = Header(default=None)):
    """Pending handoffs across cities — the supervisor's inbox."""
    _need(authorization, x_api_key, "cases.manage", "admin.read")
    conn = _DB()
    try:
        q = ("SELECT t.*, c.title case_title, c.borrower_id FROM ls_case_transfers t "
             "LEFT JOIN ls_cases c ON c.id=t.case_id WHERE 1=1")
        params: list = []
        if status:
            q += " AND t.status=?"
            params.append(status.upper())
        q += " ORDER BY t.id DESC LIMIT 200"
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()
