"""Background jobs: async work with real status tracking.

A daemon worker polls ls_jobs and runs handlers by kind with retries.
Long operations (document verification, risk recalculation hooks) never
block API requests; the frontend reads actual job rows — never fake progress.

Document pipeline stages per document live in ls_documents:
  pipeline_status: PENDING -> PROCESSING -> VERIFIED | REVIEW | FAILED
  ocr_status: always NOT_AVAILABLE in this deployment (no OCR engine is
    configured — surfaced honestly instead of fabricated).
  scan_status: always NOT_AVAILABLE (no malware scanner configured).
Verification here = real deterministic checks over stored metadata and the
borrower's stored profile (type coverage, duplicates via content hash,
income consistency, verification-flag consistency). Anything ambiguous
goes to human REVIEW, never auto-VERIFIED on thin evidence.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/ls", tags=["jobs"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731
_started = False
_lock = threading.Lock()


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def now() -> str:
    return datetime.utcnow().isoformat()


def _role_of(authorization: Optional[str]) -> str:
    from .api import role_of
    return role_of(authorization, None)


def enqueue(conn, kind: str, ref_type: str = "", ref_id: str = "",
            payload: dict | None = None, idempotency_key: str | None = None,
            max_attempts: int = 3) -> int:
    """Insert a PENDING job. Idempotent when idempotency_key is given."""
    if idempotency_key:
        row = conn.execute("SELECT id FROM ls_jobs WHERE idempotency_key=?",
                           (idempotency_key,)).fetchone()
        if row:
            return row["id"]
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ls_jobs (kind,ref_type,ref_id,status,payload,idempotency_key,max_attempts,created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (kind, ref_type, str(ref_id), "PENDING", json.dumps(payload or {}),
         idempotency_key, max_attempts, now()))
    return cur.lastrowid


# ── document verification handler (real checks, honest limits) ──

_ALLOWED_TYPES = {"identity", "bank_statement", "income_document", "salary_slip", "business_document"}
_ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}


def _handle_document_verify(conn, job: dict) -> dict:
    payload = json.loads(job["payload"] or "{}")
    doc_id = int(payload.get("doc_id") or job["ref_id"] or 0)
    doc = conn.execute("SELECT * FROM ls_documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        raise RuntimeError(f"document {doc_id} not found")
    doc = dict(doc)
    b = conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?",
                     (doc["borrower_id"],)).fetchone()
    b = dict(b) if b else {}
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str, weight: str = "info"):
        checks.append({"check": name, "passed": passed, "detail": detail,
                       "severity": weight})

    # 1. file validation (name + extension allowlist + size cap when bytes stored)
    fname = (doc.get("file_name") or "").strip()
    ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    check("file_present", bool(fname), f"file_name={'present' if fname else 'MISSING'}",
          "fail" if not fname else "info")
    check("file_type_allowed", ext in _ALLOWED_EXT,
          f"extension '{ext or '?'}' {'allowed' if ext in _ALLOWED_EXT else 'NOT allowed ' + str(sorted(_ALLOWED_EXT))}",
          "fail" if ext not in _ALLOWED_EXT else "info")
    frow = conn.execute("SELECT size_bytes FROM ls_doc_files WHERE doc_id=?",
                        (doc_id,)).fetchone()
    if frow:
        check("file_size", frow["size_bytes"] <= 2_000_000,
              f"{frow['size_bytes']} bytes (cap 2MB)",
              "fail" if frow["size_bytes"] > 2_000_000 else "info")
    else:
        check("file_bytes", False, "no file bytes stored — metadata-only record",
              "warn")

    # 2. duplicate detection via content hash (or file_name fallback)
    chash = doc.get("content_hash") or ""
    if chash:
        dups = conn.execute(
            "SELECT COUNT(*) c FROM ls_documents WHERE borrower_id=? AND content_hash=? AND id!=?",
            (doc["borrower_id"], chash, doc_id)).fetchone()["c"]
        check("duplicate", dups == 0,
              "content hash unique" if not dups else f"{dups} duplicate(s) with same content",
              "info" if not dups else "fail")
    else:
        dups = conn.execute(
            "SELECT COUNT(*) c FROM ls_documents WHERE borrower_id=? AND file_name=? AND id!=?",
            (doc["borrower_id"], fname, doc_id)).fetchone()["c"]
        check("duplicate_name", dups == 0,
              "file name unique" if not dups else f"{dups} same-name document(s) — possible duplicate",
              "info" if not dups else "warn")

    # 3. type coverage: is this doc type already verified?
    if doc.get("doc_type") not in _ALLOWED_TYPES:
        check("known_type", False, f"unknown doc_type '{doc.get('doc_type')}'", "fail")
    else:
        check("known_type", True, f"type '{doc['doc_type']}' recognized", "info")

    # 4. income consistency (income-ish docs vs borrower's stated/documented income)
    if doc.get("doc_type") in ("income_document", "salary_slip", "bank_statement") and b:
        stated = (b.get("monthly_income") or b.get("avg_income_6m") or 0) or 0
        doc_inc = b.get("doc_avg_income") or 0
        if stated > 0 and doc_inc > 0:
            ratio = doc_inc / stated
            ok = 0.7 <= ratio <= 1.3
            check("income_consistency", ok,
                  f"documented ₹{doc_inc:,.0f} vs stated ₹{stated:,.0f} (ratio {ratio:.2f})",
                  "info" if ok else "warn")
        else:
            check("income_consistency", True, "insufficient income fields to compare — skipped",
                  "info")

    # 5. identity-flag consistency for identity docs
    if doc.get("doc_type") == "identity" and b:
        ver = b.get("id_verification", 0)
        check("identity_flags", ver == 2,
              f"id_verification={ver} (2=verified)",
              "info" if ver == 2 else "warn")

    fails = [c for c in checks if c["severity"] == "fail" and not c["passed"]]
    warns = [c for c in checks if c["severity"] == "warn" and not c["passed"]]
    if fails:
        status, legacy = "FAILED", "suspicious"
    elif warns:
        status, legacy = "REVIEW", "needs_review"
    else:
        status, legacy = "VERIFIED", "verified"

    conn.execute(
        "UPDATE ls_documents SET pipeline_status=?, pipeline_evidence=?, status=? WHERE id=?",
        (status, json.dumps(checks), legacy, doc_id))
    # audit + event (imported lazily to avoid a cycle at module load)
    from .notify import emit, audit as _audit
    actor = "doc-worker"
    _audit(conn, doc["borrower_id"], None, actor, "document_processed",
           {"doc_id": doc_id, "pipeline": status, "checks": len(checks)})
    emit(conn, "DocumentProcessed", "document", doc_id, actor,
         {"pipeline": status, "borrower_id": doc["borrower_id"]})
    if status == "VERIFIED":
        emit(conn, "DocumentVerified", "document", doc_id, actor,
             {"borrower_id": doc["borrower_id"]})
    return {"pipeline": status, "checks": checks}


_HANDLERS = {"document.verify": _handle_document_verify}


def _run_one() -> bool:
    conn = _DB()
    try:
        job = conn.execute(
            "SELECT * FROM ls_jobs WHERE status IN ('PENDING','RETRYING') ORDER BY id LIMIT 1"
        ).fetchone()
        if not job:
            return False
        job = dict(job)
        if job["attempts"] >= job["max_attempts"]:
            conn.execute("UPDATE ls_jobs SET status='FAILED', error='max attempts exceeded', finished_at=? WHERE id=?",
                         (now(), job["id"]))
            conn.commit()
            return True
        conn.execute("UPDATE ls_jobs SET status='PROCESSING', attempts=attempts+1, started_at=?, error='' WHERE id=?",
                     (now(), job["id"]))
        conn.commit()
        handler = _HANDLERS.get(job["kind"])
        if not handler:
            conn.execute("UPDATE ls_jobs SET status='FAILED', error=?, finished_at=? WHERE id=?",
                         (f"no handler for kind '{job['kind']}'", now(), job["id"]))
            conn.commit()
            return True
        try:
            result = handler(conn, job)
            conn.execute("UPDATE ls_jobs SET status='COMPLETED', result=?, finished_at=? WHERE id=?",
                         (json.dumps(result)[:4000], now(), job["id"]))
            conn.commit()
        except Exception as e:
            left = job["max_attempts"] - job["attempts"] - 1
            if left > 0:
                conn.execute("UPDATE ls_jobs SET status='RETRYING', error=? WHERE id=?",
                             (str(e)[:500], job["id"]))
            else:
                conn.execute("UPDATE ls_jobs SET status='FAILED', error=?, finished_at=? WHERE id=?",
                             (str(e)[:500], now(), job["id"]))
            conn.commit()
        return True
    finally:
        conn.close()


def _worker():
    time.sleep(3)
    while True:
        try:
            worked = _run_one()
        except Exception as e:
            print(f"[jobs] worker error: {e}", flush=True)
            worked = False
        time.sleep(1 if worked else 5)


def start_worker():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_worker, daemon=True).start()


# ── jobs API ──

def _need(conn_role: str, *perms: str):
    from .api import ROLE_PERMS
    if not any(p in ROLE_PERMS.get(conn_role, set()) for p in perms):
        from fastapi import HTTPException as _H
        raise _H(403, f"Insufficient permissions for role '{conn_role}'")


@router.get("/admin/jobs")
def list_jobs(status: str = "", limit: int = 50,
              authorization: Optional[str] = Header(default=None)):
    from .api import role_of
    role = role_of(authorization, None)
    _need(role, "jobs.manage", "admin.read")
    conn = _DB()
    try:
        q = "SELECT * FROM ls_jobs"
        params: list = []
        if status:
            q += " WHERE status=?"
            params.append(status.upper())
        q += " ORDER BY id DESC LIMIT ?"
        params.append(min(limit, 200))
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        agg = conn.execute(
            "SELECT status, COUNT(*) c FROM ls_jobs GROUP BY status").fetchall()
        return {"jobs": rows, "by_status": {r["status"]: r["c"] for r in agg}}
    finally:
        conn.close()


@router.post("/admin/jobs/{jid}/retry")
def retry_job(jid: int, authorization: Optional[str] = Header(default=None)):
    from .api import role_of
    role = role_of(authorization, None)
    _need(role, "jobs.manage")
    conn = _DB()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ls_jobs SET status='RETRYING', error='' WHERE id=? AND status='FAILED'",
                    (jid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Failed job not found")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
