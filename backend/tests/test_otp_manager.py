"""Central OTP manager: generation, cooldowns, burns, custom lengths."""
import app as app_module
from lendsure import otp as otp_manager


def test_code_length_config(monkeypatch):
    assert len(otp_manager.new_code()) == 6
    monkeypatch.setenv("LENDSURE_OTP_LEN", "4")
    assert otp_manager.code_length() == 4
    assert len(otp_manager.new_code()) == 4
    assert otp_manager.new_code().isdigit()
    monkeypatch.setenv("LENDSURE_OTP_LEN", "99")
    assert otp_manager.code_length() == 8  # clamped
    monkeypatch.setenv("LENDSURE_OTP_LEN", "abc")
    assert otp_manager.code_length() == 6  # invalid falls back


def test_phone_cooldown_on_immediate_resend(client):
    r = client.post("/api/auth/request-otp", json={"phone": "9333333333"})
    assert r.status_code == 200
    r = client.post("/api/auth/request-otp", json={"phone": "9333333333"})
    assert r.status_code == 429


def test_request_returns_otp_len(client):
    r = client.post("/api/auth/request-otp", json={"phone": "9444444444"})
    assert r.status_code == 200
    assert r.json()["otp_len"] == 6


def test_otp_config_endpoint(client):
    r = client.get("/api/auth/otp-config")
    assert r.status_code == 200
    d = r.json()
    assert d["otp_len"] == 6 and d["cooldown_sec"] == 60 and d["max_attempts"] == 5


def test_malformed_code_does_not_burn_attempts(client):
    client.post("/api/auth/request-otp", json={"phone": "9555555555"})
    conn = app_module.db()
    try:
        before = conn.execute("SELECT attempts FROM otps WHERE phone='9555555555' ORDER BY id DESC LIMIT 1").fetchone()["attempts"]
    finally:
        conn.close()
    r = client.post("/api/auth/verify-otp", json={"phone": "9555555555", "otp": "abc"})
    assert r.status_code == 400
    conn = app_module.db()
    try:
        after = conn.execute("SELECT attempts FROM otps WHERE phone='9555555555' ORDER BY id DESC LIMIT 1").fetchone()["attempts"]
    finally:
        conn.close()
    assert after == before


def test_manager_rejects_unknown_channel(client):
    import pytest
    from fastapi import HTTPException
    conn = app_module.db()
    try:
        with pytest.raises(ValueError):
            otp_manager.issue(conn, "pigeon", "x", ttl_min=5)
    finally:
        conn.close()
