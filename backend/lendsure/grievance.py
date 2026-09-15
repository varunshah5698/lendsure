"""Borrower grievance / complaint portal.

Borrowers raise a complaint without logging in and get a ticket ID they can
track with their phone number. Staff triage the queue: assign an owner,
investigate (notes form the case file), resolve, escalate, or close.
Every transition is audited and notifies like any other domain event.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ls", tags=["grievance"])

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


CATEGORIES = {"billing", "repayment", "collection", "fraud_dispute",
              "documents", "service", "other"}
PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
STATUSES = {"OPEN", "IN_REVIEW", "RESOLVED", "ESCALATED", "CLOSED"}


def _clean_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())[-10:]
    if len(digits) != 10:
        raise HTTPException(400, "A valid 10-digit mobile number is required")
    return digits


def _row(conn, gid: int) -> dict:
    g = conn.execute("SELECT * FROM ls_grievances WHERE id=?", (gid,)).fetchone()
    if not g:
        raise HTTPException(404, "Grievance not found")
    return dict(g)


def _with_notes(conn, g: dict) -> dict:
    g["notes"] = [dict(r) for r in conn.execute(
        "SELECT * FROM ls_grievance_notes WHERE grievance_id=? ORDER BY id", (g["id"],)).fetchall()]
    return g


def _log(conn, g: dict, actor: str, action: str, detail: dict):
    from .notify import emit, audit
    emit(conn, action[0].upper() + action[1:], "grievance", g["id"], actor, detail)
    audit(conn, g.get("borrower_id") or "*", None, actor, action, detail)


class GrievanceIn(BaseModel):
    borrower_id: str = ""
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=10, max_length=15)
    category: str = "other"
    subject: str = Field(min_length=5, max_length=140)
    description: str = ""


class NoteIn(BaseModel):
    note: str = Field(min_length=2, max_length=2000)


class AssignGrievanceIn(BaseModel):
    officer_phone: str = Field(min_length=10, max_length=15)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(OPEN|IN_REVIEW|RESOLVED|ESCALATED|CLOSED)$")
    note: str = ""


@router.post("/grievances")
def raise_grievance(body: GrievanceIn):
    """Public: file a complaint, get a ticket ID. No login needed."""
    phone = _clean_phone(body.phone)
    category = (body.category or "other").strip().lower()
    if category not in CATEGORIES:
        raise HTTPException(400, f"Category must be one of: {', '.join(sorted(CATEGORIES))}")
    if len((body.description or "").strip()) > 4000:
        raise HTTPException(400, "Description is too long (max 4000 characters)")
    conn = _DB()
    try:
        ts = now()
        cur = conn.cursor()
        cur.execute("INSERT INTO ls_grievances (ticket_id, borrower_id, name, phone, category, subject,"
                    " description, priority, status, assigned_to, created_at, updated_at, resolved_at)"
                    " VALUES ('PENDING',?,?,?,?,?,?,'NORMAL','OPEN','',?,?,NULL)",
                    ((body.borrower_id or "").strip(), body.name.strip(), phone, category,
                     body.subject.strip(), (body.description or "").strip(), ts, ts))
        gid = cur.lastrowid
        ticket = f"GRV-{gid:06d}"
        conn.execute("UPDATE ls_grievances SET ticket_id=? WHERE id=?", (ticket, gid))
        conn.execute("INSERT INTO ls_grievance_notes (grievance_id, actor, note, created_at) VALUES (?,?,?,?)",
                     (gid, "system", "Complaint received. Our team will review it shortly.", ts))
        g = _row(conn, gid)
        _log(conn, g, f"{g['name']} ({phone})", "grievance_raised",
             {"ticket_id": ticket, "category": category, "subject": g["subject"]})
        conn.commit()
        return {"ok": True, "ticket_id": ticket, "id": gid,
                "message": "Complaint registered. Save your ticket ID to track it."}
    finally:
        conn.close()


@router.get("/grievances/track")
def track_grievance(ticket_id: str = "", phone: str = ""):
    """Public: track a complaint with ticket ID + phone number."""
    ticket = (ticket_id or "").strip().upper()
    conn = _DB()
    try:
        g = conn.execute("SELECT * FROM ls_grievances WHERE ticket_id=?", (ticket,)).fetchone()
        if not g:
            raise HTTPException(404, "No complaint found with that ticket ID")
        g = dict(g)
        if g["phone"] != _clean_phone(phone):
            raise HTTPException(403, "Phone number does not match this ticket")
        return _with_notes(conn, g)
    finally:
        conn.close()


@router.get("/grievances")
def list_grievances(status: str = "", assigned_to: str = "", category: str = "",
                    limit: int = 50, authorization: str | None = Header(default=None),
                    x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "grievance.read")
    conn = _DB()
    try:
        q = ("SELECT g.*, (SELECT COUNT(*) FROM ls_grievance_notes n WHERE n.grievance_id=g.id) notes_count"
             " FROM ls_grievances g WHERE 1=1")
        params: list = []
        if status:
            q += " AND g.status=?"
            params.append(status.upper())
        if assigned_to:
            q += " AND g.assigned_to=?"
            params.append(assigned_to.strip())
        if category:
            q += " AND g.category=?"
            params.append(category.strip().lower())
        q += " ORDER BY g.id DESC LIMIT ?"
        params.append(min(limit, 200))
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()


@router.get("/grievances/{gid}")
def get_grievance(gid: int, authorization: str | None = Header(default=None),
                 x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "grievance.read")
    conn = _DB()
    try:
        return _with_notes(conn, _row(conn, gid))
    finally:
        conn.close()


@router.post("/grievances/{gid}/notes")
def add_note(gid: int, body: NoteIn, authorization: str | None = Header(default=None),
             x_api_key: str | None = Header(default=None)):
    actor = _need(authorization, x_api_key, "grievance.manage")
    conn = _DB()
    try:
        g = _row(conn, gid)
        if g["status"] in ("RESOLVED", "CLOSED"):
            raise HTTPException(400, "Cannot add notes to a closed complaint. Reopen it first.")
        ts = now()
        conn.execute("INSERT INTO ls_grievance_notes (grievance_id, actor, note, created_at) VALUES (?,?,?,?)",
                     (gid, actor, body.note.strip(), ts))
        conn.execute("UPDATE ls_grievances SET updated_at=? WHERE id=?", (ts, gid))
        _log(conn, g, actor, "grievance_noted", {"ticket_id": g["ticket_id"]})
        conn.commit()
        return _with_notes(conn, _row(conn, gid))
    finally:
        conn.close()


@router.post("/grievances/{gid}/assign")
def assign_grievance(gid: int, body: AssignGrievanceIn,
                     authorization: str | None = Header(default=None),
                     x_api_key: str | None = Header(default=None)):
    actor = _need(authorization, x_api_key, "grievance.manage")
    phone = _clean_phone(body.officer_phone)
    conn = _DB()
    try:
        g = _row(conn, gid)
        o = conn.execute("SELECT * FROM ls_officers WHERE phone=? AND active=1", (phone,)).fetchone()
        if not o:
            raise HTTPException(400, "No active officer with that phone")
        o = dict(o)
        conn.execute("UPDATE ls_grievances SET assigned_to=?, updated_at=? WHERE id=?",
                     (phone, now(), gid))
        conn.execute("INSERT INTO ls_grievance_notes (grievance_id, actor, note, created_at) VALUES (?,?,?,?)",
                     (gid, actor, f"Assigned to {o['name']} ({o['city']}) for investigation.", now()))
        _log(conn, g, actor, "grievance_assigned",
             {"ticket_id": g["ticket_id"], "officer": o["name"], "phone": phone})
        conn.commit()
        return _with_notes(conn, _row(conn, gid))
    finally:
        conn.close()


@router.post("/grievances/{gid}/status")
def set_status(gid: int, body: StatusIn, authorization: str | None = Header(default=None),
               x_api_key: str | None = Header(default=None)):
    actor = _need(authorization, x_api_key, "grievance.manage")
    conn = _DB()
    try:
        g = _row(conn, gid)
        to = body.status
        if g["status"] in ("RESOLVED", "CLOSED") and to not in ("OPEN",):
            raise HTTPException(400, "Closed complaints can only be reopened (set status to OPEN)")
        if to == g["status"]:
            return _with_notes(conn, g)
        ts = now()
        resolved = ts if to in ("RESOLVED", "CLOSED") else None
        conn.execute("UPDATE ls_grievances SET status=?, updated_at=?, resolved_at=? WHERE id=?",
                     (to, ts, resolved, gid))
        verbs = {"IN_REVIEW": "under investigation", "RESOLVED": "resolved",
                 "ESCALATED": "escalated to a senior reviewer", "CLOSED": "closed",
                 "OPEN": "reopened"}
        note = f"Status changed to {to} ({verbs[to]})."
        if body.note.strip():
            note += f" {body.note.strip()}"
        conn.execute("INSERT INTO ls_grievance_notes (grievance_id, actor, note, created_at) VALUES (?,?,?,?)",
                     (gid, actor, note, ts))
        _log(conn, g, actor, "grievance_status",
             {"ticket_id": g["ticket_id"], "from": g["status"], "to": to})
        conn.commit()
        return _with_notes(conn, _row(conn, gid))
    finally:
        conn.close()
