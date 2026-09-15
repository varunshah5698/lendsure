"""LendSure feature registry — every model input documented.

Groups: IDENTITY, FINANCIAL, REPAYMENT, DEBT, BEHAVIOR, TRANSACTION,
DOCUMENT, FRAUD, APPLICATION. Engineered ratios are marked versioned (v3).
No protected characteristics are used as features.
"""
from __future__ import annotations

FEATURES: list[dict] = [
    # IDENTITY (7)
    {"name": "age", "group": "IDENTITY", "type": "numeric", "source": "application form", "range": "19-68", "missing": "n/a (required)"},
    {"name": "city", "group": "IDENTITY", "type": "categorical", "source": "application form", "range": "14 supported cities", "missing": "n/a (required)"},
    {"name": "employment_type", "group": "IDENTITY", "type": "categorical", "source": "application form", "range": "salaried|self-employed|business|daily-wage", "missing": "n/a (required)"},
    {"name": "employment_years", "group": "IDENTITY", "type": "numeric", "source": "application form", "range": ">= 0", "missing": "0"},
    {"name": "monthly_income", "group": "IDENTITY", "type": "numeric", "source": "stated income", "range": ">= 8000", "missing": "0"},
    {"name": "household_size", "group": "IDENTITY", "type": "numeric", "source": "application form", "range": "1-6", "missing": "1"},
    {"name": "dependents", "group": "IDENTITY", "type": "numeric", "source": "application form", "range": "0-4", "missing": "0"},
    # APPLICATION (4)
    {"name": "requested_amount", "group": "APPLICATION", "type": "numeric", "source": "loan request", "range": "10000-500000", "missing": "n/a (required)"},
    {"name": "tenure_months", "group": "APPLICATION", "type": "numeric", "source": "loan request", "range": "3|6|12|18|24", "missing": "12"},
    {"name": "purpose", "group": "APPLICATION", "type": "categorical", "source": "loan request", "range": "personal|business|medical|education|home-repair", "missing": "personal"},
    {"name": "first_time_borrower", "group": "APPLICATION", "type": "binary", "source": "derived from prev_loans", "range": "0|1", "missing": "1"},
    # REPAYMENT (6)
    {"name": "prev_loans", "group": "REPAYMENT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
    {"name": "loans_repaid", "group": "REPAYMENT", "type": "numeric", "source": "credit history", "range": "0-prev_loans", "missing": "0"},
    {"name": "late_payments", "group": "REPAYMENT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
    {"name": "avg_delay_days", "group": "REPAYMENT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
    {"name": "defaults", "group": "REPAYMENT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
    {"name": "max_days_past_due", "group": "REPAYMENT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
    # FINANCIAL (9)
    {"name": "avg_income_6m", "group": "FINANCIAL", "type": "numeric", "source": "6-month statements", "range": "> 0", "missing": "median"},
    {"name": "avg_expenses_6m", "group": "FINANCIAL", "type": "numeric", "source": "6-month statements", "range": ">= 0", "missing": "0"},
    {"name": "avg_debt_6m", "group": "FINANCIAL", "type": "numeric", "source": "6-month statements", "range": ">= 0", "missing": "0"},
    {"name": "income_volatility", "group": "FINANCIAL", "type": "numeric", "source": "derived (std/mean)", "range": ">= 0", "missing": "0"},
    {"name": "expense_trend", "group": "FINANCIAL", "type": "numeric", "source": "derived (slope/mean)", "range": "any", "missing": "0"},
    {"name": "debt_trend", "group": "FINANCIAL", "type": "numeric", "source": "derived (slope/mean)", "range": "any", "missing": "0"},
    {"name": "total_transactions_6m", "group": "TRANSACTION", "type": "numeric", "source": "6-month statements", "range": ">= 0", "missing": "0"},
    {"name": "bounced_payments_6m", "group": "TRANSACTION", "type": "numeric", "source": "6-month statements", "range": ">= 0", "missing": "0"},
    {"name": "disputed_txns_6m", "group": "TRANSACTION", "type": "numeric", "source": "6-month statements", "range": ">= 0", "missing": "0"},
    # DOCUMENT (6)
    {"name": "id_verification", "group": "DOCUMENT", "type": "ordinal", "source": "verification pipeline", "range": "0|suspicious 1|review 2|verified", "missing": "1"},
    {"name": "address_verification", "group": "DOCUMENT", "type": "ordinal", "source": "verification pipeline", "range": "0|1|2", "missing": "1"},
    {"name": "phone_verification", "group": "DOCUMENT", "type": "ordinal", "source": "verification pipeline", "range": "0|1|2", "missing": "1"},
    {"name": "bank_stmt_status", "group": "DOCUMENT", "type": "ordinal", "source": "verification pipeline", "range": "0|1|2", "missing": "1"},
    {"name": "income_doc_status", "group": "DOCUMENT", "type": "ordinal", "source": "verification pipeline", "range": "0|1|2", "missing": "1"},
    {"name": "doc_quality_score", "group": "DOCUMENT", "type": "numeric", "source": "OCR quality", "range": "15-99", "missing": "50"},
    # BEHAVIOR (6)
    {"name": "transaction_variance", "group": "BEHAVIOR", "type": "numeric", "source": "derived (std/mean)", "range": ">= 0", "missing": "0"},
    {"name": "night_txn_ratio", "group": "BEHAVIOR", "type": "numeric", "source": "transaction timestamps", "range": "0-1", "missing": "0"},
    {"name": "new_device_90d", "group": "FRAUD", "type": "binary", "source": "device signals", "range": "0|1", "missing": "0"},
    {"name": "applications_30d", "group": "FRAUD", "type": "numeric", "source": "application velocity", "range": ">= 1", "missing": "1"},
    {"name": "address_changes_12m", "group": "FRAUD", "type": "numeric", "source": "profile history", "range": ">= 0", "missing": "0"},
    {"name": "doc_avg_income", "group": "DOCUMENT", "type": "numeric", "source": "OCR extraction", "range": ">= 0", "missing": "median"},
    # TRUST NETWORK (5)
    {"name": "vouches_count", "group": "BEHAVIOR", "type": "numeric", "source": "community vouches", "range": ">= 0", "missing": "0"},
    {"name": "avg_vouch_trust", "group": "BEHAVIOR", "type": "numeric", "source": "community vouches", "range": "0-5", "missing": "0"},
    {"name": "community_tenure_years", "group": "BEHAVIOR", "type": "numeric", "source": "community record", "range": ">= 0", "missing": "0"},
    {"name": "group_memberships", "group": "BEHAVIOR", "type": "numeric", "source": "community record", "range": ">= 0", "missing": "0"},
    {"name": "guarantor_past_count", "group": "BEHAVIOR", "type": "numeric", "source": "community record", "range": ">= 0", "missing": "0"},
    # ACCOUNT HISTORY (8)
    {"name": "account_age_months", "group": "APPLICATION", "type": "numeric", "source": "platform record", "range": ">= 0", "missing": "0"},
    {"name": "prev_lenders_count", "group": "DEBT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
    {"name": "disputes_raised", "group": "TRANSACTION", "type": "numeric", "source": "dispute log", "range": ">= 0", "missing": "0"},
    {"name": "disputes_lost", "group": "TRANSACTION", "type": "numeric", "source": "dispute log", "range": "0-disputes_raised", "missing": "0"},
    {"name": "ontime_streak_months", "group": "REPAYMENT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
    {"name": "salary_credits_6m", "group": "FINANCIAL", "type": "numeric", "source": "6-month statements", "range": "0-6", "missing": "0"},
    {"name": "savings_balance", "group": "DEBT", "type": "numeric", "source": "account record", "range": ">= 0", "missing": "0"},
    {"name": "existing_debt_accounts", "group": "DEBT", "type": "numeric", "source": "credit history", "range": ">= 0", "missing": "0"},
]

GROUPS = ["IDENTITY", "FINANCIAL", "REPAYMENT", "DEBT", "BEHAVIOR", "TRANSACTION", "DOCUMENT", "FRAUD", "APPLICATION"]

ENGINEERED_DICT: list[dict] = [
    {"name": "dti", "group": "DEBT", "formula": "avg_debt_6m / avg_income_6m", "version": "v3"},
    {"name": "lti", "group": "DEBT", "formula": "requested_amount / avg_income_6m", "version": "v3"},
    {"name": "success_rate", "group": "REPAYMENT", "formula": "loans_repaid / prev_loans (0.5 if none)", "version": "v3"},
    {"name": "repayment_capacity", "group": "FINANCIAL", "formula": "(income - expenses) / income", "version": "v3"},
    {"name": "verified_count", "group": "DOCUMENT", "formula": "count of verifications == verified", "version": "v3"},
    {"name": "income_stability", "group": "FINANCIAL", "formula": "1 / (1 + income_volatility)", "version": "v3"},
    {"name": "expense_ratio", "group": "FINANCIAL", "formula": "avg_expenses_6m / avg_income_6m", "version": "v3"},
    {"name": "debt_service_ratio", "group": "DEBT", "formula": "debt / max(income - expenses, 1)", "version": "v3"},
    {"name": "savings_ratio", "group": "DEBT", "formula": "min(savings / (income*12), 10)", "version": "v3"},
    {"name": "bounced_rate", "group": "TRANSACTION", "formula": "bounced / total_transactions", "version": "v3"},
    {"name": "dispute_rate", "group": "TRANSACTION", "formula": "disputed / total_transactions", "version": "v3"},
    {"name": "vouch_strength", "group": "BEHAVIOR", "formula": "avg_vouch_trust if vouches else 0", "version": "v3"},
    {"name": "credit_mix_score", "group": "DOCUMENT", "formula": "weighted verification coverage", "version": "v3"},
    {"name": "behavioral_risk_score", "group": "FRAUD", "formula": "night*3 + device*2 + addr*1.5 + apps*0.5 + variance*2", "version": "v3"},
    {"name": "financial_health_composite", "group": "FINANCIAL", "formula": "capacity*3 + stability*2 + (1-dti)*2 + success*1.5 + streak*1.5", "version": "v3"},
]
