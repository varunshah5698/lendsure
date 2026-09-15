"""Loan idempotency, cases, transfers, sessions, API keys."""
import app as app_module


def _analyze(client, bid="B90001"):
    r = client.post(f"/api/ls/borrowers/{bid}/analyze", json={})
    assert r.status_code == 200, r.text


def test_loan_request_idempotent(lender):
    _analyze(lender)
    body = {"borrower_id": "B90001", "amount": 50000, "interest_rate": 12,
            "duration_months": 12, "idempotency_key": "test-key-1"}
    r1 = lender.post("/api/ls/loan-requests", json=body)
    assert r1.status_code == 200
    r2 = lender.post("/api/ls/loan-requests", json=body)
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True
    assert r2.json()["id"] == r1.json()["id"]
    conn = app_module.db()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM ls_loan_requests WHERE idempotency_key=?",
                         ("test-key-1",)).fetchone()["c"]
    finally:
        conn.close()
    assert n == 1


def test_loan_request_server_key_when_missing(lender):
    _analyze(lender)
    r = lender.post("/api/ls/loan-requests",
                    json={"borrower_id": "B90001", "amount": 30000,
                          "interest_rate": 12, "duration_months": 12})
    assert r.status_code == 200
    assert r.json()["idempotency_key"].startswith("req-")


def test_guest_cannot_create_loan(guest):
    r = guest.post("/api/ls/loan-requests",
                   json={"borrower_id": "B90001", "amount": 1000,
                         "interest_rate": 12, "duration_months": 6})
    assert r.status_code == 403


def test_case_transfer_flow(lender):
    lender.post("/api/ls/officers",
                json={"name": "Asha Rao", "phone": "9811111111", "city": "Mumbai"})
    lender.post("/api/ls/officers",
                json={"name": "Bala Menon", "phone": "9822222222", "city": "Pune"})
    cid = lender.post("/api/ls/cases",
                      json={"title": "Transfer probe", "borrower_id": "B90001"}).json()["id"]
    r = lender.post(f"/api/ls/cases/{cid}/assign", json={"officer_phone": "9811111111"})
    assert r.status_code == 200
    r = lender.post(f"/api/ls/cases/{cid}/transfer-request",
                    json={"to_city": "Pune", "note": "moved"})
    assert r.status_code == 200
    r = lender.post(f"/api/ls/cases/{cid}/transfer-review",
                    json={"decision": "APPROVE", "assign_to": "9822222222"})
    assert r.status_code == 200
    body = r.json()
    assert body["city"] == "Pune" and body["assigned_to"] == "9822222222"
    hist = lender.get(f"/api/ls/cases/{cid}/transfers").json()
    assert hist and hist[0]["status"] == "TRANSFERRED"


def test_expired_api_key_rejected(client, lender):
    from fastapi.testclient import TestClient
    import app as app_module
    r = lender.post("/api/ls/admin/keys", json={"name": "probe"})
    assert r.status_code == 200
    key = r.json()["key"]
    with TestClient(app_module.app) as bare:
        # No session cookie here: the key alone must authenticate.
        assert bare.get("/api/ls/admin/stats", headers={"X-API-Key": key}).status_code == 200
        conn = app_module.db()
        try:
            conn.execute("UPDATE ls_api_keys SET expires_at='2000-01-01T00:00:00'")
            conn.commit()
        finally:
            conn.close()
        # Expired key = dead credential -> 401 (re-authenticate), never access.
        assert bare.get("/api/ls/admin/stats", headers={"X-API-Key": key}).status_code == 401


def test_read_scope_key_cannot_mutate(client, lender):
    r = lender.post("/api/ls/admin/keys",
                    json={"name": "reader", "scopes": "read"})
    key = r.json()["key"]
    assert lender.get("/api/ls/admin/stats", headers={"X-API-Key": key}).status_code == 200
    r = lender.post("/api/ls/borrowers/B90001/analyze", json={},
                    headers={"X-API-Key": key})
    assert r.status_code == 403
