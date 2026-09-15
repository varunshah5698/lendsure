import os
import subprocess
import sys
from pathlib import Path


def test_health_identifies_service(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["service"] == "lendsure-api"
    assert response.json()["environment"] in {"development", "test"}


def test_health_has_request_id_and_security_headers(client):
    response = client.get("/api/health")
    assert response.headers.get("x-request-id")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in response.headers.get("content-security-policy", "")


def test_readiness_is_structured(client):
    response = client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert "ready" in body
    assert set(body["checks"]) == {"database", "tables", "ml_model"}


def test_production_rejects_demo_otp():
    env = os.environ.copy()
    env.update({
        "LENDSURE_ENV": "production",
        "LENDSURE_DEMO_OTP": "1",
        "LENDSURE_DB_PATH": "/tmp/lendsure-test.db",
    })
    result = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "LENDSURE_DEMO_OTP=1" in result.stderr + result.stdout
