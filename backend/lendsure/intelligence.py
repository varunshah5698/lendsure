from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator

from .cashflow_intelligence import (
    CATEGORIES, MAX_CSV_BYTES, MAX_RECORDS, CashflowRecord, SandboxAccountProvider,
    account_provider, extract_features, fingerprint, normalized_record, parse_statement,
    summarize, transfer_categories,
)
from .credit_bureau import (
    ProviderUnavailable, SandboxCreditProvider, credit_provider, demo_enabled, normalize_report,
)
from .notify import audit


_DB = None
_RESOLVE = None
_ENV = None
_TRANSFERS = None
PURPOSE = "cashflow_assessment"


def configure(db_factory, session_resolver, environment=None):
    global _DB, _RESOLVE, _ENV, _TRANSFERS
    env = dict(os.environ if environment is None else environment)
    raw = env.get("LENDSURE_INTELLIGENCE_TRANSFER_CATEGORIES")
    categories = transfer_categories(json.loads(raw) if raw is not None else None)
    _DB, _RESOLVE, _ENV, _TRANSFERS = db_factory, session_resolver, env, categories


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def principal_for(session: dict | None) -> str | None:
    if not session:
        return None
    user_id = session.get("user_id", session.get("id"))
    if user_id is not None and not isinstance(user_id, bool) and str(user_id).strip():
        return "user:" + str(user_id).strip()
    email = str(session.get("email") or "").strip().casefold()
    if not email and "@" in str(session.get("phone") or ""):
        email = str(session["phone"]).strip().casefold()
    if email and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return "email:" + hashlib.sha256(email.encode()).hexdigest()
    phone = str(session.get("phone") or "").strip()
    if not re.fullmatch(r"[+\d ()-]+", phone):
        return None
    phone = re.sub(r"\D", "", phone)
    if len(phone) == 10:
        phone = "91" + phone
    if phone.startswith("00"):
        phone = phone[2:]
    if not 10 <= len(phone) <= 15:
        return None
    return "phone:" + hashlib.sha256(phone.encode()).hexdigest()


def actor_for(principal) -> str:
    return "intelligence:" + hashlib.sha256((principal or "anonymous").encode()).hexdigest()


class IntelligenceRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                response = await original(request)
                conn = getattr(request.state, "intelligence_connection", None)
                if conn is not None:
                    audit(conn, request.path_params["bid"], None,
                          actor_for(request.state.intelligence_principal),
                          "intelligence.read" if request.method == "GET" else "intelligence.write",
                          {"method": request.method})
                    conn.commit()
                response.headers["Cache-Control"] = "no-store"
                return response
            except (HTTPException, RequestValidationError) as exc:
                conn = getattr(request.state, "intelligence_connection", None) or _DB()
                request.state.intelligence_connection = conn
                try:
                    conn.rollback()
                    conn.execute("BEGIN IMMEDIATE")
                    status = exc.status_code if isinstance(exc, HTTPException) else 422
                    audit(conn, "*", None, actor_for(getattr(request.state, "intelligence_principal", None)),
                          "intelligence.denied", {"status": status, "method": request.method})
                    conn.commit()
                finally:
                    conn.close()
                    request.state.intelligence_connection = None
                detail = exc.detail if isinstance(exc, HTTPException) else "Invalid intelligence request; check required fields and limits"
                raise HTTPException(status, detail, headers={"Cache-Control": "no-store"}) from None
            finally:
                conn = getattr(request.state, "intelligence_connection", None)
                if conn is not None:
                    conn.close()
                    request.state.intelligence_connection = None

        return handler


router = APIRouter(prefix="/api/ls/borrowers/{bid}/intelligence", tags=["borrower-intelligence"],
                   route_class=IntelligenceRoute)


async def authorized(bid: str, request: Request, response: Response):
    session = request.state.session if hasattr(request.state, "session") else _RESOLVE(request.headers.get("authorization"))
    principal = principal_for(session)
    request.state.intelligence_principal = principal
    if not session:
        raise HTTPException(401, "Sign in as a lender; service keys cannot access borrower intelligence")
    if session.get("role") != "lender" or not principal:
        raise HTTPException(403, "Authenticated lender access is required")
    conn = _DB()
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        grant = conn.execute("SELECT * FROM ls_intelligence_access WHERE borrower_id=? AND principal=?",
                             (bid, principal)).fetchone()
        if not grant:
            raise HTTPException(403, "Borrower intelligence access is not provisioned. Ask authorized staff to provision an explicit borrower access grant.")
        demo_only = bool(grant["demo_only"])
        demo_actor = bool(session.get("demo") or session.get("is_demo") or session.get("demo_only"))
        if demo_actor and not demo_only:
            raise HTTPException(403, "Demo actors cannot access non-demo borrower records")
        if demo_only and (not demo_enabled(_ENV) or not bid.startswith("DEMO-")):
            raise HTTPException(403, "Sandbox access requires an explicitly enabled development environment and fictional borrower")
        if not conn.execute("SELECT 1 FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone():
            raise HTTPException(404, "Borrower not found")
        response.headers["Cache-Control"] = "no-store"
        context = {"conn": conn, "bid": bid, "principal": principal, "demo_only": demo_only}
        request.state.intelligence_connection = conn
        return context
    except Exception:
        conn.rollback()
        conn.close()
        raise


Access = Annotated[dict, Depends(authorized)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentIn(InputModel):
    scope: Literal["credit", "cashflow"]
    acknowledged: StrictBool
    mode: Literal["sandbox", "attested"] = "sandbox"
    purpose: Literal["cashflow_assessment"] | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def valid_consent(self):
        if self.acknowledged is not True:
            raise ValueError("Explicit acknowledgement is required")
        if self.mode == "attested" and (self.scope != "cashflow" or not self.purpose or not self.expires_at):
            raise ValueError("Declared cashflow requires recorded borrower authorization, purpose and expiry")
        if self.expires_at:
            current = datetime.now(timezone.utc)
            if self.expires_at.tzinfo is None or not current < self.expires_at <= current + timedelta(days=30):
                raise ValueError("Expiry requires a timezone and must be within 30 days")
        return self


class CollectionIn(InputModel):
    consent_id: str = Field(min_length=1, max_length=64)


class RecordsIn(CollectionIn):
    records: list[CashflowRecord] = Field(min_length=1, max_length=MAX_RECORDS)


class StatementIn(CollectionIn):
    csv: str = Field(min_length=1, max_length=MAX_CSV_BYTES)


def consent_view(row: dict) -> dict:
    status = row["status"]
    if status != "revoked" and row["expires_at"] <= now():
        status = "expired"
    return {"id": row["id"], "scope": row["scope"], "status": status,
            "expires_at": row["expires_at"], "created_at": row["created_at"],
            "mode": row["mode"], "purpose": row["purpose"],
            "notice": "Fictional sandbox acknowledgement; not legal borrower consent" if row["mode"] == "sandbox"
            else "Lender attests recorded borrower authorization for declared cashflow assessment; not bureau or bank-provider consent"}


def consent_for(context, consent_id: str, scope: str, mode: str | None = None) -> dict:
    row = context["conn"].execute(
        "SELECT * FROM ls_intelligence_consents WHERE id=? AND borrower_id=? AND principal=?",
        (consent_id, context["bid"], context["principal"])).fetchone()
    if not row or row["scope"] != scope or (mode and row["mode"] != mode):
        raise HTTPException(403, "A matching borrower authorization or sandbox acknowledgement is required")
    row = dict(row)
    if consent_view(row)["status"] not in {"sandbox", "attested"}:
        raise HTTPException(403, "Consent is revoked or expired")
    if row["mode"] == "sandbox":
        require_demo(context)
    return row


def require_demo(context):
    if not demo_enabled(_ENV) or not context["demo_only"] or not context["bid"].startswith("DEMO-"):
        raise HTTPException(403, "Development sandbox requires a fictional DEMO- borrower and a staff-provisioned demo-only grant")


def visible_consents(context) -> list[dict]:
    rows = [dict(r) for r in context["conn"].execute(
        "SELECT * FROM ls_intelligence_consents WHERE borrower_id=? AND principal=? ORDER BY created_at,id",
        (context["bid"], context["principal"]))]
    return [r for r in rows if consent_view(r)["status"] in {"sandbox", "attested"}
            and (r["mode"] != "sandbox" or (demo_enabled(_ENV) and context["demo_only"]))]


def summaries_for(context, consents: list[dict]) -> list[dict]:
    allowed = {c["id"]: c for c in consents if c["scope"] == "cashflow"}
    groups = {}
    for row in context["conn"].execute(
            "SELECT * FROM ls_intelligence_records WHERE borrower_id=? AND principal=? ORDER BY record_date,id",
            (context["bid"], context["principal"])):
        consent = allowed.get(row["consent_id"])
        if not consent:
            continue
        if row["source"] in {"DEMO/SANDBOX", "BANK-DERIVED"} and not (demo_enabled(_ENV) and context["demo_only"] and consent["mode"] == "sandbox"):
            continue
        if row["source"] == "DECLARED BY BORROWER" and consent["mode"] != "attested":
            continue
        group = groups.setdefault(row["source"], {"records": [], "fetched_at": row["fetched_at"]})
        group["fetched_at"] = max(group["fetched_at"], row["fetched_at"])
        group["records"].append({"date": row["record_date"], **{k: row[k] for k in
                                ("direction", "amount", "category", "balance")}})
    return [summarize(g["records"], source, g["fetched_at"], _TRANSFERS) for source, g in sorted(groups.items())]


def internal_metrics(context) -> dict:
    if context["demo_only"]:
        return {}
    row = context["conn"].execute(
        "SELECT loans_completed,repayments_on_time,repayments_missed,amount_repaid,updated_at"
        " FROM ls_borrower_perf WHERE borrower_id=?", (context["bid"],)).fetchone()
    return {"source": "INTERNAL REPAYMENT RECORDS", **dict(row)} if row else {}


@router.get("")
async def get_intelligence(context: Access):
    consents = visible_consents(context)
    allowed_credit = {c["id"]: c for c in consents if c["scope"] == "credit"}
    credit = None
    for row in context["conn"].execute(
            "SELECT * FROM ls_intelligence_credit WHERE borrower_id=? AND principal=? ORDER BY fetched_at DESC,id DESC",
            (context["bid"], context["principal"])):
        consent = allowed_credit.get(row["consent_id"])
        if not consent:
            continue
        if row["source"] != "DEMO/SANDBOX" or consent["mode"] != "sandbox":
            continue
        try:
            report = normalize_report(json.loads(row["report_json"]))
            if report["source"] != row["source"] or report["provider"] != row["provider"]:
                continue
            credit = report
            break
        except (ValueError, ValidationError):
            continue
    summaries = summaries_for(context, consents)
    provider, bank = credit_provider(_ENV), account_provider()
    sandbox_available = demo_enabled(_ENV) and context["demo_only"]
    all_consents = [consent_view(dict(r)) for r in context["conn"].execute(
        "SELECT * FROM ls_intelligence_consents WHERE borrower_id=? AND principal=? ORDER BY created_at,id",
        (context["bid"], context["principal"]))]
    return {
        "credit": credit, "cashflow": summaries, "consents": all_consents,
        "providers": {
            "credit": {"provider": provider.name, "status": provider.status,
                       "sandbox_available": sandbox_available and isinstance(provider, SandboxCreditProvider)},
            "bank": {"provider": bank.name, "status": bank.status},
            "demo_enabled": demo_enabled(_ENV), "statement_upload_enabled": sandbox_available,
            "cashflow_demo_available": sandbox_available,
        },
        "model": {"uses_new_features": False, "status": "Retraining required",
                  "features": extract_features(credit, summaries)},
        "internal": internal_metrics(context),
        "access": {"granted": True, "demo_only": context["demo_only"],
                   "categories": sorted(CATEGORIES), "declared_authorization_purpose": PURPOSE,
                   "max_consent_days": 30},
    }


@router.post("/consents")
async def create_consent(item: ConsentIn, context: Access):
    if item.mode == "sandbox":
        require_demo(context)
    ts = now()
    expiry = item.expires_at.astimezone(timezone.utc).isoformat() if item.expires_at else (
        datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    row = {"id": uuid.uuid4().hex, "borrower_id": context["bid"], "principal": context["principal"],
           "scope": item.scope, "mode": item.mode, "status": item.mode,
           "purpose": PURPOSE if item.mode == "attested" else "fictional_sandbox_demonstration",
           "expires_at": expiry, "created_at": ts}
    context["conn"].execute(
        "INSERT INTO ls_intelligence_consents (id,borrower_id,principal,scope,mode,status,purpose,expires_at,created_at)"
        " VALUES (:id,:borrower_id,:principal,:scope,:mode,:status,:purpose,:expires_at,:created_at)", row)
    return consent_view(row)


@router.post("/consents/{consent_id}/revoke")
async def revoke_consent(consent_id: str, context: Access):
    row = context["conn"].execute(
        "SELECT * FROM ls_intelligence_consents WHERE id=? AND borrower_id=? AND principal=?",
        (consent_id, context["bid"], context["principal"])).fetchone()
    if not row:
        raise HTTPException(404, "Consent not found")
    context["conn"].execute("UPDATE ls_intelligence_consents SET status='revoked' WHERE id=?", (consent_id,))
    return consent_view({**dict(row), "status": "revoked"})


@router.post("/credit/fetch")
async def fetch_credit(item: CollectionIn, context: Access):
    consent_for(context, item.consent_id, "credit")
    provider = credit_provider(_ENV)
    if isinstance(provider, SandboxCreditProvider):
        require_demo(context)
    try:
        report = normalize_report(provider.fetch(context["bid"]))
        if report["provider"] != provider.name or report["source"] != "DEMO/SANDBOX":
            raise ProviderUnavailable("Authorized production consent integration is unavailable")
    except (ProviderUnavailable, ValueError, ValidationError):
        raise HTTPException(503, "Credit provider unavailable or returned invalid data; authorized production integration is required") from None
    context["conn"].execute(
        "INSERT INTO ls_intelligence_credit (borrower_id,principal,consent_id,source,provider,report_json,fetched_at)"
        " VALUES (?,?,?,?,?,?,?) ON CONFLICT(consent_id,source,provider) DO UPDATE SET"
        " report_json=excluded.report_json,fetched_at=excluded.fetched_at",
        (context["bid"], context["principal"], item.consent_id, report["source"], report["provider"],
         json.dumps(report, allow_nan=False), report["fetched_at"]))
    return report


def save_records(context, consent_id: str, records: list[dict], source: str, provider: str) -> dict:
    conn, ts = context["conn"], now()
    added = 0
    for record in records:
        record = normalized_record(record)
        cur = conn.execute(
            "INSERT INTO ls_intelligence_records (borrower_id,principal,consent_id,source,provider,record_date,"
            "direction,amount,category,balance,fingerprint,fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(borrower_id,principal,source,fingerprint) DO NOTHING",
            (context["bid"], context["principal"], consent_id, source, provider, record["date"],
             record["direction"], record["amount"], record["category"], record["balance"], fingerprint(record), ts))
        added += cur.rowcount
    summaries = summaries_for(context, visible_consents(context))
    summary = next((s for s in summaries if s["source"] == source), None)
    return {"source": source, "added": added, "duplicates": len(records) - added, "summary": summary}


@router.post("/cashflow/demo")
async def create_demo(item: CollectionIn, context: Access):
    require_demo(context)
    consent_for(context, item.consent_id, "cashflow", "sandbox")
    existing = context["conn"].execute(
        "SELECT 1 FROM ls_intelligence_records WHERE borrower_id=? AND principal=? AND source='DEMO/SANDBOX' LIMIT 1",
        (context["bid"], context["principal"])).fetchone()
    provider = SandboxAccountProvider(_ENV)
    return save_records(context, item.consent_id, [] if existing else provider.fetch(context["bid"]),
                        "DEMO/SANDBOX", provider.name)


@router.post("/cashflow/records")
async def create_records(item: RecordsIn, context: Access):
    consent_for(context, item.consent_id, "cashflow", "attested")
    return save_records(context, item.consent_id, [r.model_dump() for r in item.records],
                        "DECLARED BY BORROWER", "lender_attested_declaration")


@router.post("/cashflow/statement")
async def upload_statement(item: StatementIn, context: Access):
    require_demo(context)
    consent_for(context, item.consent_id, "cashflow", "sandbox")
    try:
        records = parse_statement(item.csv)
    except ValueError:
        raise HTTPException(422, "Invalid statement CSV; use the six required columns, valid categories, dates and amounts; maximum 2000 records / 1MB") from None
    return save_records(context, item.consent_id, records, "BANK-DERIVED", "development_statement_upload_unverified")
