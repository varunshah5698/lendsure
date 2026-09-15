"""Shared feature definitions — ONE place used by training AND serving.

Every feature below is computable from (a) the UCI frame and (b) a
LendSure borrower record. Where the two worlds measure differently, the
mapping is explicit and shipped in metadata.json (FEATURE_NOTES), and all
features are z-scored by the pipeline so cross-domain scale differences
cannot silently break the model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import PAY_COLS, BILL_COLS, PAYAMT_COLS

FEATURES = [
    "credit_capacity",   # UCI: LIMIT_BAL | app: avg_income_6m
    "loan_amount",       # UCI: LIMIT_BAL | app: requested_amount
    "age",
    "dpd_max",           # worst months-past-due in 6m window
    "dpd_mean",          # mean months-past-due (negative = early)
    "late_count",        # months with any delay
    "severe_count",      # months with DPD >= 2
    "utilization",       # revolving use: bill / limit
    "pay_ratio",         # paid / billed (repayment discipline)
    "pay_volatility",    # std of monthly payments / mean bill
    "bill_trend",        # (last - first) / mean bill
    "tenure_months",     # UCI: MISSING -> NaN (median-imputed)
    "city_risk",         # UCI: MISSING -> NaN | app: target-encoded city prior
    "prev_defaults",     # prior serious delinquencies
    "dti",               # debt-to-income load
    "ontime_rate",       # share of clean months / successful repayments
]

FEATURE_NOTES = {
    "credit_capacity": "UCI LIMIT_BAL (credit limit, income-correlated) | app avg_income_6m. Different units; pipeline z-scores both.",
    "loan_amount": "UCI LIMIT_BAL as exposure proxy | app requested_amount.",
    "age": "UCI AGE | app age. Direct match, no proxy.",
    "dpd_max": "UCI max(PAY_*) | app round(max_days_past_due/30), floor 0.",
    "dpd_mean": "UCI mean(PAY_*) | app avg_delay_days/30 (may be negative).",
    "late_count": "UCI #(PAY_*>0) | app late_payments clipped to 0..6.",
    "severe_count": "UCI #(PAY_*>=2) | app (max_days_past_due>=60) + min(defaults,2).",
    "utilization": "UCI mean(BILL)/LIMIT | app avg_debt_6m / max(6*avg_income_6m,1), clipped 0..3.",
    "pay_ratio": "UCI mean(PAY_AMT/max(BILL_AMT,1)) clipped 0..2 | app loans_repaid/max(loans_repaid+late_payments,1).",
    "pay_volatility": "UCI std(PAY_AMT)/mean(BILL) | app income_volatility/100.",
    "bill_trend": "UCI (BILL6-BILL1)/mean(BILL) | app debt_trend as stored.",
    "tenure_months": "Absent from UCI (NaN, median-imputed) | app tenure_months. Learned mostly from synthetic rows.",
    "city_risk": "Absent from UCI (NaN) | app target-encoded city default prior fitted on TRAIN ONLY. City effect comes from the synthetic prior; reported as weak by design.",
    "prev_defaults": "UCI #(PAY_*>=3) | app defaults field.",
    "dti": "UCI BILL_AMT6/max(LIMIT_BAL,1) | app avg_debt_6m/max(avg_income_6m,1), clipped 0..5.",
    "ontime_rate": "UCI #(PAY_*<0)/6 | app ontime_streak_months/max(ontime+late+1,1) blended with salary_credits_6m/6.",
}

CITY_PRIOR = {  # synthetic-prior city default multipliers (documented assumption)
    "Mumbai": 0.20, "Delhi": 0.22, "Bengaluru": 0.18, "Chennai": 0.17,
    "Hyderabad": 0.18, "Kolkata": 0.23, "Pune": 0.17, "Ahmedabad": 0.19,
    "Jaipur": 0.21, "Surat": 0.19, "Lucknow": 0.24, "Kanpur": 0.25,
    "Nagpur": 0.22, "Indore": 0.20, "Bhopal": 0.23, "Patna": 0.27,
    "Kochi": 0.16, "Coimbatore": 0.17, "Vadodara": 0.19, "Other": 0.22,
}
GLOBAL_PRIOR = float(np.mean(list(CITY_PRIOR.values())))


def engineer_train(df: pd.DataFrame) -> pd.DataFrame:
    """UCI frame -> canonical features. Returns dataframe with FEATURES + default."""
    pay = df[PAY_COLS].to_numpy(dtype=float)
    bill = df[BILL_COLS].to_numpy(dtype=float)
    payamt = df[PAYAMT_COLS].to_numpy(dtype=float)
    limit = df["LIMIT_BAL"].to_numpy(dtype=float)
    mean_bill = bill.mean(axis=1)
    out = pd.DataFrame(index=df.index)
    out["credit_capacity"] = limit
    out["loan_amount"] = limit
    out["age"] = df["AGE"].to_numpy(dtype=float)
    out["dpd_max"] = pay.max(axis=1).clip(min=0)
    out["dpd_mean"] = pay.mean(axis=1)
    out["late_count"] = (pay > 0).sum(axis=1)
    out["severe_count"] = (pay >= 2).sum(axis=1)
    out["utilization"] = (mean_bill / np.maximum(limit, 1)).clip(0, 3)
    out["pay_ratio"] = (payamt / np.maximum(bill, 1)).mean(axis=1).clip(0, 2)
    out["pay_volatility"] = payamt.std(axis=1) / np.maximum(mean_bill, 1)
    out["bill_trend"] = (bill[:, -1] - bill[:, 0]) / np.maximum(mean_bill, 1)
    out["tenure_months"] = np.nan
    out["city_risk"] = np.nan
    out["prev_defaults"] = (pay >= 3).sum(axis=1)
    out["dti"] = (bill[:, -1] / np.maximum(limit, 1)).clip(0, 5)
    out["ontime_rate"] = (pay < 0).mean(axis=1)
    out["default"] = df["default"].to_numpy(dtype=int)
    return out[FEATURES + ["default"]]


def _num(v, default=np.nan) -> float:
    try:
        f = float(v)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def borrower_to_features(b: dict, city_encoder: dict | None = None) -> dict:
    """LendSure borrower record -> canonical features (same definitions)."""
    inc = max(_num(b.get("avg_income_6m"), 0.0), 0.0)
    debt = max(_num(b.get("avg_debt_6m"), 0.0), 0.0)
    late = int(np.clip(_num(b.get("late_payments"), 0.0), 0, 60))
    max_dpd_days = max(_num(b.get("max_days_past_due"), 0.0), 0.0)
    repaid = max(_num(b.get("loans_repaid"), 0.0), 0.0)
    defaults = max(_num(b.get("defaults"), 0.0), 0.0)
    ontime = max(_num(b.get("ontime_streak_months"), 0.0), 0.0)
    salary_credits = np.clip(_num(b.get("salary_credits_6m"), 0.0), 0, 6)
    city = (b.get("city") or "Other").strip() or "Other"
    if city_encoder:
        city_risk = float(city_encoder.get(city, city_encoder.get("__median__", GLOBAL_PRIOR)))
    else:
        city_risk = CITY_PRIOR.get(city, GLOBAL_PRIOR)
    return {
        "credit_capacity": inc if inc > 0 else np.nan,
        "loan_amount": _num(b.get("requested_amount"), np.nan),
        "age": _num(b.get("age"), np.nan),
        "dpd_max": round(max_dpd_days / 30.0),
        "dpd_mean": _num(b.get("avg_delay_days"), 0.0) / 30.0,
        "late_count": min(late, 6),
        "severe_count": (1 if max_dpd_days >= 60 else 0) + min(int(defaults), 2),
        "utilization": float(np.clip(debt / max(6 * inc, 1.0), 0, 3)) if inc > 0 else np.nan,
        "pay_ratio": float(repaid / max(repaid + late, 1.0)),
        "pay_volatility": _num(b.get("income_volatility"), np.nan) / 100.0,
        "bill_trend": _num(b.get("debt_trend"), 0.0),
        "tenure_months": _num(b.get("tenure_months"), np.nan),
        "city_risk": city_risk,
        "prev_defaults": defaults,
        "dti": float(np.clip(debt / max(inc, 1.0), 0, 5)) if inc > 0 else np.nan,
        "ontime_rate": float(np.clip(
            0.5 * (ontime / max(ontime + late + 1, 1.0)) + 0.5 * (salary_credits / 6.0), 0, 1)),
    }
