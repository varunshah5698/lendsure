"""Twilio Verify OTP path — HTTP stubbed, endpoint wiring is real."""
import app as app_module


def _db():
    return app_module.db()


def test_twilio_config_gating(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    assert app_module._twilio_configured() is False
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_VERIFY_SERVICE_SID", "VAxxx")
    monkeypatch.setenv("LENDSURE_SMS_PROVIDER", "twilio")
    assert app_module._twilio_configured() is True
    monkeypatch.setenv("LENDSURE_SMS_PROVIDER", "other")
    assert app_module._twilio_configured() is False


def test_twilio_send_stores_marker_not_code(client, monkeypatch):
    monkeypatch.setattr(app_module, "_twilio_configured", lambda: True)
    monkeypatch.setattr(app_module, "send_sms_otp", lambda phone: True)
    r = client.post("/api/auth/request-otp", json={"phone": "9666666666"})
    assert r.status_code == 200
    assert "demo_otp" not in r.json()  # never leak, even in demo mode
    conn = _db()
    try:
        row = conn.execute("SELECT code FROM otps WHERE phone='9666666666' ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row["code"] == app_module.TWILIO_OTP_MARKER


def test_twilio_send_failure_rolls_back_row(client, monkeypatch):
    monkeypatch.setattr(app_module, "_twilio_configured", lambda: True)
    monkeypatch.setattr(app_module, "send_sms_otp", lambda phone: False)
    r = client.post("/api/auth/request-otp", json={"phone": "9677777777"})
    assert r.status_code == 503
    conn = _db()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM otps WHERE phone='9677777777'").fetchone()["c"]
    finally:
        conn.close()
    assert n == 0


def test_twilio_verify_approved_creates_session(client, monkeypatch):
    monkeypatch.setattr(app_module, "_twilio_configured", lambda: True)
    monkeypatch.setattr(app_module, "send_sms_otp", lambda phone: True)
    monkeypatch.setattr(app_module, "check_sms_otp", lambda phone, code: True)
    client.post("/api/auth/request-otp", json={"phone": "9688888888"})
    r = client.post("/api/auth/verify-otp",
                    json={"phone": "9688888888", "otp": "123456", "name": "Tw"})
    assert r.status_code == 200
    assert r.json()["role"] == "lender"
    assert "token" not in r.json()
    assert client.get("/api/auth/me").status_code == 200


def test_twilio_verify_wrong_counts_attempts(client, monkeypatch):
    monkeypatch.setattr(app_module, "_twilio_configured", lambda: True)
    monkeypatch.setattr(app_module, "send_sms_otp", lambda phone: True)
    monkeypatch.setattr(app_module, "check_sms_otp", lambda phone, code: False)
    client.post("/api/auth/request-otp", json={"phone": "9699999999"})
    r = client.post("/api/auth/verify-otp",
                    json={"phone": "9699999999", "otp": "000000"})
    assert r.status_code == 400
    assert "attempt(s) left" in r.json()["detail"]
    conn = _db()
    try:
        n = conn.execute("SELECT attempts FROM otps WHERE phone='9699999999' ORDER BY id DESC LIMIT 1").fetchone()["attempts"]
    finally:
        conn.close()
    assert n == 1


def test_twilio_outage_is_503_not_500(client, monkeypatch):
    monkeypatch.setattr(app_module, "_twilio_configured", lambda: True)
    monkeypatch.setattr(app_module, "send_sms_otp", lambda phone: True)
    monkeypatch.setattr(app_module, "check_sms_otp", lambda phone, code: None)
    client.post("/api/auth/request-otp", json={"phone": "9600000000"})
    r = client.post("/api/auth/verify-otp",
                    json={"phone": "9600000000", "otp": "123456"})
    assert r.status_code == 503


def test_verify_post_request_shape(monkeypatch):
    import json as _json

    captured = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return _json.dumps({"status": "approved"}).encode()

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = req.data.decode()
        return FakeResp()

    monkeypatch.setattr(app_module, "urlopen", fake_urlopen)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok456")
    monkeypatch.setenv("TWILIO_VERIFY_SERVICE_SID", "VA789")
    out = app_module._twilio_verify_post("VerificationCheck", {"To": "+919681111111", "Code": "123456"})
    assert out == {"status": "approved"}
    assert captured["url"] == "https://verify.twilio.com/v2/Services/VA789/VerificationCheck"
    assert captured["auth"].startswith("Basic ")
    assert "tok456" not in captured["auth"]  # credentials stay encoded, never raw
    assert "Code=123456" in captured["body"]
