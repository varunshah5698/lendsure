"""LendSure deterministic engines — transparent, config-driven, swappable for ML later.

RiskEngine / FraudEngine / TrustEngine / RecommendationEngine / EvidenceService
+ FinancialService (derived metrics) + amortizing EMI. Same input -> same output.
"""
from __future__ import annotations

import json
import math
from typing import Any


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _ml_model_id() -> str:
    """Active ML artifact id for display strings. Never hardcode versions."""
    try:
        from .ml import MODEL_ID
        return MODEL_ID
    except Exception:
        return "lendsure-ml"


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    """Standard amortizing EMI. Zero-rate safe."""
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate_pct / 1200.0
    if r <= 0:
        return round(principal / months, 2)
    f = (1 + r) ** months
    return round(principal * r * f / (f - 1), 2)


# ---------------- FinancialService (derived metrics) ----------------

class FinancialService:
    @staticmethod
    def derived(b: dict, snaps: list[dict]) -> dict:
        inc = b["avg_income_6m"] or 0
        exp = b["avg_expenses_6m"] or 0
        debt = b["avg_debt_6m"] or 0
        dti = round(debt / inc, 3) if inc else 9.99
        lti = round(b["requested_amount"] / inc, 2) if inc else 99.0
        surplus = inc - exp
        capacity = round(surplus / inc, 3) if inc else 0.0
        tot = b["prev_loans"] or 0
        success = round(b["loans_repaid"] / tot, 3) if tot else None
        return {
            "avg_income": inc, "avg_expenses": exp, "avg_debt": debt,
            "dti": dti, "lti": lti, "repayment_capacity": capacity,
            "success_rate": success,
            "interpretation": FinancialService.interpret(b),
        }

    @staticmethod
    def interpret(b: dict) -> list[str]:
        # Sparse/legacy borrower rows carry NULLs — never crash the narrative.
        def g(key, default=0.0):
            v = b.get(key, default)
            return default if v is None else v
        out = []
        v = g("income_volatility")
        out.append("Income is stable" if v < 0.12 else ("Income is moderately variable" if v < 0.25 else "Income is highly variable"))
        dt = g("debt_trend")
        out.append("Debt is increasing" if dt > 0.03 else ("Debt is decreasing" if dt < -0.03 else "Debt is flat"))
        et = g("expense_trend")
        out.append("Expenses are moderately increasing" if et > 0.03 else ("Expenses are easing" if et < -0.03 else "Expenses are steady"))
        dti = (g("avg_debt_6m") / g("avg_income_6m")) if g("avg_income_6m") else 9
        out.append("Debt burden is high relative to income" if dti > 0.6 else "Debt burden looks manageable")
        return out


# ---------------- RiskEngine ----------------

class RiskEngine:
    WEIGHTS = {"repayment": 30, "debt": 20, "income_stab": 12, "employment": 8,
               "loan_burden": 12, "behavior": 10, "verification": 8}

    @staticmethod
    def run(b: dict, cfg: dict, ml_p: float | None = None) -> dict:
        f = FinancialService.derived(b, [])
        parts: list[dict] = []

        if b["prev_loans"] == 0 and not any([
                b["loans_repaid"], b["late_payments"], b["defaults"], b["max_days_past_due"]]):
            rep = 45.0
            obs = "No prior loans (thin file)"
        else:
            # Recorded history always counts, even when prev_loans is 0 —
            # otherwise bad history on thin files scores a free pass.
            rep = clamp(b["defaults"] * 28 + b["late_payments"] * 5 + b["max_days_past_due"] * 0.5
                        + (b["avg_delay_days"] * 0.4 if b["late_payments"] else 0))
            obs = f"{b['loans_repaid']}/{max(b['prev_loans'], b['loans_repaid'] + b['late_payments'] + b['defaults'], 1)} repaid, {b['late_payments']} late, {b['defaults']} defaults"
        parts.append({"code": "repayment_history", "title": "Repayment history",
                      "observed": obs, "score": round(rep, 1), "weight": 30,
                      "impact": "raises" if rep >= 50 else "lowers",
                      "explanation": "Past repayment is the strongest predictor of future repayment."})

        debt_s = clamp(f["dti"] * 110 + b["existing_debt_accounts"] * 7)
        parts.append({"code": "debt_burden", "title": "Debt burden",
                      "observed": f"DTI {f['dti']:.2f}, {b['existing_debt_accounts']} open debt accounts",
                      "score": round(debt_s, 1), "weight": 20,
                      "impact": "raises" if debt_s >= 50 else "lowers",
                      "explanation": "High debt relative to income leaves little room for a new EMI."})

        inc_s = clamp(b["income_volatility"] * 320)
        parts.append({"code": "income_stability", "title": "Income stability",
                      "observed": f"6-month volatility {b['income_volatility']:.2f}",
                      "score": round(inc_s, 1), "weight": 12,
                      "impact": "raises" if inc_s >= 50 else "lowers",
                      "explanation": "Volatile income makes future repayment less predictable."})

        emp_s = clamp(max(0.0, 60 - b["employment_years"] * 12) + (10 if b["employment_type"] == "daily-wage" else 0))
        parts.append({"code": "employment", "title": "Employment stability",
                      "observed": f"{b['employment_type']}, {b['employment_years']}y",
                      "score": round(emp_s, 1), "weight": 8,
                      "impact": "raises" if emp_s >= 50 else "lowers",
                      "explanation": "Longer, stable employment supports repayment capacity."})

        loan_s = clamp(f["lti"] * 13)
        parts.append({"code": "loan_burden", "title": "Requested loan burden",
                      "observed": f"Asking {f['lti']:.1f}x monthly income",
                      "score": round(loan_s, 1), "weight": 12,
                      "impact": "raises" if loan_s >= 50 else "lowers",
                      "explanation": "Larger requests relative to income strain monthly cash flow."})

        beh_s = clamp(b["bounced_payments_6m"] * 16 + b["disputed_txns_6m"] * 12 + b["night_txn_ratio"] * 60)
        parts.append({"code": "payment_behavior", "title": "Payment behavior",
                      "observed": f"{b['bounced_payments_6m']} bounced, {b['disputed_txns_6m']} disputed in 6 months",
                      "score": round(beh_s, 1), "weight": 10,
                      "impact": "raises" if beh_s >= 50 else "lowers",
                      "explanation": "Bounced and disputed payments signal cash-flow stress."})

        missing = sum(1 for k in ("id_verification", "address_verification", "phone_verification") if b[k] < 2)
        ver_s = clamp(missing * 30)
        parts.append({"code": "verification", "title": "Verification gaps",
                      "observed": f"{3 - missing}/3 identity checks verified",
                      "score": round(ver_s, 1), "weight": 8,
                      "impact": "raises" if ver_s >= 50 else "lowers",
                      "explanation": "Unverified identity weakens every other signal."})

        score = round(sum(p["score"] * p["weight"] for p in parts) / 100, 1)
        if ml_p is not None:
            blend = float(cfg.get("ml_blend", 0.5))
            ml_score = round(ml_p * 100, 1)
            score = round((1 - blend) * score + blend * ml_score, 1)
            for p in parts:
                p["weight"] = round(p["weight"] * (1 - blend), 1)
            parts.append({"code": "ml_default_model", "title": "ML default model (51 features)",
                          "observed": f"P(default in 12m) = {ml_p:.0%} ({_ml_model_id()})",
                          "score": ml_score, "weight": round(blend * 100, 1),
                          "impact": "raises" if ml_score >= 50 else "lowers",
                          "explanation": "Gradient-boosted model trained on observed repayment outcomes; blended with rules."})
        level = "LOW" if score < cfg["risk_low_max"] else ("MEDIUM" if score < cfg["risk_medium_max"] else "HIGH")
        ver_cov = sum(1 for k in ("id_verification", "address_verification", "phone_verification",
                                  "bank_stmt_status", "income_doc_status") if b[k] == 2)
        confidence = round(clamp(55 + ver_cov * 7 + (0 if b["first_time_borrower"] else 6)
                                 - (4 if level == "HIGH" else 0), 30, 97), 1)
        return {"risk_score": score, "risk_level": level, "confidence": confidence, "factors": parts}


# ---------------- FraudEngine ----------------

class FraudEngine:
    @staticmethod
    def run(b: dict, docs: list[dict], dup_phone: bool, cfg: dict) -> dict:
        signals: list[dict] = []

        def add(code, title, evidence, severity, weight):
            signals.append({"code": code, "title": title, "evidence": evidence,
                            "severity": severity, "weight": weight})

        stated, doc_inc = b["monthly_income"] or 0, b["doc_avg_income"] or 0
        if stated and doc_inc:
            drift = abs(stated - doc_inc) / stated
            if drift > 0.4:
                add("income_mismatch", "Potential income inconsistency",
                    f"Stated {stated:,.0f}/mo vs document-derived {doc_inc:,.0f}/mo (drift {drift:.0%}).",
                    "high" if drift > 0.7 else "medium", 30 if drift > 0.7 else 18)

        statuses = [d["status"] for d in docs]
        if "suspicious" in statuses:
            bad = [d["doc_type"] for d in docs if d["status"] == "suspicious"]
            add("suspect_document", "Potential document issue",
                f"{', '.join(bad)} flagged suspicious with quality review pending.",
                "high", 30)
        elif "needs_review" in statuses:
            n = statuses.count("needs_review")
            add("doc_review", "Documents need review",
                f"{n} document(s) awaiting verification before full confidence.",
                "low", 8)

        if b["transaction_variance"] > 0.5:
            add("txn_variance", "Unusual transaction pattern",
                f"Monthly transaction variance {b['transaction_variance']:.2f} is well above normal.",
                "medium", 14)
        if b["bounced_payments_6m"] >= 3:
            add("bounced_cluster", "Repeated bounced payments",
                f"{b['bounced_payments_6m']} bounced payments in six months.",
                "medium", 14)
        if b["disputed_txns_6m"] >= 2:
            add("disputed_cluster", "Multiple disputed transactions",
                f"{b['disputed_txns_6m']} disputed transactions in six months.",
                "medium", 12)
        if dup_phone:
            add("duplicate_application", "Possible repeat application",
                "This phone number already appears on another borrower record.",
                "medium", 15)
        if b["applications_30d"] >= 3:
            add("velocity", "High application velocity",
                f"{b['applications_30d']} applications in the last 30 days.",
                "medium" if b["applications_30d"] >= 4 else "low", 12 if b["applications_30d"] >= 4 else 6)
        if b["new_device_90d"] and b["applications_30d"] >= 2:
            add("device_velocity", "New device with repeat applications",
                "Application from a new device combined with repeat applications.",
                "low", 6)
        lti = (b["requested_amount"] / b["avg_income_6m"]) if b["avg_income_6m"] else 99
        if b["first_time_borrower"] and lti > 5:
            add("thin_large_request", "Large first-time request",
                f"First-time borrower requesting {lti:.1f}x monthly income.",
                "medium", 12)

        score = round(clamp(sum(s["weight"] for s in signals)), 1)
        risk = "LOW" if score < cfg["fraud_low_max"] else ("MEDIUM" if score < cfg["fraud_medium_max"] else "HIGH")
        return {"fraud_score": score, "fraud_risk": risk, "signals": signals,
                "note": "Signals are potential indicators, not accusations. Review evidence before deciding."}


# ---------------- TrustEngine ----------------

class TrustEngine:
    FACTORS = [("identity", 15), ("documents", 15), ("repayment", 20), ("financial", 15),
               ("behavior", 10), ("network", 10), ("disputes", 5), ("fraud_signals", 10)]

    @staticmethod
    def run(b: dict, docs: list[dict], fraud: dict) -> dict:
        f = FinancialService.derived(b, [])
        out: list[dict] = []

        id_s = (b["id_verification"] * 33.4 + b["address_verification"] * 33.3 + b["phone_verification"] * 33.3) / 2
        out.append({"code": "identity", "title": "Identity", "score": round(clamp(id_s), 1), "weight": 15,
                    "evidence": f"ID/phone/address checks: {b['id_verification']}/{b['address_verification']}/{b['phone_verification']} (2=verified)."})

        q = b["doc_quality_score"]
        doc_s = clamp(q * (1.0 if "suspicious" not in [d["status"] for d in docs] else 0.55))
        out.append({"code": "documents", "title": "Documents", "score": round(doc_s, 1), "weight": 15,
                    "evidence": f"{len(docs)} documents on file, quality {q}/100."})

        if b["prev_loans"] == 0 and not any([
                b["loans_repaid"], b["late_payments"], b["defaults"], b["max_days_past_due"]]):
            rep_s, rep_e = 45.0, "No prior loans — neutral starting point."
        else:
            # Any recorded history (even with prev_loans==0) must count:
            # otherwise defaults/lates on thin files score a free pass.
            rep_s = clamp(100 - b["defaults"] * 30 - b["late_payments"] * 6 - b["max_days_past_due"] * 0.4)
            rep_e = f"{b['loans_repaid']}/{max(b['prev_loans'], b['loans_repaid'] + b['late_payments'] + b['defaults'], 1)} repaid."
        out.append({"code": "repayment", "title": "Repayment", "score": round(rep_s, 1), "weight": 20, "evidence": rep_e})

        fin_s = clamp(100 - f["dti"] * 80 - b["income_volatility"] * 120 + max(0, f["repayment_capacity"]) * 30)
        out.append({"code": "financial", "title": "Financial Stability", "score": round(fin_s, 1), "weight": 15,
                    "evidence": f"DTI {f['dti']:.2f}, capacity {f['repayment_capacity']:.0%} of income."})

        beh_s = clamp(100 - b["bounced_payments_6m"] * 14 - b["disputed_txns_6m"] * 10 - b["night_txn_ratio"] * 50)
        out.append({"code": "behavior", "title": "Payment Behavior", "score": round(beh_s, 1), "weight": 10,
                    "evidence": f"{b['bounced_payments_6m']} bounced, {b['disputed_txns_6m']} disputed (6m)."})

        if b["vouches_count"] == 0:
            net_s, net_e = 35.0, "No community vouches yet."
        else:
            net_s = clamp((b["avg_vouch_trust"] / 5) * 80 + min(20, b["vouches_count"] * 4))
            net_e = f"{b['vouches_count']} vouches, avg {b['avg_vouch_trust']}/5."
        out.append({"code": "network", "title": "Trust Network", "score": round(net_s, 1), "weight": 10, "evidence": net_e})

        disp_s = clamp(100 - b["disputes_lost"] * 30 - b["disputes_raised"] * 8)
        out.append({"code": "disputes", "title": "Disputes", "score": round(disp_s, 1), "weight": 5,
                    "evidence": f"{b['disputes_raised']} raised, {b['disputes_lost']} lost."})

        fraud_s = clamp(100 - fraud["fraud_score"] * 1.2)
        out.append({"code": "fraud_signals", "title": "Fraud Signals", "score": round(fraud_s, 1), "weight": 10,
                    "evidence": f"{len(fraud['signals'])} potential signal(s), fraud {fraud['fraud_risk']}."})

        score = round(sum(x["score"] * x["weight"] for x in out) / 100, 1)
        return {"trust_score": score, "trust_factors": out}


# ---------------- RecommendationEngine ----------------

class RecommendationEngine:
    @staticmethod
    def run(b: dict, risk: dict, fraud: dict, trust: dict, cfg: dict,
            amount: float | None = None, rate: float | None = None,
            duration: int | None = None) -> dict:
        inc = b["avg_income_6m"] or b["monthly_income"] or 1
        affordable = inc * (cfg["afford_base_mult"] + (trust["trust_score"] / 100) * cfg["afford_trust_mult"])
        requested = b["requested_amount"]
        p = round(min(requested if amount is None else amount, max(5000, affordable)), -2)

        band = cfg["interest_low"] if risk["risk_level"] == "LOW" else (
            cfg["interest_medium"] if risk["risk_level"] == "MEDIUM" else cfg["interest_high"])
        lo, hi = band
        frac = (risk["risk_score"] % 35) / 35 if risk["risk_level"] != "HIGH" else (risk["risk_score"] - 65) / 35
        r = round(lo + clamp(frac, 0, 1) * (hi - lo), 1) if rate is None else rate

        n = duration or min(b["tenure_months"], cfg["max_tenure_months"])
        if risk["risk_level"] == "HIGH":
            n = min(n, cfg["high_risk_tenure_cap"])
        pay = emi(p, r, n)
        total = round(pay * n, 2)

        high_sev = sum(1 for s in fraud["signals"] if s["severity"] == "high")
        if risk["risk_score"] >= cfg["reject_risk_score"] or fraud["fraud_score"] >= 75 or high_sev >= 2:
            decision = "REJECT"
        elif fraud["fraud_score"] >= cfg["manual_review_fraud_score"] or risk["risk_level"] == "HIGH":
            decision = "MANUAL_REVIEW"
        elif p < requested * cfg["min_recommended_ratio"]:
            decision = "REDUCE_AMOUNT"
        elif risk["risk_level"] == "MEDIUM" or fraud["fraud_risk"] == "MEDIUM" or trust["trust_score"] < cfg["approve_trust_min"]:
            decision = "APPROVE_WITH_CONDITIONS"
        else:
            decision = "APPROVE"

        why = {
            "APPROVE": "Low risk, clean fraud screen and strong trust support full disbursal.",
            "APPROVE_WITH_CONDITIONS": "Fundable, but medium risk or trust gaps call for safeguards (guarantor, tranches).",
            "REDUCE_AMOUNT": "Affordability supports a smaller amount than requested.",
            "MANUAL_REVIEW": "High fraud signals or high risk need human review before any disbursal.",
            "REJECT": "Risk or fraud exceeds tolerance. Decline with documented reasons.",
        }[decision]
        burden = round(pay / inc, 3) if inc else 9.99
        conf = round(clamp(0.6 * risk["confidence"] + 0.4 * (100 - fraud["fraud_score"] * 0.5), 30, 97), 1)
        return {"recommended_amount": p, "interest_rate": r, "duration_months": n,
                "monthly_payment": pay, "total_repayment": total, "repayment_burden": burden,
                "decision": decision, "rationale": why, "confidence": conf}


# ---------------- EvidenceService ----------------

class EvidenceService:
    @staticmethod
    def build(b: dict, f: dict) -> list[dict]:
        g: list[dict] = []

        def grp(category: str, items: list[tuple[str, str]]):
            for i, (label, value) in enumerate(items):
                g.append({"category": category, "label": label, "value": value, "sort": i})

        grp("Financial", [
            ("Average monthly income", f"₹{f['avg_income']:,.0f}"),
            ("Average monthly expenses", f"₹{f['avg_expenses']:,.0f}"),
            ("Average debt", f"₹{f['avg_debt']:,.0f}"),
            ("Debt-to-income", f"{f['dti']:.2f}"),
            ("Loan-to-income (requested)", f"{f['lti']:.1f}x"),
            ("Repayment capacity", f"{f['repayment_capacity']:.0%} of income"),
        ])
        grp("Repayment", [
            ("Previous loans", str(b["prev_loans"])),
            ("Successfully repaid", str(b["loans_repaid"])),
            ("Late payments", f"{b['late_payments']} (avg delay {b['avg_delay_days']} days)"),
            ("Defaults", str(b["defaults"])),
            ("Success rate", f"{f['success_rate']:.1%}" if f["success_rate"] is not None else "No history"),
            ("On-time streak", f"{b['ontime_streak_months']} months"),
        ])
        grp("Verification", [
            ("Identity", ["Missing", "Pending", "Verified"][b["id_verification"]]),
            ("Address", ["Missing", "Pending", "Verified"][b["address_verification"]]),
            ("Phone", ["Missing", "Pending", "Verified"][b["phone_verification"]]),
            ("Bank statement", ["Suspicious", "Needs review", "Verified"][b["bank_stmt_status"]]),
            ("Income document", ["Suspicious", "Needs review", "Verified"][b["income_doc_status"]]),
            ("Document quality", f"{b['doc_quality_score']}/100"),
        ])
        grp("Trust Network", [
            ("Community vouches", str(b["vouches_count"])),
            ("Average voucher trust", f"{b['avg_vouch_trust']}/5" if b["vouches_count"] else "—"),
            ("Community tenure", f"{b['community_tenure_years']} years"),
            ("Group memberships", str(b["group_memberships"])),
            ("Account age", f"{b['account_age_months']} months"),
            ("Savings balance", f"₹{b['savings_balance']:,.0f}"),
        ])
        return g


# Neutral defaults for missing/NULL borrower fields. Real DB rows always
# carry values, so this changes nothing for them — it only stops sparse or
# legacy rows from crashing the pipeline with KeyError/TypeError.
# Unknown keys default to 0; known text keys default to "".
_BORROWER_TEXT_KEYS = {"borrower_id", "name", "city", "employment_type", "purpose"}

# Every key the engine reads directly. Missing/NULL fields fall back to the
# neutral zero so sparse or legacy rows analyze instead of crashing.
_BORROWER_NUM_KEYS = (
    "age tenure_months employment_years monthly_income requested_amount "
    "avg_income_6m avg_expenses_6m avg_debt_6m late_payments max_days_past_due "
    "defaults loans_repaid prev_loans vouches_count avg_vouch_trust "
    "applications_30d disputed_txns_6m bounced_payments_6m phone_verification "
    "address_verification id_verification night_txn_ratio income_volatility "
    "first_time_borrower transaction_variance new_device_90d income_doc_status "
    "group_memberships existing_debt_accounts doc_quality_score doc_avg_income "
    "disputes_raised disputes_lost bank_stmt_status avg_delay_days "
    "ontime_streak_months salary_credits_6m account_age_months savings_balance "
    "total_transactions_6m debt_trend expense_trend household_size dependents "
    "credit_score bureau_score community_tenure_years"
).split()


def _normalize_borrower(b: dict) -> dict:
    out = {k: ("" if k in _BORROWER_TEXT_KEYS else 0) for k in _BORROWER_TEXT_KEYS | set(_BORROWER_NUM_KEYS)}
    out["age"] = 30
    out["tenure_months"] = 12
    for k, v in (b or {}).items():
        if v is None:
            continue  # keep neutral default
        out[k] = v
    return out


def full_analysis(b: dict, snaps: list[dict], docs: list[dict], dup_phone: bool, cfg: dict) -> dict:
    """Run the whole pipeline. Pure function — easy to unit test."""
    from .ml import MODEL_ID as ML_ID, predict_proba
    from .schema import MODEL_VERSION as RULES_ID
    b = _normalize_borrower(b)
    fin = FinancialService.derived(b, snaps)
    ml_p = predict_proba(b)
    risk = RiskEngine.run(b, cfg, ml_p)
    fraud = FraudEngine.run(b, docs, dup_phone, cfg)
    trust = TrustEngine.run(b, docs, fraud)
    rec = RecommendationEngine.run(b, risk, fraud, trust, cfg)
    evidence = EvidenceService.build(b, fin)
    snapshot = json.dumps({k: b.get(k) for k in sorted(b.keys()) if k != "created_at"}, sort_keys=True, default=str)
    return {"financial": fin, "risk": risk, "fraud": fraud, "trust": trust,
            "recommendation": rec, "evidence": evidence, "input_snapshot": snapshot,
            "ml_proba": ml_p, "model_version": ML_ID if ml_p is not None else RULES_ID}
