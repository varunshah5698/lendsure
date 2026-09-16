"""Authentication, OTP discipline, sessions, rate limits, CSRF."""
import app as app_module


def _otp_for(client, email, purpose="verify"):
    conn = app_module.db()
    try:
        row = conn.execute(
            "SELECT code FROM email_otps WHERE email=? AND purpose=? ORDER BY id DESC LIMIT 1",
            (email, purpose)).fetchone()
        return row["code"]
    finally:
        conn.close()


def test_register_then_login_flow(client):
    r = client.post("/api/auth/register",
                    json={"name": "A", "email": "a@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    assert "demo_otp" in r.json()
    r = client.post("/api/auth/verify-email",
                    json={"email": "a@example.com", "otp": r.json()["demo_otp"]})
    assert r.status_code == 200
    assert "token" not in r.json()  # cookie-only: no credential in body
    assert "lendsure_session" in r.headers.get("set-cookie", "")
    assert "HttpOnly" in r.headers.get("set-cookie", "")
    r = client.get("/api/auth/me")
    assert r.status_code == 200 and r.json()["role"] == "lender"


def test_register_duplicate_is_neutral(client):
    client.post("/api/auth/register",
                json={"name": "A", "email": "dup@example.com", "password": "Strongpass1"})
    r = client.post("/api/auth/register",
                    json={"name": "B", "email": "dup@example.com", "password": "Strongpass2"})
    assert r.status_code == 200
    assert "demo_otp" not in r.json()
    assert "eligible" in r.json()["message"]


def test_weak_passwords_rejected(client):
    for pw in ["short", "allletters", "12345678", "Password", "qwerty123"]:
        r = client.post("/api/auth/register",
                        json={"name": "A", "email": f"{pw}@example.com", "password": pw})
        assert r.status_code == 400, pw


def test_wrong_password_locks_out(client, lender):
    for _ in range(5):
        r = client.post("/api/auth/login",
                        json={"email": "t@example.com", "password": "Wrongpass1"})
        assert r.status_code == 401
    r = client.post("/api/auth/login",
                    json={"email": "t@example.com", "password": "Wrongpass1"})
    assert r.status_code == 429


def test_new_device_demands_otp_then_verified(client, lender):
    ua = {"User-Agent": "BrandNewDevice/1.0"}
    r = client.post("/api/auth/login",
                    json={"email": "t@example.com", "password": "Strongpass1"},
                    headers=ua)
    assert r.status_code == 200
    assert r.json().get("otp_required") is True
    otp = _otp_for(client, "t@example.com", "login")
    r = client.post("/api/auth/verify-login",
                    json={"email": "t@example.com", "otp": otp}, headers=ua)
    assert r.status_code == 200
    # same device now trusted: plain password login works
    r = client.post("/api/auth/login",
                    json={"email": "t@example.com", "password": "Strongpass1"},
                    headers=ua)
    assert r.json().get("otp_required") is None


def test_otp_attempts_burn_code(client):
    client.post("/api/auth/request-otp", json={"phone": "9000000001"})
    for _ in range(5):
        r = client.post("/api/auth/verify-otp",
                        json={"phone": "9000000001", "otp": "000000"})
        assert r.status_code == 400
    r = client.post("/api/auth/verify-otp",
                    json={"phone": "9000000001", "otp": "000000"})
    assert r.status_code == 400
    assert "expired" in r.json()["detail"] or "new OTP" in r.json()["detail"]


def test_login_otp_resend_cooldown(client, lender):
    ua = {"User-Agent": "CooldownProbe/1.0"}
    r1 = client.post("/api/auth/login",
                     json={"email": "t@example.com", "password": "Strongpass1"},
                     headers=ua)
    assert r1.json().get("otp_required") is True
    r2 = client.post("/api/auth/login",
                     json={"email": "t@example.com", "password": "Strongpass1"},
                     headers=ua)
    assert r2.status_code == 429


def test_idle_expiry_kills_session(lender):
    assert lender.get("/api/auth/me").status_code == 200
    conn = app_module.db()
    try:
        # Plain (non-remembered) session, e.g. phone OTP: idle kill applies.
        conn.execute("UPDATE sessions SET remember=0, last_active=strftime('%Y-%m-%dT%H:%M:%f','now','-6 minutes')")
        conn.commit()
    finally:
        conn.close()
    assert lender.get("/api/auth/me").status_code == 401


def test_activity_refreshes_timer(lender):
    conn = app_module.db()
    try:
        conn.execute("UPDATE sessions SET last_active=strftime('%Y-%m-%dT%H:%M:%f','now','-40 seconds')")
        conn.commit()
        before = conn.execute("SELECT last_active FROM sessions LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    assert lender.get("/api/auth/me").status_code == 200
    conn = app_module.db()
    try:
        after = conn.execute("SELECT last_active FROM sessions LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    assert after > before


def test_logout_kills_only_own_session(client):
    from fastapi.testclient import TestClient
    c2 = TestClient(app_module.app)
    client.post("/api/auth/guest", json={"name": "A"})
    c2.post("/api/auth/guest", json={"name": "B"})
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert c2.get("/api/auth/me").status_code == 200


def test_hijack_binding_kills_session(client, lender):
    r = client.get("/api/auth/me", headers={"User-Agent": "Hijack/9.9",
                                            "X-Forwarded-For": "9.9.9.9"})
    assert r.status_code == 401


def test_csrf_form_post_rejected(client):
    r = client.post("/api/auth/guest", content="name=X",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 403


def test_production_no_smtp_fails_securely(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "DEMO_OTP", False)
    r = client.post("/api/auth/register",
                    json={"name": "P", "email": "prod@example.com", "password": "Strongpass1"})
    assert r.status_code == 503
    assert "demo_otp" not in r.json()


def test_dead_credential_yields_401_not_403(client, lender):
    conn = app_module.db()
    try:
        conn.execute("UPDATE sessions SET remember=0, last_active=strftime('%Y-%m-%dT%H:%M:%f','now','-6 minutes')")
        conn.commit()
    finally:
        conn.close()
    r = lender.get("/api/ls/admin/overview")
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_valid_guest_still_gets_403(guest):
    r = guest.get("/api/ls/admin/overview")
    assert r.status_code == 403
    assert "expired" not in r.json()["detail"].lower()


def test_phone_otp_disabled_without_demo(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "DEMO_OTP", False)
    r = client.post("/api/auth/request-otp", json={"phone": "9000000009"})
    assert r.status_code == 503


def test_register_persists_phone(client):
    r = client.post("/api/auth/register",
                    json={"name": "P", "email": "ph@example.com",
                          "password": "Strongpass1", "phone": "9811111111"})
    assert r.status_code == 200
    conn = app_module.db()
    try:
        row = conn.execute("SELECT phone FROM users WHERE email='ph@example.com'").fetchone()
    finally:
        conn.close()
    assert row["phone"] == "9811111111"


def test_smtp_host_port_override(monkeypatch):
    import app as app_module
    import smtplib
    seen = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            seen["host"] = host
            seen["port"] = port
        def starttls(self): pass
        def login(self, u, p): seen["login"] = u
        def send_message(self, m): seen["sent"] = True
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("LENDSURE_SMTP_USER", "u@example.com")
    monkeypatch.setenv("LENDSURE_SMTP_APP_PASSWORD", "app-pass")
    monkeypatch.setenv("LENDSURE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LENDSURE_SMTP_PORT", "2525")
    assert app_module.send_email_otp("to@example.com", "123456", "verify") is True
    assert seen == {"host": "smtp.example.com", "port": 2525,
                    "login": "u@example.com", "sent": True}


def test_expired_otp_rejected(client):
    client.post("/api/auth/request-otp", json={"phone": "9000000002"})
    conn = app_module.db()
    try:
        conn.execute("UPDATE otps SET expires_at='2000-01-01T00:00:00' WHERE phone='9000000002'")
        conn.commit()
    finally:
        conn.close()
    r = client.post("/api/auth/verify-otp",
                    json={"phone": "9000000002", "otp": "123456"})
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


def test_expired_otp_rejected(client):
    client.post("/api/auth/request-otp", json={"phone": "9000000002"})
    conn = app_module.db()
    try:
        conn.execute("UPDATE otps SET expires_at='2000-01-01T00:00:00' WHERE phone='9000000002'")
        conn.commit()
    finally:
        conn.close()
    r = client.post("/api/auth/verify-otp",
                    json={"phone": "9000000002", "otp": "123456"})
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()



def test_phone_otp_uses_live_sms_without_echo(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "DEMO_OTP", False)
    monkeypatch.setenv("LENDSURE_SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_VERIFY_SERVICE_SID", "VAtest")
    sent = []
    monkeypatch.setattr(app_module, "send_sms_otp", lambda phone: sent.append(phone) or True)
    monkeypatch.setattr(app_module, "check_sms_otp", lambda phone, code: code == "123456")

    r = client.post("/api/auth/request-otp", json={"phone": "9000000010"})
    assert r.status_code == 200
    assert "demo_otp" not in r.json()
    assert sent == ["9000000010"]

    r = client.post("/api/auth/verify-otp",
                    json={"phone": "9000000010", "otp": "123456"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_phone_otp_fails_closed_when_sms_provider_fails(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "DEMO_OTP", False)
    monkeypatch.setenv("LENDSURE_SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_VERIFY_SERVICE_SID", "VAtest")
    monkeypatch.setattr(app_module, "send_sms_otp", lambda phone: False)

    r = client.post("/api/auth/request-otp", json={"phone": "9000000011"})
    assert r.status_code == 503
    assert "demo_otp" not in r.json()


def test_remember_session_ignores_idle_timeout(client):
    profile, token = app_module._make_session(
        "remember@example.com", "R", "lender", 365,
        email="remember@example.com", remember=True)
    conn = app_module.db()
    try:
        conn.execute("UPDATE sessions SET last_active='2000-01-01T00:00:00' WHERE token=?",
                     (token,))
        conn.commit()
    finally:
        conn.close()
    # Ancient activity, but remembered: still valid, unlike normal sessions.
    assert app_module._validate_session_token(token) is not None


def test_email_login_gets_remembered_session(client):
    r = client.post("/api/auth/register",
                    json={"name": "R", "email": "rem@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    client.post("/api/auth/verify-email",
                json={"email": "rem@example.com", "otp": r.json()["demo_otp"]})
    conn = app_module.db()
    try:
        row = conn.execute("SELECT remember FROM sessions WHERE email=?",
                           ("rem@example.com",)).fetchone()
    finally:
        conn.close()
    assert row["remember"] == 1


def test_email_status_has_no_secrets(client):
    r = client.get("/api/auth/email-status")
    assert r.status_code == 200
    assert "smtp_configured" in r.json() and "demo_otp" in r.json()
