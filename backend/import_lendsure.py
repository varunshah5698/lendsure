"""Import pipeline: CSV -> ls_* tables -> baseline analysis for every borrower.

Flow: borrowers.csv -> ls_borrowers, financials.csv -> ls_financials,
      documents.csv -> ls_documents, then Backend Analysis -> ls_analyses ->
      ls_recommendations -> ls_evidence -> ls_audit.
Idempotent: safe to re-run (clears LendSure tables first, sessions/OTPs untouched).
Run: python import_lendsure.py
"""
import csv
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from lendsure.engines import full_analysis
from lendsure.schema import DDL, DEFAULT_CONFIG

BASE = Path(__file__).parent
DB = BASE / "lending.db"
DATA = BASE / "data"


def num(v, cast=float, default=0):
    try:
        return cast(v) if v not in (None, "") else default
    except (ValueError, TypeError):
        return default


INT_FIELDS = {"age", "household_size", "dependents", "tenure_months", "first_time_borrower",
              "prev_loans", "loans_repaid", "late_payments", "defaults", "max_days_past_due",
              "total_transactions_6m", "bounced_payments_6m", "disputed_txns_6m",
              "id_verification", "address_verification", "phone_verification",
              "bank_stmt_status", "income_doc_status", "doc_quality_score",
              "new_device_90d", "applications_30d", "address_changes_12m",
              "vouches_count", "group_memberships", "guarantor_past_count",
              "account_age_months", "prev_lenders_count", "disputes_raised", "disputes_lost",
              "ontime_streak_months", "salary_credits_6m", "existing_debt_accounts"}


def main():
    t0 = time.time()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.executescript(DDL)
    for _col in ("risk_factors", "fraud_signals", "trust_factors", "ml_score"):
        try:
            cur.execute(f"ALTER TABLE ls_analyses ADD COLUMN {_col} TEXT DEFAULT '[]'")
        except Exception:
            pass
    for t in ("ls_audit", "ls_evidence", "ls_recommendations", "ls_analyses",
              "ls_documents", "ls_financials", "ls_borrowers", "ls_config"):
        cur.execute(f"DELETE FROM {t}")
    ts = datetime.utcnow().isoformat()
    for k, v in DEFAULT_CONFIG.items():
        import json
        cur.execute("INSERT INTO ls_config (key, value, updated_at) VALUES (?,?,?)", (k, json.dumps(v), ts))

    borrowers = list(csv.DictReader(open(DATA / "borrowers.csv")))
    cols = [c for c in borrowers[0].keys() if c not in ("borrower_id", "name")]
    for r in borrowers:
        vals = [r["borrower_id"], r["name"]] + [r[c] for c in cols] + [ts]
        cur.execute(f"INSERT INTO ls_borrowers (borrower_id, name, {', '.join(cols)}, created_at)"
                    f" VALUES ({', '.join(['?'] * (len(vals)))})", vals)
    with open(DATA / "financials.csv") as f:
        for r in csv.DictReader(f):
            cur.execute("INSERT INTO ls_financials (borrower_id, month, label, income, expenses, debt,"
                        " transactions, bounced, disputed) VALUES (?,?,?,?,?,?,?,?,?)",
                        (r["borrower_id"], int(r["month"]), r["label"], num(r["income"]), num(r["expenses"]),
                         num(r["debt"]), int(r["transactions"]), int(r["bounced"]), int(r["disputed"])))
    with open(DATA / "documents.csv") as f:
        for r in csv.DictReader(f):
            cur.execute("INSERT INTO ls_documents (borrower_id, doc_type, file_name, status, quality_score, note, created_at)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (r["borrower_id"], r["doc_type"], r["file_name"], r["status"], int(r["quality_score"]), r["note"], ts))
    conn.commit()

    import json as _json
    cfg = {k: v for k, v in DEFAULT_CONFIG.items()}
    n = 0
    for r in borrowers:
        bid = r["borrower_id"]
        b = dict(r)
        for k in b:
            if k in ("borrower_id", "name", "city", "employment_type", "purpose"):
                continue
            b[k] = num(b[k], int if k in INT_FIELDS else float)
        snaps = [dict(x) for x in cur.execute("SELECT * FROM ls_financials WHERE borrower_id=? ORDER BY month", (bid,))]
        docs = [dict(x) for x in cur.execute("SELECT * FROM ls_documents WHERE borrower_id=?", (bid,))]
        res = full_analysis(b, snaps, docs, False, cfg)
        rr, fr, t, rec = res["risk"], res["fraud"], res["trust"], res["recommendation"]
        cur.execute(
            """INSERT INTO ls_analyses (borrower_id, model_version, risk_score, risk_level, fraud_score, fraud_risk,
               trust_score, confidence, decision, recommended_amount, interest_rate, duration_months,
               monthly_payment, ml_score, risk_factors, fraud_signals, trust_factors, input_snapshot, created_at, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bid, res.get("model_version", DEFAULT_CONFIG["model_version"]), rr["risk_score"], rr["risk_level"], fr["fraud_score"],
             fr["fraud_risk"], t["trust_score"], rec["confidence"], rec["decision"], rec["recommended_amount"],
             rec["interest_rate"], rec["duration_months"], rec["monthly_payment"], res.get("ml_proba"),
             _json.dumps(rr["factors"]), _json.dumps(fr["signals"]), _json.dumps(t["trust_factors"]),
             res["input_snapshot"], ts, "import"))
        aid = cur.lastrowid
        cur.execute(
            """INSERT INTO ls_recommendations (analysis_id, borrower_id, recommended_amount, interest_rate,
               duration_months, monthly_payment, total_repayment, decision, rationale, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (aid, bid, rec["recommended_amount"], rec["interest_rate"], rec["duration_months"],
             rec["monthly_payment"], rec["total_repayment"], rec["decision"], rec["rationale"], ts))
        for e in res["evidence"]:
            cur.execute("INSERT INTO ls_evidence (analysis_id, category, label, value, sort) VALUES (?,?,?,?,?)",
                        (aid, e["category"], e["label"], e["value"], e["sort"]))
        cur.execute("INSERT INTO ls_audit (borrower_id, analysis_id, actor, action, detail, created_at) VALUES (?,?,?,?,?,?)",
                    (bid, aid, "import", "analysis_completed",
                     _json.dumps({"risk": rr["risk_level"], "fraud": fr["fraud_risk"], "trust": t["trust_score"],
                                          "decision": rec["decision"], "model": DEFAULT_CONFIG["model_version"]}), ts))
        n += 1
        if n % 500 == 0:
            conn.commit()
    conn.commit()
    conn.close()
    print(f"Imported {n} borrowers + baseline analyses in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
