"""
AI-Powered Trust & Risk Intelligence for Informal Lending
Backend: FastAPI + SQLite (stdlib) + explainable rule-based AI engine.
Every decision returns score breakdown + evidence + confidence + audit trail.
Run: pip install -r requirements.txt && python app.py  (serves API + dashboard on :8000)
"""
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
import uuid
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


def _load_dotenv():
    """Minimal .env loader (stdlib only): KEY=value lines from backend/.env.
    Real environment variables always win — this only fills gaps, so local
    dev secrets (like LLM_API_KEY) persist across restarts without exports.
    Runs before any os.environ.get below reads configuration."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[env] ignoring unreadable .env: {e}", flush=True)


_load_dotenv()

from lendsure.schema import DDL as LS_DDL, LIFECYCLE_DDL, LS_MIGRATIONS

BASE_DIR = Path(__file__).parent
RUNTIME_ENV = os.environ.get("LENDSURE_ENV", "development").strip().lower()
_configured_db_path = os.environ.get("LENDSURE_DB_PATH", "").strip()
LIVE_DB_PATH = Path(_configured_db_path).expanduser() if _configured_db_path else BASE_DIR / "lending.db"
SEED_DB_PATH = BASE_DIR / "seed" / "lending.db"


def _resolve_db_path() -> Path:
    """Where the live SQLite file lives.

    The live DB is git-ignored (never commit data/PII). Fresh checkouts and
    deploys seed it once from backend/seed/lending.db, which IS tracked.
    Render runs one persistent container, so the live file is used directly.
    """
    live = LIVE_DB_PATH
    try:
        live.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Cannot create database directory {live.parent}: {exc}") from exc
    if not live.exists() and SEED_DB_PATH.exists():
        try:
            shutil.copyfile(SEED_DB_PATH, live)
            print(f"[db] seeded live database from {SEED_DB_PATH.name}", flush=True)
        except Exception as e:
            print(f"[db] seed copy failed: {e}", flush=True)
    return live


DB_PATH = _resolve_db_path()
STATIC_DIR = BASE_DIR / "static"

# ---------------- Security config (env-driven, no secrets in code) ----------------
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "LENDSURE_CORS_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000,http://localhost:5173").split(",") if o.strip()]
MAX_BODY_BYTES = max(1024, int(os.environ.get("LENDSURE_MAX_BODY_BYTES", "1000000")))

app = FastAPI(title="LendSure API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RATE_BUCKETS: dict[str, deque] = {}  # legacy in-memory fallback (unused; kept for tests)


def _rate_check(host: str, limit: int, window: int) -> bool:
    """Sliding-window rate gate backed by SQLite — survives restarts and
    works across workers (unlike the old in-memory buckets). Returns True
    when the hit is allowed (and records it)."""
    now_t = time.time()
    conn = db()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS ls_rate_hits (ip TEXT NOT NULL, tier TEXT NOT NULL, ts REAL NOT NULL)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rate ON ls_rate_hits (ip, tier, ts)")
        tier = f"{limit}/{window}"
        conn.execute("DELETE FROM ls_rate_hits WHERE ts <= ?", (now_t - window,))
        n = conn.execute("SELECT COUNT(*) c FROM ls_rate_hits WHERE ip=? AND tier=? AND ts > ?",
                         (host, tier, now_t - window)).fetchone()["c"]
        if n >= limit:
            conn.commit()
            return False
        conn.execute("INSERT INTO ls_rate_hits (ip, tier, ts) VALUES (?,?,?)", (host, tier, now_t))
        conn.commit()
        return True
    finally:
        conn.close()


def _login_lock_get(email: str) -> tuple[int, float]:
    conn = db()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS ls_login_locks (email TEXT PRIMARY KEY, fails INTEGER DEFAULT 0, locked_until REAL DEFAULT 0)")
        row = conn.execute("SELECT fails, locked_until FROM ls_login_locks WHERE email=?", (email,)).fetchone()
        return (row["fails"], row["locked_until"]) if row else (0, 0.0)
    finally:
        conn.close()


def _login_lock_fail(email: str):
    fails, _ = _login_lock_get(email)
    fails += 1
    locked_until = time.time() + 900 if fails >= 5 else 0.0
    conn = db()
    try:
        conn.execute("INSERT INTO ls_login_locks (email, fails, locked_until) VALUES (?,?,?)"
                     " ON CONFLICT(email) DO UPDATE SET fails=excluded.fails, locked_until=excluded.locked_until",
                     (email, fails, locked_until))
        conn.commit()
    finally:
        conn.close()


def _login_lock_clear(email: str):
    conn = db()
    try:
        conn.execute("DELETE FROM ls_login_locks WHERE email=?", (email,))
        conn.commit()
    finally:
        conn.close()


def _rate_tier(path: str) -> tuple[int, int]:
    """(max_requests, window_seconds) per client IP. Strict for auth, moderate
    for mutations/analysis, lenient for reads."""
    if path.startswith("/api/auth/"):
        return (20, 60)
    if ("/analyze" in path or "/simulate" in path or "/admin/approvals" in path
            or "/admin/config" in path or "/admin/keys" in path or "/documents" in path):
        return (60, 60)
    return (300, 60)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    request.state.rid = rid
    # --- Cookie session -> Authorization header (single choke point) ---
    # Browsers authenticate with the HttpOnly session cookie; API clients use
    # Bearer tokens. Downstream code only understands Bearer, so bridge it here.
    token = None
    authz = request.headers.get("authorization")
    if authz and authz.startswith("Bearer "):
        token = authz[7:].strip() or None
    if not token:
        token = request.cookies.get(SESSION_COOKIE)
    request.state.session_token = token
    if token and not authz:
        try:
            request.scope["headers"].append(
                (b"authorization", f"Bearer {token}".encode("latin-1")))
        except Exception:
            pass
    # Full session gate: absolute expiry, idle window, hijack binding + touch.
    try:
        request.state.session = _validate_session_token(token, request) if token else None
    except Exception:
        request.state.session = None
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        try:
            cl = int(request.headers.get("content-length", "0") or 0)
        except ValueError:
            cl = 0
        if cl > MAX_BODY_BYTES:
            return JSONResponse(
                {"detail": f"Request body too large (limit {MAX_BODY_BYTES} bytes)"},
                status_code=413, headers={"X-Request-ID": rid})
        # --- CSRF gate: cookies ride along automatically, so mutations must
        # not be forgeable by a plain cross-site form post. JSON bodies can't
        # be forged that way; multipart uploads additionally need same-origin.
        # Bodiless POSTs (logout) carry nothing to forge — let them through.
        if cl > 0 and request.url.path.startswith("/api/"):
            ctype = request.headers.get("content-type", "")
            if "application/json" not in ctype and "multipart/form-data" not in ctype:
                return JSONResponse(
                    {"detail": "Requests must use JSON encoding"},
                    status_code=403, headers={"X-Request-ID": rid})
            if "multipart/form-data" in ctype:
                from urllib.parse import urlparse
                origin = request.headers.get("origin") or request.headers.get("referer") or ""
                if origin:
                    oh = urlparse(origin).hostname or ""
                    hh = (request.headers.get("host") or "").split(":")[0]
                    if oh and hh and oh != hh:
                        return JSONResponse(
                            {"detail": "Cross-origin request rejected"},
                            status_code=403, headers={"X-Request-ID": rid})
    p = request.url.path
    if not (p.startswith("/static") or p in ("/docs", "/openapi.json", "/redoc")):
        limit, window = _rate_tier(p)
        host = request.client.host if request.client else "?"
        if not _rate_check(host, limit, window):
            return JSONResponse(
                {"detail": "Rate limit exceeded. Slow down and retry."},
                status_code=429, headers={"X-Request-ID": rid, "Retry-After": "60"})
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = rid
    # Cache policy: hashed build assets are immutable; entry HTML never caches
    # (stale index.html referencing wiped hashed chunks silently kills lazy 3D).
    if p.startswith("/static/assets"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    resp.headers["X-Frame-Options"] = "DENY"
    # HSTS only over real HTTPS (never on local http, which has no TLS).
    # Render/CDN terminate TLS and forward x-forwarded-proto, which counts.
    try:
        from urllib.parse import urlparse as _urlparse
        _proto = (request.headers.get("x-forwarded-proto", "") or "").split(",")[0].strip()
        _is_tls = _proto == "https" or _urlparse(str(request.url)).scheme == "https"
    except Exception:
        _is_tls = False
    if _is_tls:
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    return resp


def _audit_event(action: str, actor: str, detail: dict):
    """Best-effort audit write — must never break the request it records."""
    try:
        from lendsure.notify import audit as _audit_log
        conn = db()
        try:
            _audit_log(conn, "*", None, actor, action, detail)
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

# ---------------- DB ----------------

def db() -> sqlite3.Connection:
    """Single choke point for connections, tuned to SQLite's safe maximum:
    WAL journaling (readers never block writers), foreign-key enforcement,
    and a busy timeout so concurrent requests wait instead of crashing."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return conn


def _apply_migration(conn, name: str, sql: str) -> bool:
    """Run one named migration atomically. Returns True if applied.

    Skips migrations already in the ledger. A 'duplicate column name' error
    on one statement means that statement predates the ledger era: tolerate
    it and continue with the rest. Anything else rolls back and RAISES
    loudly — a half-migrated database must never boot silently.
    (Statement loop, not executescript: the latter force-commits and would
    silently break the atomicity this function promises.)
    """
    if conn.execute("SELECT 1 FROM ls_migrations WHERE name=?", (name,)).fetchone():
        return False
    conn.commit()
    prev_level = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN")
        for st in [s.strip() for s in sql.split(";") if s.strip()]:
            try:
                conn.execute(st)
            except sqlite3.OperationalError as err:
                if "duplicate column name" not in str(err):
                    raise
        conn.execute("INSERT INTO ls_migrations (name, applied_at) VALUES (?,?)",
                     (name, datetime.utcnow().isoformat()))
        conn.execute("COMMIT")
        return True
    except Exception as err:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        print(f"[MIGRATION FAILED] {name}: {err}", flush=True)
        raise
    finally:
        conn.isolation_level = prev_level


def _backfill_audit_chain(conn) -> int:
    """Link pre-chain audit rows (genesis-linked, in id order). Idempotent:
    returns 0 fast when nothing is unchained. Runs at every boot."""
    from lendsure.notify import GENESIS_HASH, chain_hash
    missing = conn.execute(
        "SELECT COUNT(*) c FROM ls_audit WHERE chain_hash IS NULL OR chain_hash=''").fetchone()["c"]
    if not missing:
        return 0
    rows = conn.execute(
        "SELECT id, borrower_id, analysis_id, actor, action, detail, created_at"
        " FROM ls_audit WHERE chain_hash IS NULL OR chain_hash='' ORDER BY id").fetchall()
    prev_row = conn.execute("SELECT chain_hash FROM ls_audit WHERE chain_hash IS NOT NULL"
                            " AND chain_hash != '' ORDER BY id DESC LIMIT 1").fetchone()
    prev = prev_row["chain_hash"] if prev_row else GENESIS_HASH
    n = 0
    for r in rows:
        r = dict(r)
        ch = chain_hash(prev, r["borrower_id"], r["analysis_id"], r["actor"],
                        r["action"], r["detail"] or "", r["created_at"] or "")
        conn.execute("UPDATE ls_audit SET prev_hash=?, chain_hash=? WHERE id=?",
                     (prev, ch, r["id"]))
        prev = ch
        n += 1
    conn.commit()
    if n:
        print(f"[audit] backfilled hash chain for {n} pre-chain rows", flush=True)
    return n


def init_db():
    conn = db()
    try:
        conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            code TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT DEFAULT 'lender',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email_verified INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS email_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            purpose TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ls_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
        )
        # LendSure tables (created if missing; data comes from import scripts)
        conn.executescript(LS_DDL)
        conn.executescript(LIFECYCLE_DDL)
        for _name, _sql in LS_MIGRATIONS:
            _apply_migration(conn, _name, _sql)
        _backfill_audit_chain(conn)
        conn.commit()
    finally:
        conn.close()


init_db()

# LendSure product API (borrowers, analysis, evidence, admin) — real DB-backed routes
from lendsure import api as ls_api  # noqa: E402
from lendsure import finance as fi_api  # noqa: E402
from lendsure import loans as loan_api  # noqa: E402
from lendsure import jobs as jobs_api  # noqa: E402
from lendsure import graph as graph_api  # noqa: E402
from lendsure import notify as notify_api  # noqa: E402


def _ls_session(authorization: Optional[str]) -> Optional[dict]:
    return _session_from_header(authorization)


ls_api.configure(db, _ls_session)
app.include_router(ls_api.router)

fi_api.configure(db, _ls_session)
fi_api.init_fi_db()
app.include_router(fi_api.router)

loan_api.configure(db, _ls_session)
app.include_router(loan_api.router)

jobs_api.configure(db, _ls_session)
jobs_api.start_worker()
app.include_router(jobs_api.router)

graph_api.configure(db, _ls_session)
app.include_router(graph_api.router)

notify_api.configure(db, _ls_session)
app.include_router(notify_api.router)

from lendsure import intel as intel_api  # noqa: E402
intel_api.configure(db, _ls_session)
app.include_router(intel_api.router)

from lendsure import simulate as sim_api  # noqa: E402
sim_api.configure(db, _ls_session)
app.include_router(sim_api.router)

from lendsure import recovery as rec_api  # noqa: E402
rec_api.configure(db, _ls_session)
app.include_router(rec_api.router)

from lendsure import grievance as grv_api  # noqa: E402
grv_api.configure(db, _ls_session)
app.include_router(grv_api.router)

from lendsure import credit_risk as cr_api  # noqa: E402
cr_api.configure(db, _ls_session)
app.include_router(cr_api.router)

from lendsure import assistant as asst_api  # noqa: E402
asst_api.configure(db, _ls_session)
app.include_router(asst_api.router)

class OtpRequestIn(BaseModel):
    phone: str
    name: str = ""


class OtpVerifyIn(BaseModel):
    phone: str
    otp: str
    name: str = ""


class GuestIn(BaseModel):
    name: str = "Guest"


# Phone OTP delivery. In production, Twilio Verify generates and validates the
# code server-side. Demo mode is opt-in and must never be enabled in production.
# NOTE (operator): the local otps row enforces OTP_TTL_MIN, so keep the Twilio
# Verify Service "time to live" at or above OTP_TTL_MIN, or users will see
# local expiry for still-valid Twilio codes. Numbers are India (+91) only —
# the 10-digit validation upstream guarantees that shape.
DEMO_OTP = os.environ.get("LENDSURE_DEMO_OTP", "0") == "1"
OTP_TTL_MIN = max(1, int(os.environ.get("LENDSURE_OTP_TTL_MIN", "5")))
TWILIO_OTP_MARKER = "__twilio_verify__"

def _otp_len() -> int:
    from lendsure.otp import code_length
    return code_length()

def _twilio_configured() -> bool:
    return (
        os.environ.get("LENDSURE_SMS_PROVIDER", "twilio").strip().lower() == "twilio"
        and bool(os.environ.get("TWILIO_ACCOUNT_SID", "").strip())
        and bool(os.environ.get("TWILIO_AUTH_TOKEN", "").strip())
        and bool(os.environ.get("TWILIO_VERIFY_SERVICE_SID", "").strip())
    )

def _phone_e164(phone: str) -> str:
    return f"+91{phone}"

def _twilio_verify_post(resource: str, fields: dict[str, str]) -> Optional[dict]:
    """Call Twilio Verify without exposing credentials or OTPs to the client."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    service_sid = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "").strip()
    if not account_sid or not auth_token or not service_sid:
        return None
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    request = UrlRequest(
        f"https://verify.twilio.com/v2/Services/{service_sid}/{resource}",
        data=urlencode(fields).encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("message", "provider rejected request")
        except Exception:
            detail = "provider rejected request"
        print(f"[Twilio] Verify {resource} failed ({exc.code}): {detail}", flush=True)
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"[Twilio] Verify {resource} unavailable: {exc}", flush=True)
    return None

def send_sms_otp(phone: str) -> bool:
    result = _twilio_verify_post("Verifications", {"To": _phone_e164(phone), "Channel": "sms"})
    return bool(result and result.get("status") in {"pending", "approved"})

def check_sms_otp(phone: str, code: str) -> Optional[bool]:
    result = _twilio_verify_post(
        "VerificationCheck", {"To": _phone_e164(phone), "Code": code}
    )
    if result is None:
        return None
    return result.get("status") == "approved"

# ---------------- Persistent sessions + inactivity timeout ----------------
# Browser sessions live in an HttpOnly SameSite cookie; the server owns all
# state (absolute expiry + sliding inactivity window). localStorage/JS never
# holds anything that can authenticate — it only caches display profile.
SESSION_COOKIE = "lendsure_session"
IDLE_TIMEOUT_SEC = int(os.environ.get("LENDSURE_IDLE_TIMEOUT_SEC", "300"))
IDLE_TIMEOUT_SEC = max(30, IDLE_TIMEOUT_SEC)  # floor so tests can shrink it
TOUCH_THROTTLE_SEC = 30  # refresh last_active at most this often (write thrift)


def _validate_runtime_config() -> None:
    """Reject unsafe production settings before the service accepts traffic."""
    if RUNTIME_ENV not in {"development", "test", "staging", "production"}:
        raise RuntimeError("LENDSURE_ENV must be development, test, staging, or production")
    if RUNTIME_ENV == "production" and DEMO_OTP:
        raise RuntimeError("LENDSURE_DEMO_OTP=1 is not allowed when LENDSURE_ENV=production")
    if RUNTIME_ENV == "production" and "*" in CORS_ORIGINS:
        raise RuntimeError("Wildcard CORS is not allowed when LENDSURE_ENV=production")
    if RUNTIME_ENV == "production" and not LIVE_DB_PATH.is_absolute():
        raise RuntimeError("LENDSURE_DB_PATH must be an absolute path in production")


_validate_runtime_config()


# ---------------- API ----------------
@app.get("/api/health")
def health():
    return {"ok": True, "service": "lendsure-api", "version": app.version,
            "environment": RUNTIME_ENV, "time": datetime.utcnow().isoformat()}


# ---------------- Auth (OTP + guest) ----------------

def _now() -> datetime:
    return datetime.utcnow()


def _session_from_header(authorization: Optional[str]) -> Optional[dict]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    conn = db()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not row:
            return None
        s = dict(row)
        if s["expires_at"] < _now().isoformat():
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return None
        # Idle window is enforced here too (no touch — the middleware owns that),
        # so direct callers can never resurrect a timed-out session.
        last = s.get("last_active") or s.get("created_at")
        if (not s.get("remember") and last
                and last < (_now() - timedelta(seconds=IDLE_TIMEOUT_SEC)).isoformat()):
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return None
        return s
    finally:
        conn.close()


def _client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _ua_hash(request: Request | None) -> str:
    if request is None:
        return ""
    return hashlib.sha256((request.headers.get("user-agent", "") or "").encode()).hexdigest()[:32]


def _device_hash(request: Request | None) -> str:
    """Stable-ish device fingerprint: browser UA + client IP."""
    if request is None:
        return ""
    ua = request.headers.get("user-agent", "") or ""
    return hashlib.sha256(f"{ua}|{_client_ip(request)}".encode()).hexdigest()[:32]


def _is_https(request: Request) -> bool:
    if (request.headers.get("x-forwarded-proto", "") or "").split(",")[0].strip() == "https":
        return True
    return request.url.scheme == "https"


def _validate_session_token(token: str | None, request: Request | None = None) -> Optional[dict]:
    """Full session gate used by the middleware on every request.

    Enforces absolute expiry, then the sliding inactivity window (each login
    gets an independent timer that refreshes on authenticated activity),
    then hijack binding (IP *and* UA both changed => kill). Refreshes
    last_active, throttled to TOUCH_THROTTLE_SEC to spare the DB.
    """
    if not token:
        return None
    conn = db()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not row:
            return None
        s = dict(row)
        now = _now()
        if s["expires_at"] < now.isoformat():
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return None
        last = s.get("last_active") or s.get("created_at")
        # Remembered (email-signup) sessions never idle-expire: sign up once,
        # stay signed in. Phone-OTP and guest sessions keep the idle window.
        if (not s.get("remember") and last
                and last < (now - timedelta(seconds=IDLE_TIMEOUT_SEC)).isoformat()):
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            _audit_event("auth_idle_expired",
                         f"{s.get('display_name', '?')} ({s.get('phone', '?')})", {})
            return None
        if request is not None:
            cur_ip, cur_ua = _client_ip(request), _ua_hash(request)
            if not s.get("ua_hash") or not s.get("ip"):
                # Legacy session: adopt the binding on first contact.
                conn.execute("UPDATE sessions SET ip=?, ua_hash=?, last_active=? WHERE token=?",
                             (cur_ip, cur_ua, now.isoformat(), token))
                conn.commit()
            else:
                if s["ua_hash"] != cur_ua and s["ip"] != cur_ip:
                    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
                    conn.commit()
                    _audit_event("auth_hijack_killed",
                                 f"{s.get('display_name', '?')} ({s.get('phone', '?')})",
                                 {"ip": cur_ip})
                    return None
                if not last or last < (now - timedelta(seconds=TOUCH_THROTTLE_SEC)).isoformat():
                    conn.execute("UPDATE sessions SET last_active=? WHERE token=?",
                                 (now.isoformat(), token))
                    conn.commit()
        return s
    finally:
        conn.close()


def _make_session(phone: str, display_name: str, role: str, days: int, email: str = "",
                  request: Request | None = None, device_hash: str = "",
                  remember: bool = False) -> tuple[dict, str]:
    """Create a session row. Returns (public profile, raw token).
    The token is NEVER returned to browsers in a body — it travels out in
    the HttpOnly session cookie only. remember=True marks an email-signup
    lender session that never idle-expires (stays signed in)."""
    token = secrets.token_urlsafe(32)
    now = _now()
    conn = db()
    try:
        conn.execute(
            "INSERT INTO sessions (token, phone, display_name, role, created_at, expires_at, email,"
            " last_active, ip, ua_hash, device_hash, remember) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (token, phone, display_name, role, now.isoformat(),
             (now + timedelta(days=days)).isoformat(), email, now.isoformat(),
             _client_ip(request), _ua_hash(request), device_hash, int(remember)),
        )
        conn.commit()
    finally:
        conn.close()
    return ({"display_name": display_name, "phone": phone, "role": role, "email": email}, token)


def _set_session_cookie(response: Response, request: Request, token: str, days: int):
    response.set_cookie(SESSION_COOKIE, token, max_age=days * 86400, httponly=True,
                        samesite="lax", secure=_is_https(request), path="/")


def _clear_session_cookie(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


def _record_device(conn, email: str, request: Request | None, verified: int):
    dh = _device_hash(request)
    if not dh:
        return
    ts = _now().isoformat()
    conn.execute("INSERT INTO ls_devices (email, device_hash, verified, first_seen, last_seen)"
                 " VALUES (?,?,?,?,?) ON CONFLICT(email, device_hash) DO UPDATE SET"
                 " verified=max(verified, excluded.verified), last_seen=excluded.last_seen",
                 (email, dh, verified, ts, ts))


def _device_verified(conn, email: str, request: Request | None) -> bool:
    dh = _device_hash(request)
    if not dh:
        return False
    row = conn.execute("SELECT verified FROM ls_devices WHERE email=? AND device_hash=?",
                       (email, dh)).fetchone()
    return bool(row and row["verified"])


@app.get("/api/auth/otp-config")
def otp_config():
    """Public OTP policy (lengths, cooldowns) so clients render correctly.
    Contains no secrets — codes and delivery state never leave here."""
    from lendsure.otp import code_length, COOLDOWN_SEC, MAX_ATTEMPTS
    return {"otp_len": code_length(), "cooldown_sec": COOLDOWN_SEC,
            "ttl_min": OTP_TTL_MIN, "max_attempts": MAX_ATTEMPTS}


@app.get("/api/auth/email-status")
def email_status():
    """Delivery diagnostics (no secrets): tells the UI/operator whether email
    OTP can actually send right now, and why not if it can't."""
    user = "".join(os.environ.get("LENDSURE_SMTP_USER", "").split())
    return {"smtp_configured": _smtp_configured(),
            "sendgrid_configured": _sendgrid_configured(),
            "email_configured": _email_configured(),
            "demo_otp": DEMO_OTP,
            "smtp_user_set": bool(user),
            "smtp_domain": user.split("@")[-1] if "@" in user else ""}


@app.post("/api/auth/request-otp")
def request_otp(payload: OtpRequestIn):
    phone = payload.phone.strip()
    if not re.match(r"^\d{10}$", phone):
        raise HTTPException(400, "Enter a valid 10-digit mobile number")
    live_sms = _twilio_configured()
    if not live_sms and not DEMO_OTP:
        raise HTTPException(503, "SMS delivery is not configured on this server.")
    conn = db()
    otp_id = None
    try:
        from lendsure.otp import issue as _otp_issue
        # One path for caps/cooldown/storage; Twilio mode stores a marker
        # because the real code lives with the provider, not with us.
        code = _otp_issue(conn, "phone", phone, ttl_min=OTP_TTL_MIN,
                          code_override=TWILIO_OTP_MARKER if live_sms else None)
        otp_id = conn.execute("SELECT id FROM otps WHERE phone=? ORDER BY id DESC LIMIT 1",
                              (phone,)).fetchone()["id"]
        conn.commit()
    finally:
        conn.close()
    if live_sms and not send_sms_otp(phone):
        conn = db()
        try:
            conn.execute("DELETE FROM otps WHERE id=?", (otp_id,))
            conn.commit()
        finally:
            conn.close()
        raise HTTPException(503, "We could not send the SMS right now. Please try again.")
    if DEMO_OTP and not live_sms and os.environ.get("LENDSURE_LOG_CODES") == "1":
        print(f"[OTP] {phone} -> {code} (valid {OTP_TTL_MIN} min)", flush=True)
    resp: dict[str, Any] = {
        "ok": True,
        "message": f"OTP sent to +91 {phone}",
        "expires_in_sec": OTP_TTL_MIN * 60,
        "retry_after_sec": 60,
        "otp_len": _otp_len(),
    }
    if DEMO_OTP and not live_sms:
        resp["demo_otp"] = code
        resp["message"] += " (demo mode: code shown on screen)"
    return resp


@app.post("/api/auth/verify-otp")
def verify_otp(payload: OtpVerifyIn, request: Request, response: Response):
    phone = payload.phone.strip()
    code = payload.otp.strip()
    otp_len = _otp_len()
    if not re.match(r"^\d{10}$", phone) or len(code) != otp_len or not code.isdigit():
        raise HTTPException(400, "Invalid phone or OTP format")
    conn = db()
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT * FROM otps WHERE phone=? ORDER BY id DESC LIMIT 1", (phone,)
        ).fetchone()
        if not row or row["expires_at"] <= _now().isoformat():
            raise HTTPException(400, "OTP expired or not found. Request a new one.")
        if row["attempts"] >= 5:
            cur.execute("DELETE FROM otps WHERE id=?", (row["id"],))
            conn.commit()
            raise HTTPException(400, "Too many wrong attempts. Request a new OTP.")
        if row["code"] == TWILIO_OTP_MARKER:
            verified = check_sms_otp(phone, code)
            if verified is None:
                raise HTTPException(503, "SMS verification is temporarily unavailable. Please try again.")
        else:
            verified = secrets.compare_digest(row["code"], code)
        if not verified:
            cur.execute("UPDATE otps SET attempts = attempts + 1 WHERE id=?", (row["id"],))
            conn.commit()
            remaining = 5 - row["attempts"] - 1
            raise HTTPException(400, f"Wrong OTP. {remaining} attempt(s) left.")
        cur.execute("DELETE FROM otps WHERE id=?", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    name = payload.name.strip() or f"Lender {phone[-4:]}"
    profile, token = _make_session(phone, name, "lender", 7, request=request)
    _set_session_cookie(response, request, token, 7)
    _audit_event("auth_login", f"{name} ({phone})", {"method": "otp"})
    return {"ok": True, **profile}


@app.post("/api/auth/guest")
def guest_login(payload: GuestIn, request: Request, response: Response):
    name = payload.name.strip() or "Guest"
    profile, token = _make_session("guest", name, "guest", 1, request=request)
    _set_session_cookie(response, request, token, 1)
    _audit_event("auth_login", f"{name} (guest)", {"method": "guest"})
    return {"ok": True, **profile}


# ---------------- Email auth: password + real Gmail OTP ----------------
# Passwords: PBKDF2-HMAC-SHA256 (stdlib, 600k iterations, per-user salt).
# OTP codes: emailed through Gmail SMTP when LENDSURE_SMTP_* is configured
# (use a Gmail App Password, never your login password); otherwise the code
# is returned in the API response so the demo flow still works.

EMAIL_OTP_TTL_MIN = 10
# Login-attempt throttling lives in ls_login_locks (SQLite) — see _login_lock_* helpers.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _smtp_configured() -> bool:
    return bool("".join(os.environ.get("LENDSURE_SMTP_USER", "").split())
                and "".join(os.environ.get("LENDSURE_SMTP_APP_PASSWORD", "").split()))


def _sendgrid_configured() -> bool:
    return bool((os.environ.get("SENDGRID_API_KEY") or "").strip())


def _email_configured() -> bool:
    return _sendgrid_configured() or _smtp_configured()


def _send_via_sendgrid(to_email: str, code: str, purpose: str) -> bool:
    """HTTPS email API (port 443) for hosts that block outbound SMTP
    (e.g. Render free tier: smtp.gmail.com is unreachable from there).
    Stdlib only. Returns True on 2xx from the SendGrid v3 API."""
    import urllib.request
    api_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
    sender = "".join(os.environ.get("LENDSURE_SMTP_USER", "").split())
    if not api_key or not sender:
        return False
    action = ("verify your email address" if purpose == "verify"
              else "confirm it's you on this device" if purpose == "login"
              else "reset your password")
    body = json.dumps({
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": sender, "name": "LendSure"},
        "subject": f"Your LendSure verification code is {code}",
        "content": [{"type": "text/plain",
                     "value": (f"Your LendSure verification code is: {code}\n\n"
                               f"Use it to {action}. It expires in {EMAIL_OTP_TTL_MIN} minutes.\n\n"
                               "If you didn't request this, you can safely ignore this email.")}],
    }).encode()
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}",
                 "User-Agent": "LendSure/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            detail = ""
        print(f"[SendGrid] send failed for {to_email}: HTTP {e.code} {detail}", flush=True)
        return False
    except Exception as e:
        print(f"[SendGrid] send failed for {to_email}: {e}", flush=True)
        return False


def send_email_otp(to_email: str, code: str, purpose: str) -> bool:
    # App passwords are displayed in spaced groups — strip all whitespace
    # so a pasted-with-spaces password still authenticates.
    user = "".join(os.environ.get("LENDSURE_SMTP_USER", "").split())
    pwd = "".join(os.environ.get("LENDSURE_SMTP_APP_PASSWORD", "").split())
    host = os.environ.get("LENDSURE_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("LENDSURE_SMTP_PORT", "587"))
    # Preferred on hosted networks: HTTPS API first (Render blocks SMTP ports).
    if _sendgrid_configured() and user:
        if _send_via_sendgrid(to_email, code, purpose):
            return True
        print("[email] SendGrid failed, falling back to SMTP", flush=True)
    if not user or not pwd:
        if DEMO_OTP and os.environ.get("LENDSURE_LOG_CODES") == "1":
            print(f"[EMAIL-OTP] {to_email} -> {code} ({purpose}) — SMTP not configured, demo mode", flush=True)
        return False
    try:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"] = f"LendSure <{user}>"
        msg["To"] = to_email
        action = ("verify your email address" if purpose == "verify"
                  else "confirm it's you on this device" if purpose == "login"
                  else "reset your password")
        msg["Subject"] = f"Your LendSure verification code is {code}"
        msg.set_content(
            f"Your LendSure verification code is: {code}\n\n"
            f"Use it to {action}. It expires in {EMAIL_OTP_TTL_MIN} minutes.\n\n"
            "If you didn't request this, you can safely ignore this email.")
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[SMTP] send failed for {to_email}: {e}", flush=True)
        return False


def _argon_hasher():
    """Argon2id hasher, or None when the optional dependency is absent."""
    try:
        from argon2 import PasswordHasher
        return PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
    except Exception:
        return None


def _hash_password(password: str) -> str:
    ph = _argon_hasher()
    if ph is not None:
        return ph.hash(password)
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2$600000${salt.hex()}${dk.hex()}"


# Blocklisted passwords: the most abused choices. Checked on register + reset.
COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "12345678", "123456789", "1234567890",
    "qwerty", "qwerty123", "abc12345", "letmein", "welcome", "welcome1",
    "monkey", "dragon", "football", "baseball", "superman", "trustno1",
    "lendsure", "lendsure123", "admin123", "user1234", "test1234", "abcd1234",
    "p@ssw0rd", "passw0rd", "changeme", "default", "login123", "master123",
    "qazwsxedc", "1q2w3e4r", "aa123456", "india123", "mumbai123", "delhi123",
    "iloveyou", "princess", "sunshine", "shadow", "654321", "87654321",
})


def _password_problem(password: str) -> str | None:
    """None when acceptable, else the human-readable reason."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if len(password) > 128:
        # Memory-hard hashing (Argon2id) makes giant inputs a CPU-DoS vector.
        return "Password must be at most 128 characters"
    if not re.search(r"[A-Za-z]", password):
        return "Password must contain at least one letter"
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number"
    if password.lower() in COMMON_PASSWORDS:
        return "That password is too common — choose a less predictable one"
    return None


def _unsent_code_or_503(sent: bool, code: str) -> dict:
    """Fail-secure delivery accounting for email/SMS codes.

    Delivered -> {}. Undelivered in demo mode -> echo the code (the documented
    demo feature). Undelivered in production -> 503, never the code."""
    if sent:
        return {}
    if DEMO_OTP:
        return {"demo_otp": code}
    raise HTTPException(503, "Verification code could not be delivered. Contact the administrator.")


def _check_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("$argon2id$"):
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError
            try:
                PasswordHasher().verify(stored, password)
                return True
            except VerifyMismatchError:
                return False
        algo, iters, salt, dk = stored.split("$")
        if algo != "pbkdf2":
            return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return secrets.compare_digest(test.hex(), dk)
    except Exception:
        return False


def _hash_needs_upgrade(stored: str) -> bool:
    """True for legacy PBKDF2 hashes when Argon2id is available: callers
    re-hash transparently on the next successful password login."""
    return stored.startswith("pbkdf2$") and _argon_hasher() is not None


def _issue_email_otp(conn, email: str, purpose: str) -> str:
    """Thin wrapper: identical behavior, centralized in lendsure.otp."""
    from lendsure.otp import issue as _otp_issue
    return _otp_issue(conn, "email", email, purpose, ttl_min=EMAIL_OTP_TTL_MIN)


def _check_email_otp(conn, email: str, purpose: str, code: str) -> None:
    """Thin wrapper: identical behavior, centralized in lendsure.otp."""
    from lendsure.otp import check as _otp_check
    _otp_check(conn, "email", email, code, purpose)


class RegisterIn(BaseModel):
    name: str = ""
    email: str
    password: str
    phone: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class VerifyEmailIn(BaseModel):
    email: str
    otp: str


class ResendIn(BaseModel):
    email: str


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    email: str
    otp: str
    new_password: str


@app.post("/api/auth/register")
def register(payload: RegisterIn, request: Request):
    """Password-only signup: Gmail + password saves the account (verified).
    No session is created here — the user signs in on the Sign in tab,
    where the password is checked. No OTP anywhere."""
    email = payload.email.strip().lower()
    name = payload.name.strip() or email.split("@")[0]
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address")
    if (reason := _password_problem(payload.password)) is not None:
        raise HTTPException(400, reason)
    if len(name) > 60:
        raise HTTPException(400, "Name too long")
    phone = "".join(ch for ch in (payload.phone or "") if ch.isdigit())
    if phone and len(phone) != 10:
        raise HTTPException(400, "Phone must be a 10-digit mobile number")
    conn = db()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(400, "Account already exists — just sign in.")
        conn.execute(
            "INSERT INTO users (name, email, password_hash, email_verified, created_at, phone) VALUES (?,?,?,?,?,?)",
            (name, email, _hash_password(payload.password), 1, _now().isoformat(), phone))
        _record_device(conn, email, request, verified=1)
        conn.commit()
    finally:
        conn.close()
    _audit_event("auth_register", f"{name} ({email})", {})
    return {"ok": True, "email": email,
            "message": "Account created — sign in with your email and password."}


@app.post("/api/auth/resend-code")
def resend_code(payload: ResendIn):
    """Resend a registration verification code (unverified accounts only)."""
    email = payload.email.strip().lower()
    conn = db()
    try:
        row = conn.execute("SELECT email_verified FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            raise HTTPException(400, "Account not found. Please register first.")
        if row["email_verified"]:
            raise HTTPException(400, "Email already verified — just sign in.")
        recent = conn.execute(
            "SELECT created_at FROM email_otps WHERE email=? AND purpose='verify'"
            " ORDER BY id DESC LIMIT 1", (email,)).fetchone()
        if recent and recent["created_at"] > (_now() - timedelta(seconds=60)).isoformat():
            raise HTTPException(429, "A code was just sent — check your inbox (or wait a minute to resend).")
        code = _issue_email_otp(conn, email, "verify")
        conn.commit()
    finally:
        conn.close()
    sent = send_email_otp(email, code, "verify")
    resp: dict[str, Any] = {"ok": True, "email": email, "email_sent": sent}
    if not sent:
        resp.update(_unsent_code_or_503(sent, code))
    return resp


@app.post("/api/auth/verify-email")
def verify_email(payload: VerifyEmailIn, request: Request, response: Response):
    email = payload.email.strip().lower()
    conn = db()
    try:
        _check_email_otp(conn, email, "verify", payload.otp.strip())
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            raise HTTPException(400, "Account not found. Please register first.")
        conn.execute("UPDATE users SET email_verified=1 WHERE email=?", (email,))
        # Registration proves this device: future logins skip OTP on it.
        _record_device(conn, email, request, verified=1)
        conn.commit()
        name = row["name"]
    finally:
        conn.close()
    profile, token = _make_session(email, name, "lender", 365, email=email,
                                   request=request, device_hash=_device_hash(request),
                                   remember=True)
    _set_session_cookie(response, request, token, 365)
    _audit_event("auth_login", f"{name} ({email})", {"method": "email-register"})
    return {"ok": True, **profile}


@app.post("/api/auth/login")
def email_login(payload: LoginIn, request: Request, response: Response):
    """Email + Password only. Matching credentials sign straight in on any
    device with a remembered (never-expiring) session. No OTP anywhere."""
    email = payload.email.strip().lower()
    _, locked_until = _login_lock_get(email)
    if locked_until > time.time():
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    conn = db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        row = dict(row) if row else None
    finally:
        conn.close()
    if not row or not _check_password(payload.password, row["password_hash"]):
        _login_lock_fail(email)
        raise HTTPException(401, "Incorrect email or password")
    _login_lock_clear(email)
    conn = db()
    try:
        _record_device(conn, email, request, verified=1)
        if _hash_needs_upgrade(row["password_hash"]):
            # Transparent upgrade: legacy PBKDF2 hash becomes Argon2id now
            # that the user proved the password. No UX impact.
            conn.execute("UPDATE users SET password_hash=? WHERE email=?",
                         (_hash_password(payload.password), email))
        conn.commit()
    finally:
        conn.close()
    profile, token = _make_session(email, row["name"], "lender", 365, email=email,
                                   request=request, device_hash=_device_hash(request),
                                   remember=True)
    _set_session_cookie(response, request, token, 365)
    _audit_event("auth_login", f"{row['name']} ({email})", {"method": "email-password"})
    return {"ok": True, **profile}


class VerifyLoginIn(BaseModel):
    email: str
    otp: str


@app.post("/api/auth/verify-login")
def verify_login(payload: VerifyLoginIn, request: Request, response: Response):
    """Complete a new-device login: correct inbox code verifies the device,
    then behaves exactly like a normal login (fresh 5-minute timer)."""
    email = payload.email.strip().lower()
    conn = db()
    try:
        _check_email_otp(conn, email, "login", payload.otp.strip())
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            raise HTTPException(400, "Account not found.")
        row = dict(row)
        _record_device(conn, email, request, verified=1)
        conn.commit()
    finally:
        conn.close()
    profile, token = _make_session(email, row["name"], "lender", 365, email=email,
                                   request=request, device_hash=_device_hash(request),
                                   remember=True)
    _set_session_cookie(response, request, token, 365)
    _audit_event("auth_login", f"{row['name']} ({email})", {"method": "email-password-new-device"})
    return {"ok": True, **profile}


@app.post("/api/auth/forgot-password")
def forgot_password(payload: ForgotIn):
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address")
    conn = db()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
        code = _issue_email_otp(conn, email, "reset") if exists else None
    finally:
        conn.close()
    sent = send_email_otp(email, code, "reset") if code else False
    # Same response whether or not the account exists (no user enumeration).
    # A 503 here would itself be an oracle, so delivery failure stays neutral
    # and is shouted into the server log for the operator instead.
    resp: dict[str, Any] = {"ok": True, "email_sent": sent,
                            "message": "If an account exists for this email, a reset code was sent."}
    if code and not sent:
        if DEMO_OTP:
            resp["demo_otp"] = code
        else:
            print(f"[SMTP] password-reset code for {email} could NOT be delivered — SMTP unconfigured", flush=True)
    return resp


@app.post("/api/auth/reset-password")
def reset_password(payload: ResetIn):
    email = payload.email.strip().lower()
    if (reason := _password_problem(payload.new_password)) is not None:
        raise HTTPException(400, reason)
    conn = db()
    try:
        _check_email_otp(conn, email, "reset", payload.otp.strip())
        if not conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(400, "Account not found.")
        conn.execute("UPDATE users SET password_hash=? WHERE email=?",
                     (_hash_password(payload.new_password), email))
        # Sign out everywhere after a password change.
        conn.execute("DELETE FROM sessions WHERE phone=? OR email=?", (email, email))
        # Security event: every device must re-verify with an inbox code.
        conn.execute("UPDATE ls_devices SET verified=0 WHERE email=?", (email,))
        conn.commit()
    finally:
        conn.close()
    _login_lock_clear(email)
    _audit_event("auth_password_reset", email, {})
    return {"ok": True, "message": "Password updated. Please sign in again."}


@app.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)):
    s = _session_from_header(authorization)
    if not s:
        raise HTTPException(401, "Not signed in")
    return {"ok": True, "phone": s["phone"], "display_name": s["display_name"], "role": s["role"]}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response,
                authorization: Optional[str] = Header(default=None)):
    # Session can arrive via cookie (browsers) or Bearer (API clients).
    tok = None
    if authorization and authorization.startswith("Bearer "):
        tok = authorization[7:].strip() or None
    if not tok:
        tok = request.cookies.get(SESSION_COOKIE)
    s = _session_from_header(f"Bearer {tok}") if tok else None
    if tok:
        conn = db()
        try:
            conn.execute("DELETE FROM sessions WHERE token=?", (tok,))
            conn.commit()
        finally:
            conn.close()
    _clear_session_cookie(response)
    if s:
        _audit_event("auth_logout", f"{s['display_name']} ({s['phone']})", {})
    return {"ok": True}


def _my_session_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip() or None
    return request.cookies.get(SESSION_COOKIE)


@app.get("/api/auth/sessions")
def my_sessions(request: Request, authorization: Optional[str] = Header(default=None)):
    """My active sessions for the Security Center. Full tokens never leave
    the server — only metadata plus which row is this call."""
    tok = _my_session_token(request, authorization)
    s = _session_from_header(f"Bearer {tok}") if tok else None
    if not s:
        raise HTTPException(401, "Not signed in")
    key_email = (s.get("email") or "").strip().lower()
    key_phone = (s.get("phone") or "").strip()
    conn = db()
    try:
        rows = conn.execute(
            "SELECT token, display_name, role, created_at, last_active, ip, remember"
            " FROM sessions WHERE email=? OR phone=? ORDER BY last_active DESC",
            (key_email, key_phone)).fetchall()
    finally:
        conn.close()
    return {"ok": True, "sessions": [
        {"current": r["token"] == tok,
         "display_name": r["display_name"], "role": r["role"],
         "created_at": r["created_at"], "last_active": r["last_active"],
         "ip": r["ip"], "remembered": bool(r["remember"])}
        for r in rows]}


@app.post("/api/auth/sessions/revoke-all")
def revoke_all_sessions(request: Request, response: Response,
                        authorization: Optional[str] = Header(default=None)):
    """Sign out everywhere else: kills all my sessions except this one."""
    tok = _my_session_token(request, authorization)
    s = _session_from_header(f"Bearer {tok}") if tok else None
    if not s:
        raise HTTPException(401, "Not signed in")
    key_email = (s.get("email") or "").strip().lower()
    key_phone = (s.get("phone") or "").strip()
    conn = db()
    try:
        cur = conn.execute("DELETE FROM sessions WHERE (email=? OR phone=?) AND token!=?",
                           (key_email, key_phone, tok))
        conn.commit()
        n = cur.rowcount
    finally:
        conn.close()
    _audit_event("auth_revoke_all", f"{s.get('display_name', '?')} ({key_email or key_phone})",
                 {"revoked": n})
    return {"ok": True, "revoked": n}


@app.get("/api/security/status")
def security_status():
    """Real control state — UNKNOWN means not implemented, never faked."""
    conn = db()
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        audit_n = conn.execute("SELECT COUNT(*) c FROM ls_audit").fetchone()["c"] if "ls_audit" in tables else 0
    finally:
        conn.close()
    try:
        from lendsure import ml as _ml
        ml_loaded, ml_id = bool(_ml.loaded()), getattr(_ml, "MODEL_ID", "unknown")
    except Exception:
        ml_loaded, ml_id = False, "unknown"
    return {
        "authentication": {"otp": True, "guest": True, "demo_otp_mode": DEMO_OTP,
                           "otp_ttl_min": OTP_TTL_MIN,
                           "email_password": "pbkdf2-sha256",
                           "email_otp": "gmail-smtp" if _smtp_configured() else "demo-mode",
                           "passwords": ("argon2id" if _argon_hasher() is not None
                                           else "pbkdf2-sha256 (argon2id unavailable)"),
                           "sessions": "httponly-samesite-cookies, server-side",
                           "idle_timeout_sec": IDLE_TIMEOUT_SEC,
                           "device_otp": "first-login and new-device inbox verification",
                           "hijack_binding": "session dies when both IP and browser change",
                           "csrf": "json-body gate + same-origin multipart check",
                           "mfa": "email-otp-on-new-device"},
        "rbac": {"enabled": True, "roles": ["lender", "guest", "service(api-key)"],
                 "note": "guests are read/analyze-only; policy, reviews, keys and sessions require lender or service role"},
        "rate_limiting": {"enabled": True, "auth_per_min_per_ip": 20,
                          "mutations_per_min_per_ip": 60, "reads_per_min_per_ip": 300},
        "cors": {"mode": "open" if "*" in CORS_ORIGINS else "restricted", "origins": CORS_ORIGINS},
        "headers": {"csp": True, "nosniff": True, "frame_deny": True, "referrer_policy": True},
        "body_limit_bytes": MAX_BODY_BYTES,
        "database": {"ok": True, "tables": len(tables), "encryption_at_rest": "unknown"},
        "ml": {"loaded": ml_loaded, "model_id": ml_id},
        "audit": {"enabled": True, "append_only": True, "events": audit_n, "hash_chaining": "not_configured"},
        "backups": {"status": "unknown"},
        "document_malware_scan": {"status": "not_configured"},
    }


@app.get("/api/ready")
def readiness():
    conn = db()
    try:
        ok_db = conn.execute("SELECT 1").fetchone() is not None
        has_tables = conn.execute(
            "SELECT COUNT(*) c FROM sqlite_master WHERE type='table' AND name LIKE 'ls_%'").fetchone()["c"] > 0
    except Exception:
        ok_db, has_tables = False, False
    finally:
        try:
            conn.close()
        except Exception:
            pass
    try:
        from lendsure import ml as _ml
        ok_ml = bool(_ml.loaded())
    except Exception:
        ok_ml = False
    ready = ok_db and has_tables and ok_ml
    return {"ready": ready, "checks": {"database": ok_db, "tables": has_tables, "ml_model": ok_ml}}


# ---------------- Frontend ----------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx), headers={"Cache-Control": "no-store"})
    return {"message": "API running. Build the frontend (backend/static/index.html) to view dashboard.", "docs": "/docs"}


@app.get("/favicon.svg")
def favicon():
    f = STATIC_DIR / "favicon.svg"
    if f.exists():
        return FileResponse(str(f), media_type="image/svg+xml")
    raise HTTPException(status_code=404)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """SPA fallback: serve index.html for client-side routes (non-API, non-static)."""
    if full_path.startswith("api/") or full_path.startswith("static/") or full_path.startswith("docs") or full_path.startswith("openapi"):
        raise HTTPException(status_code=404)
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx), headers={"Cache-Control": "no-store"})
    return {"message": "Not found", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
