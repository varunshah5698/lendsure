"""Shared ML feature contract — training AND inference use this exact mapping.

51 raw inputs + 15 engineered ratios = 66 model columns. Any change here
requires retraining (train_model.py) since the artifact embeds the layout.
"""
from __future__ import annotations

ENGINEERED = [
    "dti", "lti", "success_rate", "repayment_capacity", "verified_count",
    "income_stability", "expense_ratio", "debt_service_ratio", "savings_ratio",
    "bounced_rate", "dispute_rate", "vouch_strength", "credit_mix_score",
    "behavioral_risk_score", "financial_health_composite",
]


def add_engineered(df):
    """Add derived ratios. Works on pandas DataFrames (train) — mirrored for
    single rows in ml.predict_proba via the same formulas."""
    df = df.copy()
    inc = df["avg_income_6m"].clip(lower=1)
    exp = df["avg_expenses_6m"].clip(lower=1)
    debt = df["avg_debt_6m"]

    # Core ratios
    df["dti"] = debt / inc
    df["lti"] = df["requested_amount"] / inc
    df["success_rate"] = (df["loans_repaid"] / df["prev_loans"].clip(lower=1)).where(
        df["prev_loans"] > 0, 0.5)
    df["repayment_capacity"] = (df["avg_income_6m"] - df["avg_expenses_6m"]) / inc
    df["verified_count"] = (df[["id_verification", "address_verification",
                                "phone_verification"]] == 2).sum(axis=1)

    # Enhanced features
    df["income_stability"] = 1.0 / (1.0 + df["income_volatility"])
    df["expense_ratio"] = df["avg_expenses_6m"] / inc
    df["debt_service_ratio"] = debt / (df["avg_income_6m"] - df["avg_expenses_6m"]).clip(lower=1)
    df["savings_ratio"] = (df["savings_balance"] / (inc * 12)).clip(upper=10)
    df["bounced_rate"] = df["bounced_payments_6m"] / df["total_transactions_6m"].clip(lower=1)
    df["dispute_rate"] = df["disputed_txns_6m"] / df["total_transactions_6m"].clip(lower=1)
    df["vouch_strength"] = df["avg_vouch_trust"] * (df["vouches_count"] > 0).astype(float)
    df["credit_mix_score"] = (
        (df["id_verification"] == 2).astype(float) * 2 +
        (df["bank_stmt_status"] == 2).astype(float) * 2 +
        (df["income_doc_status"] == 2).astype(float) * 2 +
        (df["vouches_count"] > 0).astype(float) * 1.5 +
        (df["group_memberships"] > 0).astype(float) * 1
    )
    df["behavioral_risk_score"] = (
        df["night_txn_ratio"] * 3 +
        df["new_device_90d"] * 2 +
        df["address_changes_12m"] * 1.5 +
        df["applications_30d"] * 0.5 +
        df["transaction_variance"] * 2
    )
    df["financial_health_composite"] = (
        df["repayment_capacity"] * 3 +
        df["income_stability"] * 2 +
        (1 - df["dti"].clip(upper=2) / 2) * 2 +
        df["success_rate"] * 1.5 +
        (df["ontime_streak_months"] / 36).clip(upper=1) * 1.5
    )
    return df


def engineer_row(b: dict) -> dict:
    """Single-row version for inference (identical math, no pandas needed)."""
    inc = max(b.get("avg_income_6m") or 1, 1)
    exp = max(b.get("avg_expenses_6m") or 1, 1)
    debt = b.get("avg_debt_6m") or 0
    prev = b.get("prev_loans") or 0
    txns = max(b.get("total_transactions_6m") or 1, 1)
    savings = b.get("savings_balance") or 0
    rep_cap = (inc - exp) / inc
    income_vol = b.get("income_volatility") or 0
    return {
        "dti": debt / inc,
        "lti": (b.get("requested_amount") or 0) / inc,
        "success_rate": (b.get("loans_repaid") or 0) / prev if prev > 0 else 0.5,
        "repayment_capacity": rep_cap,
        "verified_count": sum(1 for k in ("id_verification", "address_verification",
                                          "phone_verification") if b.get(k) == 2),
        "income_stability": 1.0 / (1.0 + income_vol),
        "expense_ratio": exp / inc,
        "debt_service_ratio": debt / max(inc - exp, 1),
        "savings_ratio": min(savings / max(inc * 12, 1), 10),
        "bounced_rate": (b.get("bounced_payments_6m") or 0) / txns,
        "dispute_rate": (b.get("disputed_txns_6m") or 0) / txns,
        "vouch_strength": (b.get("avg_vouch_trust") or 0) * (1 if (b.get("vouches_count") or 0) > 0 else 0),
        "credit_mix_score": (
            (2 if b.get("id_verification") == 2 else 0) +
            (2 if b.get("bank_stmt_status") == 2 else 0) +
            (2 if b.get("income_doc_status") == 2 else 0) +
            (1.5 if (b.get("vouches_count") or 0) > 0 else 0) +
            (1 if (b.get("group_memberships") or 0) > 0 else 0)
        ),
        "behavioral_risk_score": (
            (b.get("night_txn_ratio") or 0) * 3 +
            (b.get("new_device_90d") or 0) * 2 +
            (b.get("address_changes_12m") or 0) * 1.5 +
            (b.get("applications_30d") or 0) * 0.5 +
            (b.get("transaction_variance") or 0) * 2
        ),
        "financial_health_composite": (
            rep_cap * 3 +
            (1.0 / (1.0 + income_vol)) * 2 +
            max(1 - min(debt / inc, 2) / 2, 0) * 2 +
            ((b.get("loans_repaid") or 0) / prev if prev > 0 else 0.5) * 1.5 +
            min((b.get("ontime_streak_months") or 0) / 36, 1) * 1.5
        ),
    }
