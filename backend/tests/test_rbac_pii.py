"""Authorization boundaries + guest PII filtering (traced to the DB)."""
import app as app_module

PII = {"phone", "email", "address_line", "bank_account", "device_id"}


def test_guest_blocked_from_governance(guest):
    for path in ["/api/ls/admin/overview", "/api/ls/admin/sessions",
                 "/api/ls/admin/config", "/api/ls/admin/model",
                 "/api/ls/admin/approvals"]:
        r = guest.post(path, json={}) if "ask" in path or "analyze" in path else guest.get(path)
        assert r.status_code in (403, 422), (path, r.status_code)


def test_guest_blocked_from_runs(guest):
    r = guest.post("/api/ls/borrowers/B90001/analyze", json={})
    assert r.status_code == 403
    r = guest.post("/api/ls/recommendations/simulate",
                   json={"borrower_id": "B90001", "amount": 50000,
                         "interest_rate": 12, "duration_months": 12})
    assert r.status_code == 403


def test_lender_passes_governance(lender):
    assert lender.get("/api/ls/admin/overview").status_code == 200


def test_guest_list_has_no_pii(guest):
    rows = guest.get("/api/ls/borrowers").json()["rows"]
    assert rows, "seed borrower missing"
    assert not (PII & set(rows[0].keys())), PII & set(rows[0].keys())


def test_guest_detail_has_no_pii_but_lender_does(guest, lender):
    g = guest.get("/api/ls/borrowers/B90001").json()
    assert not (PII & set(g.keys())), PII & set(g.keys())
    assert g["name"] == "Test Borrower" and g["city"] == "Mumbai"
    l = lender.get("/api/ls/borrowers/B90001").json()
    assert l["phone"] == "9811111111"


def test_guest_analysis_hides_input_snapshot(guest, lender):
    lender.post("/api/ls/borrowers/B90001/analyze", json={})
    g = guest.get("/api/ls/borrowers/B90001/analysis").json()
    assert "input_snapshot" not in g
    assert g["trust_score"] is not None


def test_sessions_list_hides_tokens(lender):
    rows = lender.get("/api/ls/admin/sessions").json()
    assert rows, "expected at least the lender session"
    assert all("token" not in r for r in rows)
    assert all(r.get("token_prefix") for r in rows)
    assert any(r.get("current") is True for r in rows)


def test_revoke_by_id_kills_session(client, lender):
    me = lender.get("/api/auth/me")
    assert me.status_code == 200
    rows = lender.get("/api/ls/admin/sessions").json()
    mine = [r for r in rows if r.get("current")]
    assert mine, "current session not flagged"
    r = lender.request("DELETE", f"/api/ls/admin/sessions/{mine[0]['id']}")
    assert r.status_code == 200
    assert lender.get("/api/auth/me").status_code == 401


def test_notification_audience_masks_tokens(lender):
    import app as app_module
    conn = app_module.db()
    try:
        tok = conn.execute("SELECT token FROM sessions LIMIT 1").fetchone()[0]
        conn.execute("INSERT INTO ls_notifications (audience, kind, title, body, link, created_at)"
                     " VALUES (?,?,?,?,?,?)",
                     (tok, "probe", "Hello", "body", "", "2026-01-01T00:00:00"))
        conn.execute("INSERT INTO ls_notifications (audience, kind, title, body, link, created_at)"
                     " VALUES ('role:lender','probe','Staff','body','','2026-01-01T00:00:00')")
        conn.commit()
    finally:
        conn.close()
    rows = lender.get("/api/ls/notifications").json()
    assert rows, "expected notifications"
    assert all(r["audience"] in ("you", "role:lender", "role:guest", "role:all") for r in rows)
    assert not any(len(str(r["audience"])) > 20 and r["audience"] not in
                   ("role:lender", "role:guest", "role:all") for r in rows)
