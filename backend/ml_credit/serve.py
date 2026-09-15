"""Serve credit-v4.0: calibrated PD + score + band + SHAP factors + priority.

Everything returned here is computed live from the trained artifacts.
If artifacts are absent, loaded() is False and callers must say so.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .features import FEATURES, borrower_to_features

BASE = Path(__file__).parent.parent
ART = BASE / "models" / "credit_v4"

FACTOR_LABELS = {
    "credit_capacity": "Credit capacity",
    "loan_amount": "Loan amount",
    "age": "Age",
    "dpd_max": "Worst months overdue",
    "dpd_mean": "Average delay",
    "late_count": "Late-payment months",
    "severe_count": "Serious delinquencies",
    "utilization": "Credit utilization",
    "pay_ratio": "Repayment discipline",
    "pay_volatility": "Payment volatility",
    "bill_trend": "Debt trend",
    "tenure_months": "Loan tenure",
    "city_risk": "City risk prior",
    "prev_defaults": "Previous defaults",
    "dti": "Debt-to-income load",
    "ontime_rate": "On-time record",
}

PRIORITY = {
    "Critical": {"code": "P1", "action": "Immediate field visit + senior review",
                 "why": "highest default probability in the book"},
    "High": {"code": "P2", "action": "Priority calling queue + schedule field visit",
             "why": "material default risk, early action recovers most"},
    "Medium": {"code": "P3", "action": "Reminder schedule + watch DPD movement",
               "why": "moderate risk, cheap to monitor"},
    "Low": {"code": "P4", "action": "Standard monitoring only",
            "why": "low predicted risk, no action needed"},
}


@lru_cache(maxsize=1)
def _bundle():
    need = ["model.joblib", "preprocessor.joblib", "features.json",
            "city_encoder.json", "metadata.json"]
    if not all((ART / f).exists() for f in need):
        return None
    return {
        "model": joblib.load(ART / "model.joblib"),
        "pre": joblib.load(ART / "preprocessor.joblib"),
        "features": json.loads((ART / "features.json").read_text()),
        "encoder": json.loads((ART / "city_encoder.json").read_text()),
        "meta": json.loads((ART / "metadata.json").read_text()),
    }


def loaded() -> bool:
    return _bundle() is not None


def feature_count() -> int:
    b = _bundle()
    return len(b["features"]) if b else 0


def metadata() -> dict | None:
    b = _bundle()
    return b["meta"] if b else None


def _band(pd_: float, bands: list) -> str:
    for band in bands:
        if band["lo"] <= pd_ < band["hi"]:
            return band["name"]
    return bands[-1]["name"]


def _shap_factors(model, x_row: np.ndarray, feature_names: list, top_k: int = 5) -> list:
    """Top drivers for ONE prediction via Tree SHAP (exact for tree models)."""
    try:
        import shap
        base = model
        # CalibratedClassifierCV wraps fitted clones in calibrated_classifiers_
        est = None
        ccs = getattr(base, "calibrated_classifiers_", None)
        if ccs:
            est = ccs[0].estimator if hasattr(ccs[0], "estimator") else ccs[0].base_estimator
        est = est or base
        explainer = shap.TreeExplainer(est)
        sv = explainer.shap_values(x_row.reshape(1, -1))
        if isinstance(sv, list):
            sv = sv[1] if len(sv) > 1 else sv[0]
        sv = np.asarray(sv).ravel()
        order = np.argsort(-np.abs(sv))[:top_k]
        out = []
        for i in order:
            v = float(sv[int(i)])
            if v == 0:
                continue
            out.append({
                "feature": feature_names[int(i)],
                "label": FACTOR_LABELS.get(feature_names[int(i)], feature_names[int(i)]),
                "direction": "increases risk" if v > 0 else "reduces risk",
                "weight": round(abs(v), 4),
            })
        return out
    except Exception:
        return []


def predict_borrower(borrower: dict) -> dict | None:
    b = _bundle()
    if not b:
        return None
    feats = borrower_to_features(borrower, b["encoder"])
    row = pd.DataFrame([{f: feats.get(f, np.nan) for f in b["features"]}])
    Xs = b["pre"].transform(row)
    pd_ = float(b["model"].predict_proba(Xs)[0, 1])
    pd_ = min(max(pd_, 0.0), 1.0)
    band = _band(pd_, b["meta"]["bands"])
    pri = PRIORITY[band]
    # DPD override (documented): 60+ days overdue is at least P2 whatever the model says.
    dpd_days = 0.0
    try:
        dpd_days = max(float(borrower.get("max_days_past_due") or 0), 0.0)
    except (TypeError, ValueError):
        pass
    if dpd_days >= 60 and band in ("Low", "Medium"):
        pri = PRIORITY["High"]
        pri_note = f"escalated to P2: {int(dpd_days)} days past due"
    else:
        pri_note = pri["why"]
    return {
        "model_id": b["meta"]["model_id"],
        "default_probability": round(pd_, 4),
        "risk_score": round(100 * (1 - pd_), 1),
        "risk_category": band,
        "recovery_priority": {**pri, "why": pri_note},
        "factors": _shap_factors(b["model"], Xs[0], b["features"]),
        "inputs_used": {f: (None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 3))
                        for f, v in feats.items()},
    }
