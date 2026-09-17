import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lendsure import intelligence
from lendsure.cashflow_intelligence import (
    SandboxAccountProvider, account_provider, extract_features, parse_statement, summarize,
)
from lendsure.credit_bureau import (
    ProviderUnavailable, SandboxCreditProvider, TransUnionProvider, credit_provider,
    demo_enabled, normalize_report,
)
from lendsure.schema import DDL, INTELLIGENCE_DDL, LIFECYCLE_DDL, LS_MIGRATIONS


ENV = {"LENDSURE_ENV": "test", "LENDSURE_INTELLIGENCE_DEMO": "1", "LENDSURE_CIBIL_PROVIDER": "sandbox"}
BASE = "/api/ls/borrowers/DEMO-one/intelligence"
HEADER = "date,direction,amount,category,description,balance\n"


def record(month="01", direction="in", amount=1000, category="cash_income", balance=None):
    return {"date": f"2025-{month}-05", "direction": direction, "amount": amount,
            "category": category, "balance": balance}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    path = tmp_path / "intelligence.sqlite"

    def db():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    sessions = {
        "one": {"role": "lender", "email": "one@example.test"},
        "two": {"role": "lender", "email": "two@example.test"},
        "guest": {"role": "guest", "email": "guest@example.test"},
        "service": {"role": "service", "user_id": 42},
        "demo": {"role": "lender", "email": "demo@example.test", "demo": True},
    }
    conn = db()
    conn.executescript(DDL + LIFECYCLE_DDL + INTELLIGENCE_DDL)
    for bid in ("DEMO-one", "DEMO-two", "REAL-one"):
        conn.execute("INSERT INTO ls_borrowers(borrower_id,name,monthly_income,created_at) VALUES (?,?,?,?)",
                     (bid, "Fictional test borrower", 12345, intelligence.now()))
    for token, bid, demo in (("one", "DEMO-one", 1), ("two", "DEMO-one", 1),
                             ("two", "DEMO-two", 1), ("one", "REAL-one", 0),
                             ("demo", "REAL-one", 0)):
        conn.execute("INSERT INTO ls_intelligence_access VALUES (?,?,?,?)",
                     (bid, intelligence.principal_for(sessions[token]), demo, intelligence.now()))
    conn.commit()
    conn.close()
    for name in ("_DB", "_RESOLVE", "_ENV", "_TRANSFERS"):
        monkeypatch.setattr(intelligence, name, getattr(intelligence, name))
    intelligence.configure(db, lambda auth: sessions.get((auth or "").removeprefix("Bearer ")), ENV)
    app = FastAPI()
    app.include_router(intelligence.router)
    with TestClient(app, headers={"Authorization": "Bearer one"}) as client:
        yield client, db, sessions


def consent(client, scope="cashflow", mode="sandbox", base=BASE):
    data = {"scope": scope, "acknowledged": True, "mode": mode}
    if mode == "attested":
        data.update(purpose="cashflow_assessment",
                    expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    response = client.post(base + "/consents", json=data)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_principals_are_stable_and_normalized():
    principal = intelligence.principal_for
    assert principal({"user_id": 7, "email": "a@example.test"}) == "user:7"
    assert principal({"email": " ONE@EXAMPLE.TEST "}) == principal({"email": "one@example.test"})
    assert principal({"phone": "+91 (98765) 43210"}) == principal({"phone": "9876543210"})
    assert principal({"phone": "one@example.test"}) == principal({"email": "one@example.test"})
    assert principal({"phone": "guest"}) is None
    assert principal(None) is None
    assert "one@example" not in principal({"email": "one@example.test"})


@pytest.mark.parametrize("token,status", [("", 401), ("guest", 403), ("service", 403), ("invalid", 401)])
def test_all_endpoints_reject_unauthorized(isolated, token, status):
    client, db, _ = isolated
    client.headers["Authorization"] = "Bearer " + token
    client.headers["X-API-Key"] = "service-key"
    assert client.get(BASE).status_code == status
    for endpoint, payload in (
        ("/consents", {"scope": "cashflow", "acknowledged": True}),
        ("/credit/fetch", {"consent_id": "none"}),
        ("/cashflow/demo", {"consent_id": "none"}),
        ("/cashflow/records", {"consent_id": "none", "records": [record()]}),
        ("/cashflow/statement", {"consent_id": "none", "csv": HEADER}),
        ("/consents/none/revoke", {}),
    ):
        assert client.post(BASE + endpoint, json=payload).status_code == status
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ls_intelligence_consents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ls_audit WHERE action='intelligence.denied'").fetchone()[0] == 7


def test_explicit_grants_no_demo_bypass(isolated):
    client, db, _ = isolated
    other = BASE.replace("DEMO-one", "DEMO-two")
    response = client.get(other)
    assert response.status_code == 403 and "staff" in response.json()["detail"]
    assert client.post(other + "/consents", json={"scope": "credit", "acknowledged": True}).status_code == 403
    client.headers["Authorization"] = "Bearer demo"
    assert client.get(BASE.replace("DEMO-one", "REAL-one")).status_code == 403
    client.headers["Authorization"] = "Bearer one"
    real = BASE.replace("DEMO-one", "REAL-one")
    assert client.get(real).status_code == 200
    assert client.post(real + "/consents", json={"scope": "credit", "acknowledged": True}).status_code == 403
    with db() as conn:
        conn.execute("DELETE FROM ls_intelligence_access WHERE borrower_id='DEMO-one'")
    assert client.get(BASE).status_code == 403


def test_credit_consent_revocation_and_user_isolation(isolated):
    client, db, _ = isolated
    cid = consent(client, "credit")
    response = client.post(BASE + "/credit/fetch", json={"consent_id": cid})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["source"] == "DEMO/SANDBOX" and report["score_min"] <= report["score"] <= report["score_max"]
    assert report["accounts"][0]["credit_limit"] is None
    response = client.get(BASE)
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["model"]["uses_new_features"] is False
    assert response.json()["credit"] == report
    client.headers["Authorization"] = "Bearer two"
    assert client.get(BASE).json()["credit"] is None
    assert client.post(BASE + "/credit/fetch", json={"consent_id": cid}).status_code == 403
    assert client.post(BASE + f"/consents/{cid}/revoke").status_code == 404
    client.headers["Authorization"] = "Bearer one"
    assert client.post(BASE + f"/consents/{cid}/revoke").json()["status"] == "revoked"
    assert client.get(BASE).json()["credit"] is None
    assert client.post(BASE + "/credit/fetch", json={"consent_id": cid}).status_code == 403
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ls_intelligence_credit").fetchone()[0] == 1


def test_demo_idempotence_mixed_sources_and_privacy(isolated):
    client, db, _ = isolated
    cid = consent(client)
    first = client.post(BASE + "/cashflow/demo", json={"consent_id": cid})
    assert first.status_code == 200, first.text
    assert first.json()["added"] == 18
    assert client.post(BASE + "/cashflow/demo", json={"consent_id": cid}).json()["added"] == 0
    declared = consent(client, mode="attested")
    data = {"consent_id": declared, "records": [{**record(), "description": "Private identifying text"}]}
    assert client.post(BASE + "/cashflow/records", json=data).json()["added"] == 1
    data["records"][0]["description"] = "Changed private text"
    assert client.post(BASE + "/cashflow/records", json=data).json()["duplicates"] == 1
    statement = HEADER + "2025-01-05,in,1200,salary,Private payer,2000\n"
    response = client.post(BASE + "/cashflow/statement", json={"consent_id": cid, "csv": statement})
    assert response.status_code == 200, response.text
    assert "statement upload/unverified" in response.json()["summary"]["confidence"]
    assert client.post(BASE + "/cashflow/statement", json={"consent_id": cid, "csv": statement}).json()["added"] == 0
    result = client.get(BASE).json()
    assert {s["source"] for s in result["cashflow"]} == {"DEMO/SANDBOX", "BANK-DERIVED", "DECLARED BY BORROWER"}
    assert len(result["model"]["features"]["cashflow_by_source"]) == 3
    client.headers["Authorization"] = "Bearer two"
    assert client.get(BASE).json()["cashflow"] == []
    client.headers["Authorization"] = "Bearer one"
    with db() as conn:
        dump = "\n".join(conn.iterdump())
        assert "Private" not in dump and "Changed private" not in dump
        assert conn.execute("SELECT monthly_income FROM ls_borrowers WHERE borrower_id='DEMO-one'").fetchone()[0] == 12345
        audits = conn.execute("SELECT actor,detail FROM ls_audit").fetchall()
        assert audits and all("@" not in row["actor"] and "records" not in row["detail"] for row in audits)
    client.post(BASE + f"/consents/{cid}/revoke")
    assert [s["source"] for s in client.get(BASE).json()["cashflow"]] == ["DECLARED BY BORROWER"]
    client.post(BASE + f"/consents/{declared}/revoke")
    assert client.get(BASE).json()["cashflow"] == []


def test_expiry_and_scope_block_collection(isolated):
    client, db, _ = isolated
    cid = consent(client)
    assert client.post(BASE + "/credit/fetch", json={"consent_id": cid}).status_code == 403
    assert client.post(BASE + "/cashflow/records", json={"consent_id": cid, "records": [record()]}).status_code == 403
    client.post(BASE + "/cashflow/demo", json={"consent_id": cid})
    with db() as conn:
        conn.execute("UPDATE ls_intelligence_consents SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (cid,))
    result = client.get(BASE).json()
    assert result["cashflow"] == [] and result["consents"][0]["status"] == "expired"
    assert client.post(BASE + "/cashflow/demo", json={"consent_id": cid}).status_code == 403


@pytest.mark.parametrize("payload", [
    {"scope": "credit", "acknowledged": False},
    {"scope": "cashflow", "acknowledged": "true"},
    {"scope": "credit", "acknowledged": True, "mode": "attested"},
    {"scope": "cashflow", "acknowledged": True, "mode": "attested"},
    {"scope": "cashflow", "acknowledged": True, "mode": "attested", "purpose": "other"},
    {"scope": "cashflow", "acknowledged": True, "expires_at": "2020-01-01T00:00:00Z"},
    {"scope": "cashflow", "acknowledged": True, "expires_at": "2099-01-01T00:00:00Z"},
])
def test_invalid_consents(isolated, payload):
    client, _, _ = isolated
    assert client.post(BASE + "/consents", json=payload).status_code == 422


@pytest.mark.parametrize("patch", [
    {"amount": -1}, {"amount": 0}, {"amount": True}, {"amount": "100"}, {"amount": 1e13},
    {"date": "2025-02-30"}, {"date": "2099-01-01"}, {"date": "2025-1-1"},
    {"direction": "credit"}, {"category": "invented"}, {"description": "x" * 241},
    {"balance": True}, {"extra": "forbidden"},
])
def test_invalid_records(isolated, patch):
    client, _, _ = isolated
    cid = consent(client, mode="attested")
    response = client.post(BASE + "/cashflow/records", json={"consent_id": cid, "records": [{**record(), **patch}]})
    assert response.status_code == 422
    assert client.get(BASE).json()["cashflow"] == []


def test_declared_production_and_internal_metrics(isolated, monkeypatch):
    client, db, _ = isolated
    monkeypatch.setattr(intelligence, "_ENV", {"LENDSURE_ENV": "production", "LENDSURE_INTELLIGENCE_DEMO": "1"})
    real = BASE.replace("DEMO-one", "REAL-one")
    cid = consent(client, mode="attested", base=real)
    response = client.post(real + "/cashflow/records", json={"consent_id": cid, "records": [record()]})
    assert response.status_code == 200, response.text
    assert client.post(real + "/cashflow/statement", json={"consent_id": cid, "csv": HEADER}).status_code == 403
    with db() as conn:
        conn.execute("INSERT INTO ls_borrower_perf VALUES (?,?,?,?,?,?)", ("REAL-one", 2, 12, 1, 12000, intelligence.now()))
    result = client.get(real).json()
    assert result["providers"]["demo_enabled"] is False
    assert result["providers"]["statement_upload_enabled"] is False
    assert result["internal"]["amount_repaid"] == 12000
    assert result["credit"] is None and len(result["cashflow"]) == 1
    assert client.get(BASE).status_code == 403


def test_unavailable_and_invalid_provider(isolated, monkeypatch):
    client, _, _ = isolated
    cid = consent(client, "credit")
    monkeypatch.setattr(intelligence, "_ENV", {**ENV, "LENDSURE_CIBIL_PROVIDER": "transunion"})
    assert client.post(BASE + "/credit/fetch", json={"consent_id": cid}).status_code == 503
    monkeypatch.setattr(intelligence, "_ENV", ENV)
    monkeypatch.setattr(SandboxCreditProvider, "fetch", lambda self, bid: {"score": 99999})
    assert client.post(BASE + "/credit/fetch", json={"consent_id": cid}).status_code == 503
    assert client.get(BASE).json()["credit"] is None


def test_provider_fail_closed_and_stale():
    assert not demo_enabled({"LENDSURE_INTELLIGENCE_DEMO": "1"})
    assert not demo_enabled({**ENV, "LENDSURE_ENV": "production"})
    for provider in (credit_provider({}), credit_provider({**ENV, "LENDSURE_ENV": "production"}),
                     TransUnionProvider(), account_provider(), SandboxCreditProvider({}), SandboxAccountProvider({})):
        with pytest.raises(ProviderUnavailable):
            provider.fetch("DEMO-one")
    report = SandboxCreditProvider(ENV).fetch("DEMO-one")
    assert normalize_report(report)["stale"] is False
    old = (datetime.now(timezone.utc) - timedelta(days=40)).date().isoformat()
    report.update(report_date=old, inquiries=None, events=None, utilization_trend=None)
    assert normalize_report(report)["stale"] is True
    report.update(score=None, score_min=None, score_max=None, report_date=None)
    result = normalize_report(report)
    assert result["score"] is None and result["stale"] is True


@pytest.mark.parametrize("patch", [
    {"score": 901}, {"score": True}, {"score": float("nan")}, {"score_min": 900},
    {"score_min": None}, {"utilization_pct": 101}, {"history_months": -1},
    {"active_accounts": 1.5}, {"overdue_amount": float("inf")},
    {"accounts": [{"status": "made-up"}]}, {"inquiries": [{"date": "bad"}]},
    {"events": [{"date": "2025-01-01", "type": "x", "description": "x" * 241}]},
    {"utilization_trend": [{"date": "2025-01-01", "value": -1}]},
    {"reference_id": "x" * 241}, {"source": "CIBIL"},
])
def test_credit_validation(patch):
    report = SandboxCreditProvider(ENV).fetch("DEMO-one")
    with pytest.raises(ValueError):
        normalize_report({**report, **patch})


def test_cashflow_positive_negative_volatile_missing_and_balances():
    rows = [record("01", amount=1000), record("01", "out", 400, "food"),
            record("03", amount=3000), record("03", "out", 4000, "housing")]
    result = summarize(rows, "DECLARED BY BORROWER", intelligence.now())
    metrics = result["metrics"]
    assert result["missing_months"] == ["2025-02"]
    assert metrics["monthly_inflow"] == 2000 and metrics["monthly_outflow"] == 2200
    assert metrics["net_cash_flow"] == -200 and metrics["negative_months"] == 1
    assert metrics["income_volatility_pct"] == 50 and metrics["income_consistency_pct"] == 50
    assert metrics["average_monthly_balance"] is None and metrics["minimum_balance"] is None
    assert metrics["largest_income_source"] == "cash_income" and metrics["income_days"] == 2
    bank = summarize([record("01", balance=500), record("02", balance=-200)], "BANK-DERIVED", intelligence.now())
    assert bank["metrics"]["average_monthly_balance"] == 150
    assert bank["metrics"]["minimum_balance"] == -200
    assert bank["metrics"]["income_consistency_pct"] == 100
    assert bank["metrics"]["expense_volatility_pct"] is None
    assert "unverified" in bank["confidence"]
    assert extract_features(None, [result, bank])["credit"]["score"] is None


def test_transfers_ratios_and_unknown_income():
    rows = [record(amount=1000), record(direction="out", amount=200, category="emi"),
            record(direction="out", amount=100, category="debt_payment"),
            record(amount=5000, category="transfer"), record(amount=2000, category="loan_proceeds"),
            record(amount=300, category="refund")]
    result = summarize(rows, "DECLARED BY BORROWER", intelligence.now())
    metrics = result["metrics"]
    assert metrics["monthly_inflow"] == 3300
    assert metrics["debt_service_burden_pct"] == 30 and metrics["emi_to_income_pct"] == 20
    assert metrics["income_volatility_pct"] is None
    custom = summarize(rows, "DECLARED BY BORROWER", intelligence.now(), ["transfer", "refund"])
    assert custom["metrics"]["monthly_inflow"] == 3000
    empty_income = summarize([record(direction="out", category="food")], "BANK-DERIVED", intelligence.now())
    assert empty_income["metrics"]["debt_service_burden_pct"] is None
    assert empty_income["metrics"]["largest_income_source"] is None
    with pytest.raises(ValueError):
        summarize(rows, "BANK-DERIVED", intelligence.now(), ["invalid"])


@pytest.mark.parametrize("csv_text", [
    "date,amount\n2025-01-01,1\n", HEADER + "2025-01-01,in,NaN,salary,,\n",
    HEADER + "2025-01-01,in,1,unknown,,\n", HEADER + "2025-01-01,in,1,salary,,1,extra\n",
    HEADER + "2025-01-01,in,1,salary,\"unterminated,\n", HEADER,
    HEADER + "2025-01-01,in,1,salary,,\n" * 2001, "x" * 1_000_001,
    HEADER + "2025-01-01,in,-1,salary,,\n", HEADER + "2025-01-01,in,1,salary,,Infinity\n",
])
def test_strict_statement(csv_text):
    with pytest.raises(ValueError):
        parse_statement(csv_text)


def test_csv_bounded_upload_and_revoked_dedup(isolated):
    client, _, _ = isolated
    cid = consent(client)
    for text in (HEADER, HEADER + "2025-01-01,in,1,salary,,\n" * 2001, "é" * 600000):
        assert client.post(BASE + "/cashflow/statement", json={"consent_id": cid, "csv": text}).status_code == 422
    declared = consent(client, mode="attested")
    payload = {"consent_id": declared, "records": [record()]}
    assert client.post(BASE + "/cashflow/records", json=payload).json()["added"] == 1
    client.post(BASE + f"/consents/{declared}/revoke")
    payload["consent_id"] = consent(client, mode="attested")
    response = client.post(BASE + "/cashflow/records", json=payload)
    assert response.json()["added"] == 0 and response.json()["summary"] is None
    assert client.get(BASE).json()["cashflow"] == []


def test_persisted_stale_and_invalid_credit(isolated):
    client, db, _ = isolated
    cid = consent(client, "credit")
    client.post(BASE + "/credit/fetch", json={"consent_id": cid})
    with db() as conn:
        report = json.loads(conn.execute("SELECT report_json FROM ls_intelligence_credit").fetchone()[0])
        report.update(report_date="2025-01-01", inquiries=None, events=None, utilization_trend=None)
        conn.execute("UPDATE ls_intelligence_credit SET report_json=?", (json.dumps(report),))
    assert client.get(BASE).json()["credit"]["stale"] is True
    with db() as conn:
        report["score"] = 10000
        conn.execute("UPDATE ls_intelligence_credit SET report_json=?", (json.dumps(report),))
    assert client.get(BASE).json()["credit"] is None


def test_raw_nonfinite_and_record_limits(isolated):
    client, _, _ = isolated
    cid = consent(client, mode="attested")
    for value in (float("nan"), float("inf"), float("-inf")):
        payload = {"consent_id": cid, "records": [{**record(), "amount": value}]}
        response = client.post(BASE + "/cashflow/records", content=json.dumps(payload),
                               headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert "NaN" not in response.text and "Infinity" not in response.text
    for records in ([], [record()] * 2001):
        assert client.post(BASE + "/cashflow/records", json={"consent_id": cid, "records": records}).status_code == 422


def test_bank_only_and_ambiguous_balances(isolated):
    client, _, _ = isolated
    cid = consent(client)
    statement = HEADER + "2025-01-01,in,1200,salary,,2000\n2025-02-01,out,100,food,,-100\n"
    response = client.post(BASE + "/cashflow/statement", json={"consent_id": cid, "csv": statement})
    assert response.status_code == 200
    cashflow = client.get(BASE).json()["cashflow"]
    assert len(cashflow) == 1 and cashflow[0]["source"] == "BANK-DERIVED"
    assert cashflow[0]["metrics"]["minimum_balance"] == -100
    ambiguous = summarize([record(balance=10), record(direction="out", category="food", balance=20)],
                          "BANK-DERIVED", intelligence.now())
    assert ambiguous["months"][0]["balance"] is None
    recurring = summarize([record("01", "out", 100, "housing"), record("02", "out", 200, "housing")],
                          "DECLARED BY BORROWER", intelligence.now())
    assert recurring["metrics"]["recurring_obligations"] == [{"category": "housing", "amount": 150, "months_observed": 2}]


def test_migration_foreign_keys_and_idempotence(isolated):
    _, db, _ = isolated
    assert ("intelligence.v1", INTELLIGENCE_DDL) in LS_MIGRATIONS
    with db() as conn:
        conn.executescript(INTELLIGENCE_DDL)
        conn.executescript(INTELLIGENCE_DDL)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO ls_intelligence_access VALUES ('MISSING','user:42',0,?)", (intelligence.now(),))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO ls_intelligence_access VALUES ('REAL-one','user:42',1,?)", (intelligence.now(),))
