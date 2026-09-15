"""Domain events, notifications, and a live SSE stream.

Every important mutation in the loan lifecycle calls emit()/audit()/notify()
here, so the UI, the graph engine and the audit trail all read the same
backend truth. Nothing here fabricates state — the stream only replays rows.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/ls", tags=["events"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def now() -> str:
    return datetime.utcnow().isoformat()


# ── writers (called by other backend modules inside their transactions) ──

GENESIS_HASH = "GENESIS"


def chain_hash(prev_hash, borrower_id, analysis_id, actor, action, detail_json, created_at) -> str:
    import hashlib
    payload = "|".join([prev_hash or GENESIS_HASH, str(borrower_id), str(analysis_id),
                        actor or "", action or "", detail_json or "", created_at or ""])
    return hashlib.sha256(payload.encode()).hexdigest()


def emit(conn, type: str, entity: str, entity_id, actor: str = "", data: dict | None = None) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ls_events (type,entity,entity_id,actor,data,created_at) VALUES (?,?,?,?,?,?)",
        (type, entity, str(entity_id), actor, json.dumps(data or {}), now()))
    return cur.lastrowid


def audit(conn, borrower_id: str, analysis_id, actor: str, action: str, detail) -> int:
    """Tamper-EVIDENT append (not tamper-proof): each row chains to the
    previous row's hash, so silent edits/deletes break verification.
    Single-writer assumption: concurrent writers could fork the chain
    (fine on this single-worker deployment; documented, not hidden)."""
    detail_json = detail if isinstance(detail, str) else json.dumps(detail)
    ts = now()
    try:
        prev = conn.execute("SELECT chain_hash FROM ls_audit ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = prev["chain_hash"] if prev and prev["chain_hash"] else GENESIS_HASH
        ch = chain_hash(prev_hash, borrower_id, analysis_id, actor, action, detail_json, ts)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ls_audit (borrower_id,analysis_id,actor,action,detail,created_at,prev_hash,chain_hash)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (borrower_id, analysis_id, actor, action, detail_json, ts, prev_hash, ch))
    except Exception:
        # Pre-chain schema (migration not yet applied): plain append.
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ls_audit (borrower_id,analysis_id,actor,action,detail,created_at) VALUES (?,?,?,?,?,?)",
            (borrower_id, analysis_id, actor, action, detail_json, ts))
    return cur.lastrowid


def verify_audit_chain(conn) -> dict:
    """Walk the chain; return {ok, checked, bad_id, reason}."""
    rows = conn.execute(
        "SELECT id, borrower_id, analysis_id, actor, action, detail, created_at, prev_hash, chain_hash"
        " FROM ls_audit ORDER BY id").fetchall()
    prev = GENESIS_HASH
    checked = 0
    for row in rows:
        r = dict(zip(
            ("id", "borrower_id", "analysis_id", "actor", "action",
             "detail", "created_at", "prev_hash", "chain_hash"), row))
        if not r.get("chain_hash"):
            return {"ok": False, "checked": checked, "bad_id": r["id"],
                    "reason": "row predates hash chaining (run boot backfill)"}
        if r.get("prev_hash") != prev:
            return {"ok": False, "checked": checked, "bad_id": r["id"],
                    "reason": "broken link: prev_hash does not match previous row"}
        if chain_hash(r["prev_hash"], r["borrower_id"], r["analysis_id"],
                      r["actor"], r["action"], r["detail"], r["created_at"]) != r["chain_hash"]:
            return {"ok": False, "checked": checked, "bad_id": r["id"],
                    "reason": "content mismatch: row was modified after writing"}
        prev = r["chain_hash"]
        checked += 1
    return {"ok": True, "checked": checked, "bad_id": None, "reason": ""}


def notify(conn, audience: str, kind: str, title: str, body: str = "", link: str = "") -> int:
    """audience is a session token or 'role:<role>' broadcast."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ls_notifications (audience,kind,title,body,link,created_at) VALUES (?,?,?,?,?,?)",
        (audience, kind, title, body, link, now()))
    return cur.lastrowid


def _session_of(authorization: Optional[str]) -> dict:
    s = _RESOLVE(authorization) if authorization else None
    if not s:
        raise HTTPException(401, "Sign in required")
    return s


def _audiences(token: str, role: str) -> list[str]:
    return [token, f"role:{role}"]




def _audience_filter(role: str) -> str:
    """Guests see only items addressed to their own session or to the guest
    role explicitly. In particular role:all broadcasts (written for staff)
    never leak to guests — default to nothing rather than everything."""
    if role == "guest":
        return "(audience=? OR audience='role:guest')"
    return "(audience=? OR audience=? OR audience='role:all')"


def _audience_params(token: str, role: str) -> list:
    if role == "guest":
        return [token]
    return [token, f"role:{role}"]


def _mask_audience(row: dict, token: str) -> dict:
    """Never echo live session tokens: token-scoped rows read as 'you',
    broadcasts keep their role: label."""
    if row.get("audience") and not str(row["audience"]).startswith("role:"):
        row["audience"] = "you" if row["audience"] == token else "private"
    return row


# ── notifications API ──

@router.get("/notifications")
def list_notifications(authorization: Optional[str] = Header(default=None), limit: int = 50):
    s = _session_of(authorization)
    conn = _DB()
    try:
        rows = conn.execute(
            "SELECT * FROM ls_notifications WHERE " + _audience_filter(s.get("role", "guest")) + " ORDER BY id DESC LIMIT ?",
            (*_audience_params(s["token"], s.get("role", "guest")), min(limit, 100)),
        ).fetchall()
        return [_mask_audience(dict(r), s["token"]) for r in rows]
    finally:
        conn.close()


@router.get("/notifications/unread-count")
def unread_count(authorization: Optional[str] = Header(default=None)):
    s = _session_of(authorization)
    conn = _DB()
    try:
        n = conn.execute(
            "SELECT COUNT(*) c FROM ls_notifications WHERE is_read=0 AND " + _audience_filter(s.get("role", "guest")),
            _audience_params(s["token"], s.get("role", "guest"))).fetchone()["c"]
        latest = conn.execute(
            "SELECT MAX(id) m FROM ls_notifications WHERE " + _audience_filter(s.get("role", "guest")),
            _audience_params(s["token"], s.get("role", "guest"))).fetchone()["m"]
        return {"unread": n, "latest_id": latest or 0}
    finally:
        conn.close()


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, authorization: Optional[str] = Header(default=None)):
    s = _session_of(authorization)
    conn = _DB()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE ls_notifications SET is_read=1 WHERE id=? AND " + _audience_filter(s.get("role", "guest")),
            (nid, *_audience_params(s["token"], s.get("role", "guest"))))
        if cur.rowcount == 0:
            raise HTTPException(404, "Notification not found")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/events")
def list_events(entity: str = "", entity_id: str = "", limit: int = 100,
                authorization: Optional[str] = Header(default=None)):
    _session_of(authorization)
    conn = _DB()
    try:
        q = "SELECT * FROM ls_events WHERE 1=1"
        params: list = []
        if entity:
            q += " AND entity=?"
            params.append(entity)
        if entity_id:
            q += " AND entity_id=?"
            params.append(str(entity_id))
        q += " ORDER BY id DESC LIMIT ?"
        params.append(min(limit, 200))
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()


# ── live stream (SSE). Token never goes in the URL: mint a 60s ticket first. ──

_TICKETS: dict[str, tuple[str, str, float]] = {}


@router.post("/events/ticket")
def stream_ticket(authorization: Optional[str] = Header(default=None)):
    s = _session_of(authorization)
    t = uuid.uuid4().hex
    _TICKETS[t] = (s["token"], s.get("role", "guest"), time.time() + 60)
    return {"ticket": t}


@router.get("/events/stream")
def stream(ticket: str = Query("")):
    rec = _TICKETS.pop(ticket, None)
    if not rec or rec[2] < time.time():
        raise HTTPException(401, "Invalid or expired ticket")
    token, role = rec[0], rec[1]

    def gen():
        last_id = 0
        start = time.time()
        yield ": connected\n\n"
        try:
            while time.time() - start < 105:
                conn = _DB()
                try:
                    rows = conn.execute(
                        "SELECT id, kind, title, body, link, created_at FROM ls_notifications "
                        "WHERE id>? AND " + _audience_filter(role) + " ORDER BY id",
                        (last_id, *_audience_params(token, role))).fetchall()
                finally:
                    conn.close()
                for r in rows:
                    last_id = max(last_id, r["id"])
                    yield f"data: {json.dumps(_mask_audience(dict(r), token))}\n\n"
                yield ": ping\n\n"
                time.sleep(4)
        except GeneratorExit:
            pass

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive",
    })
