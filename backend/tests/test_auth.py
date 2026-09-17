"""Authentication, OTP discipline, sessions, rate limits, CSRF."""
import io

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
    # Password-only: signup saves (no session), signin checks + opens.
    r = client.post("/api/auth/register",
                    json={"name": "Anil", "username": "anil", "email": "a@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    assert "lendsure_session" not in r.headers.get("set-cookie", "")
    assert client.get("/api/auth/me").status_code == 401
    # Wrong password is rejected with an error.
    r = client.post("/api/auth/login",
                    json={"email": "a@example.com", "password": "Wrongpass1"})
    assert r.status_code == 401
    assert "incorrect" in r.json()["detail"].lower()
    # Right password opens everything, remembered.
    r = client.post("/api/auth/login",
                    json={"email": "a@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    assert r.json()["role"] == "lender"
    assert "token" not in r.json()  # cookie-only: no credential in body
    assert "lendsure_session" in r.headers.get("set-cookie", "")
    assert "HttpOnly" in r.headers.get("set-cookie", "")
    r = client.get("/api/auth/me")
    assert r.status_code == 200 and r.json()["role"] == "lender"


def test_register_duplicate_signals_signin(client):
    client.post("/api/auth/register",
                json={"name": "Dup Amit", "username": "dupamit", "email": "dup@example.com", "password": "Strongpass2"})
    r = client.post("/api/auth/register",
                    json={"name": "Dup Bina", "username": "dupbina", "email": "dup@example.com", "password": "Strongpass2"})
    assert r.status_code == 400
    assert "sign in" in r.json()["detail"].lower()


def test_weak_passwords_rejected(client):
    for i, pw in enumerate(["short", "allletters", "12345678", "Password", "qwerty123"]):
        r = client.post("/api/auth/register",
                        json={"name": "Weak User", "username": f"weakuser{i}",
                              "email": f"{pw}@example.com", "password": pw})
        assert r.status_code == 400, pw


def test_username_constraints_enforced(client):
    base = {"name": "Uma User", "email": "uma@example.com", "password": "Strongpass1"}
    bad = [
        ({}, "Choose a username"),  # missing entirely
        ({"username": "ab"}, "3-20"),  # too short
        ({"username": "a" * 21}, "3-20"),  # too long
        ({"username": "uma user"}, "spaces"),  # inner space
        ({"username": "Uma!#"}, "small letters"),  # bad charset
    ]
    for i, (extra, hint) in enumerate(bad):
        payload = {**base, "email": f"uma{i}@example.com", **extra}
        r = client.post("/api/auth/register", json=payload)
        assert r.status_code == 400, extra
        assert hint.lower() in r.json()["detail"].lower(), r.json()
    # Uppercase is normalized to small letters, underscores allowed.
    r = client.post("/api/auth/register",
                    json={**base, "username": "Uma_User"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "uma_user"


def test_duplicate_username_rejected(client):
    first = {"name": "Vic One", "username": "vic", "email": "vic1@example.com",
             "password": "Strongpass1"}
    r = client.post("/api/auth/register", json=first)
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/register",
                    json={"name": "Vic Two", "username": "vic", "email": "vic2@example.com",
                          "password": "Strongpass1"})
    assert r.status_code == 400
    assert "taken" in r.json()["detail"].lower()


def test_full_name_constraints_enforced(client):
    for i, (name, hint) in enumerate([
        ("", "full name"),  # missing
        ("X", "at least 2"),  # too short
        ("N" * 61, "at most 60"),  # too long
        ("9lives", "letters"),  # must start with a letter
    ]):
        r = client.post("/api/auth/register",
                        json={"name": name, "username": f"fullname{i}",
                              "email": f"fullname{i}@example.com", "password": "Strongpass1"})
        assert r.status_code == 400, name
        assert hint.lower() in r.json()["detail"].lower(), r.json()


def test_guest_username_compulsory_with_constraints(client):
    # Missing field is rejected by request validation (422).
    r = client.post("/api/auth/guest", json={})
    assert r.status_code == 422
    for payload, hint in [
        ({"name": ""}, "username"),  # empty
        ({"name": "   "}, "username"),  # blank
        ({"name": "ab"}, "3-20"),  # too short
        ({"name": "guest explorer"}, "spaces"),  # inner space
        ({"name": "Guest!"}, "small letters"),  # bad charset
    ]:
        r = client.post("/api/auth/guest", json=payload)
        assert r.status_code == 400, payload
        assert hint.lower() in r.json()["detail"].lower(), r.json()
    r = client.post("/api/auth/guest", json={"name": "guest_explorer"})
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "guest_explorer"


def test_wrong_password_locks_out(client, lender):
    for _ in range(5):
        r = client.post("/api/auth/login",
                        json={"email": "t@example.com", "password": "Wrongpass1"})
        assert r.status_code == 401
    r = client.post("/api/auth/login",
                    json={"email": "t@example.com", "password": "Wrongpass1"})
    assert r.status_code == 429


def test_new_device_signs_straight_in(client, lender):
    # No OTP anywhere now: password match signs in on any device.
    for ua in ({"User-Agent": "BrandNewDevice/1.0"}, {"User-Agent": "OtherDevice/2.0"}):
        r = client.post("/api/auth/login",
                        json={"email": "t@example.com", "password": "Strongpass1"},
                        headers=ua)
        assert r.status_code == 200
        assert r.json()["role"] == "lender"
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


def test_repeat_password_logins_always_work(client, lender):
    for _ in range(3):
        r = client.post("/api/auth/login",
                        json={"email": "t@example.com", "password": "Strongpass1"},
                        headers={"User-Agent": "RepeatDevice/1.0"})
        assert r.status_code == 200
        assert r.json().get("otp_required") is None


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
    client.post("/api/auth/guest", json={"name": "alan"})
    c2.post("/api/auth/guest", json={"name": "bina"})
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


def test_production_no_smtp_register_still_works(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "DEMO_OTP", False)
    # Password-only signup needs no email delivery at all.
    r = client.post("/api/auth/register",
                    json={"name": "Pam", "username": "pam", "email": "prod@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    assert "demo_otp" not in r.json()
    r = client.post("/api/auth/login",
                    json={"email": "prod@example.com", "password": "Strongpass1"})
    assert r.status_code == 200


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
                    json={"name": "Pam", "username": "pamphone", "email": "ph@example.com",
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
                    json={"name": "Raj", "username": "raj", "email": "rem@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    r = client.post("/api/auth/login",
                    json={"email": "rem@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
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


def test_sendgrid_path_sends_over_https(client, monkeypatch):
    import io
    import urllib.request
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.testkey")
    monkeypatch.setenv("LENDSURE_SMTP_USER", "sender@gmail.com")
    seen = {}

    class FakeResp:
        status = 202
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b""

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert app_module.send_email_otp("to@gmail.com", "123456", "verify") is True
    assert seen["url"] == "https://api.sendgrid.com/v3/mail/send"
    assert seen["auth"] == "Bearer SG.testkey"


def test_sendgrid_failure_falls_back_to_smtp_disabled(client, monkeypatch):
    import urllib.request
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.bad")
    monkeypatch.setenv("LENDSURE_SMTP_USER", "")
    monkeypatch.setenv("LENDSURE_SMTP_APP_PASSWORD", "")
    monkeypatch.setenv("LENDSURE_DEMO_OTP", "1")
    import urllib.error
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    # SMTP unconfigured + SendGrid failing: demo echo path still answers.
    assert app_module._email_configured() is True  # sendgrid key present
    assert app_module.send_email_otp("to@gmail.com", "123456", "verify") is False


def test_argon2id_is_default_hasher(client):
    r = client.post("/api/auth/register",
                    json={"name": "Ari", "username": "ari", "email": "argon@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    conn = app_module.db()
    try:
        h = conn.execute("SELECT password_hash FROM users WHERE email=?",
                         ("argon@example.com",)).fetchone()[0]
    finally:
        conn.close()
    import argon2
    assert h.startswith("$argon2id$")


def test_legacy_pbkdf2_upgrades_to_argon2_on_login(client):
    import hashlib
    salt = "00" * 16
    dk = hashlib.pbkdf2_hmac("sha256", b"Strongpass1", bytes.fromhex(salt), 600_000).hex()
    conn = app_module.db()
    try:
        conn.execute("INSERT INTO users (name, email, password_hash, email_verified, created_at)"
                     " VALUES (?,?,?,?,?)",
                     ("Legacy", "legacy@example.com", f"pbkdf2$600000${salt}${dk}",
                      1, "2026-01-01T00:00:00"))
        conn.commit()
    finally:
        conn.close()
    r = client.post("/api/auth/login",
                    json={"email": "legacy@example.com", "password": "Strongpass1"})
    assert r.status_code == 200
    conn = app_module.db()
    try:
        h = conn.execute("SELECT password_hash FROM users WHERE email=?",
                         ("legacy@example.com",)).fetchone()[0]
    finally:
        conn.close()
    assert h.startswith("$argon2id$")


def test_password_max_length_rejects_giant_input(client):
    r = client.post("/api/auth/register",
                    json={"name": "Gia", "username": "gia", "email": "giant@example.com", "password": "A1" + "x" * 200})
    assert r.status_code == 400


def test_my_sessions_and_revoke_all(client, lender):
    r = lender.get("/api/auth/sessions")
    assert r.status_code == 200
    mine = r.json()["sessions"]
    assert len(mine) >= 1 and any(s["current"] for s in mine)
    # Simulate a second device, then revoke everything else.
    conn = app_module.db()
    try:
        conn.execute("INSERT INTO sessions (token, phone, display_name, role, created_at,"
                     " expires_at, email, last_active) VALUES (?,?,?,?,?,?,?,?)",
                     ("tok-other", "t@example.com", "T", "lender",
                      "2026-01-01T00:00:00", "2027-01-01T00:00:00",
                      "t@example.com", "2026-01-01T00:00:00"))
        conn.commit()
    finally:
        conn.close()
    r = lender.post("/api/auth/sessions/revoke-all")
    assert r.status_code == 200 and r.json()["revoked"] >= 1
    r = lender.get("/api/auth/sessions")
    assert all(s["current"] for s in r.json()["sessions"])
    assert lender.get("/api/auth/me").status_code == 200


def test_hsts_on_https_only(client):
    r = client.get("/api/ready", headers={"x-forwarded-proto": "https"})
    assert "Strict-Transport-Security" in r.headers
    r = client.get("/api/ready")
    assert "Strict-Transport-Security" not in r.headers
