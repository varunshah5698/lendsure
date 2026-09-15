"""Credit-v4 model: real outputs only — API must match the artifact metadata."""
import json
import os

from ml_credit import serve

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "models", "credit_v4", "metadata.json")


def test_model_metadata_is_honest():
    m = json.load(open(ART))
    assert m["model_id"].startswith("lendsure-credit-v4")
    assert m["test_real_metrics"]["pr_auc"] < 0.7  # no fantasy numbers
    assert "demo model" in m.get("fairness_note", "").lower()


def test_band_boundaries():
    from ml_credit.serve import _band
    bands = [{"name": "Low", "lo": 0.0, "hi": 0.15},
             {"name": "Medium", "lo": 0.15, "hi": 0.35},
             {"name": "High", "lo": 0.35, "hi": 0.6},
             {"name": "Critical", "lo": 0.6, "hi": 1.01}]
    assert _band(0.05, bands) == "Low"
    assert _band(0.2, bands) == "Medium"
    assert _band(0.5, bands) == "High"
    assert _band(0.9, bands) == "Critical"


def test_predict_single_shape(lender):
    r = lender.post("/api/ls/ml/credit/predict", json={"borrower_id": "B90001"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["model_id"].startswith("lendsure-credit-v4")
    assert 0.0 <= d["default_probability"] <= 1.0
    assert d["risk_category"] in ("Low", "Medium", "High", "Critical")
    assert 0 <= d["risk_score"] <= 100
    assert d["recovery_priority"]["code"] in ("P1", "P2", "P3", "P4")
    assert isinstance(d["factors"], list) and d["factors"]
    assert all(set(f) >= {"label", "direction"} for f in d["factors"])


def test_api_matches_artifact_metadata(lender):
    meta = json.load(open(ART))
    tm = meta["test_real_metrics"]
    info = lender.get("/api/ls/ml/credit/model").json()
    assert info["model_id"] == meta["model_id"]
    assert info["test_real_metrics"]["pr_auc"] == tm["pr_auc"]
    assert info["test_real_metrics"]["roc_auc"] == tm["roc_auc"]
    assert info["test_real_metrics"]["tp"] == tm["tp"]


def test_predict_batch(lender):
    r = lender.post("/api/ls/ml/credit/predict-batch",
                    json={"borrower_ids": ["B90001", "NOPE"]})
    assert r.status_code == 200
    d = r.json()
    assert len(d["results"]) == 1 and d["errors"].get("NOPE")


def test_guest_cannot_batch(guest):
    r = guest.post("/api/ls/ml/credit/predict-batch", json={"borrower_ids": ["B90001"]})
    assert r.status_code == 403
