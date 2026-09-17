"""Shared fixtures: each test gets a FRESH temp database + seeded borrower.

import app runs init_db() against the real DB once (idempotent, harmless).
Every role gets its OWN TestClient (separate cookie jar, same test DB) so
guest/lender sessions never leak into each other — exactly like real users.
"""
import os
import sys

# Explicit assignment keeps tests hermetic even when a developer shell or
# backend/.env has production SMTP settings exported.
os.environ["LENDSURE_DEMO_OTP"] = "1"
# Force demo delivery in tests even if the developer machine has real SMTP
# configured: tests must be hermetic (no network, no real emails sent).
os.environ["LENDSURE_SMTP_USER"] = ""
os.environ["LENDSURE_SMTP_APP_PASSWORD"] = ""
# Same for Twilio: app.py auto-loads backend/.env, which may hold real
# credentials on a dev machine. Tests must never touch live SMS.
os.environ["LENDSURE_SMS_PROVIDER"] = "none"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import app as app_module

SEED_BORROWER = (
    "B90001", "Test Borrower", 34, "Mumbai", "salaried", 60000, 200000, 24,
    "9811111111", "borrower@example.com", "1 Test Street", "dev-1", "ACC123",
    60000, 50000, 1, 20, "2026-01-01T00:00:00",
)


def _seed():
    conn = app_module.db()
    conn.execute(
        "INSERT INTO ls_borrowers (borrower_id, name, age, city, employment_type,"
        " monthly_income, requested_amount, tenure_months, phone, email,"
        " address_line, device_id, bank_account, avg_income_6m, avg_debt_6m,"
        " late_payments, max_days_past_due, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", SEED_BORROWER)
    conn.commit()
    conn.close()


@pytest.fixture()
def _db(tmp_path):
    app_module.DB_PATH = tmp_path / "test.db"
    app_module.init_db()
    _seed()
    return tmp_path


@pytest.fixture()
def client(_db):
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture()
def lender(_db):
    with TestClient(app_module.app) as c:
        r = c.post("/api/auth/register",
                   json={"name": "Tom", "username": "tom", "email": "t@example.com", "password": "Strongpass1"})
        assert r.status_code == 200, r.text
        r = c.post("/api/auth/login",
                   json={"email": "t@example.com", "password": "Strongpass1"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "lender"
        yield c


@pytest.fixture()
def guest(_db):
    with TestClient(app_module.app) as c:
        r = c.post("/api/auth/guest", json={"name": "guestuser"})
        assert r.status_code == 200, r.text
        yield c
