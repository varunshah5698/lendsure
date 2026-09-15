"""Central OTP manager: generation, storage, expiry, cooldowns, verification.

Mirrors the classic OTP-service shape (request endpoint -> store with TTL ->
verify endpoint -> burn on success), one implementation for both channels:
kind "phone" uses the otps table keyed by mobile number, kind "email" uses
email_otps keyed by (email, purpose).

Rules (identical for both channels unless noted):
- codes are cryptographically random, length from LENDSURE_OTP_LEN (4-8, 6)
- max 5 codes per identity per hour, min 60s between sends (cooldown)
- codes expire (TTL minutes, per channel), 5 wrong attempts burns the code
- verification uses constant-time comparison
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException

TABLES = {"phone": "otps", "email": "email_otps"}
IDCOLS = {"phone": "phone", "email": "email"}
NEEDS_PURPOSE = {"email"}

# Per-channel wording. Kept byte-identical to the historical messages so
# clients (and tests) see no behavior change from the refactor.
TEXT = {
    "phone": {
        "wrong": "Wrong OTP. {left} attempt(s) left.",
        "burned": "Too many wrong attempts. Request a new OTP.",
        "expired": "OTP expired or not found. Request a new one.",
        "cooldown": "A code was just sent — check your messages (or wait a minute to resend).",
        "rate": "Too many OTP requests. Try again in an hour.",
    },
    "email": {
        "wrong": "Wrong code. {left} attempt(s) left.",
        "burned": "Too many wrong attempts. Request a new code.",
        "expired": "Code expired or not found. Request a new one.",
        "cooldown": "A code was just sent — check your inbox (or wait a minute to resend).",
        "rate": "Too many codes requested. Try again in an hour.",
    },
}

MAX_ATTEMPTS = 5
MAX_PER_HOUR = 5
COOLDOWN_SEC = 60


def code_length() -> int:
    try:
        n = int(os.environ.get("LENDSURE_OTP_LEN", "6"))
    except ValueError:
        n = 6
    return max(4, min(n, 8))


def new_code(length: int | None = None) -> str:
    n = length or code_length()
    return f"{secrets.randbelow(9 * 10 ** (n - 1)) + 10 ** (n - 1):d}"


def _table(kind: str) -> tuple[str, str]:
    if kind not in TABLES:
        raise ValueError(f"unknown OTP channel: {kind}")
    return TABLES[kind], IDCOLS[kind]


def issue(conn, kind: str, identity: str, purpose: str = "",
          ttl_min: int = 5, max_attempts: int = MAX_ATTEMPTS,
          code_override: str | None = None) -> str:
    """Create + store a code. Raises 429 on hourly cap or cooldown.

    code_override stores a caller-chosen value instead of a fresh random
    code (used for provider-managed flows like Twilio Verify, where the
    real code lives with the provider and the local row is just a marker).
    Caps and cooldowns still apply — the override changes nothing else."""
    table, idcol = _table(kind)
    cur = conn.cursor()
    where = f"{idcol}=?"
    params: list = [identity]
    if kind in NEEDS_PURPOSE:
        where += " AND purpose=?"
        params.append(purpose)
    recent = cur.execute(
        f"SELECT COUNT(*) c FROM {table} WHERE {where} AND created_at > datetime('now','-1 hour')",
        params).fetchone()["c"]
    if recent >= MAX_PER_HOUR:
        raise HTTPException(429, TEXT[kind]["rate"])
    latest = cur.execute(
        f"SELECT created_at FROM {table} WHERE {where} ORDER BY id DESC LIMIT 1",
        params).fetchone()
    if latest and latest["created_at"] > (
            datetime.utcnow() - timedelta(seconds=COOLDOWN_SEC)).isoformat():
        raise HTTPException(429, TEXT[kind]["cooldown"])
    code = code_override if code_override is not None else new_code()
    now = datetime.utcnow()
    if kind == "phone":
        cur.execute(
            "INSERT INTO otps (phone, code, attempts, created_at, expires_at)"
            " VALUES (?,?,?,?,?)",
            (identity, code, 0, now.isoformat(),
             (now + timedelta(minutes=ttl_min)).isoformat()))
    else:
        cur.execute(
            "INSERT INTO email_otps (email, code, purpose, attempts, created_at, expires_at)"
            " VALUES (?,?,?,?,?,?)",
            (identity, code, purpose, 0, now.isoformat(),
             (now + timedelta(minutes=ttl_min)).isoformat()))
    conn.commit()
    return code


def check(conn, kind: str, identity: str, code: str, purpose: str = "",
          max_attempts: int = MAX_ATTEMPTS) -> None:
    """Verify a code. Burns it on success; counts attempts; raises 400."""
    table, idcol = _table(kind)
    cur = conn.cursor()
    where = f"{idcol}=?"
    params: list = [identity]
    if kind in NEEDS_PURPOSE:
        where += " AND purpose=?"
        params.append(purpose)
    row = cur.execute(
        f"SELECT * FROM {table} WHERE {where} AND expires_at > datetime('now')"
        f" ORDER BY id DESC LIMIT 1", params).fetchone()
    if not row:
        raise HTTPException(400, TEXT[kind]["expired"])
    if row["attempts"] >= max_attempts:
        cur.execute(f"DELETE FROM {table} WHERE {where}", params)
        conn.commit()
        raise HTTPException(400, TEXT[kind]["burned"])
    if not secrets.compare_digest(str(row["code"]), str(code)):
        cur.execute(f"UPDATE {table} SET attempts = attempts + 1 WHERE id=?",
                    (row["id"],))
        conn.commit()
        raise HTTPException(400, TEXT[kind]["wrong"].format(left=max_attempts - row["attempts"] - 1))
    cur.execute(f"DELETE FROM {table} WHERE {where}", params)
    conn.commit()
