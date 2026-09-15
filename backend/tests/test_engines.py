"""Scoring math, bands, EMI — known values, no hand-waving."""
from lendsure.engines import RecommendationEngine, emi, full_analysis


def _borrower(**kw):
    base = dict(
        borrower_id="T1", name="T", age=35, city="Mumbai", employment_type="salaried",
        monthly_income=60000, requested_amount=200000, tenure_months=24,
        avg_income_6m=60000, avg_expenses_6m=30000, avg_debt_6m=50000,
        late_payments=0, max_days_past_due=0, defaults=0, loans_repaid=3,
        ontime_streak_months=12, salary_credits_6m=6, vouches_count=2,
        avg_vouch_trust=4.0, income_volatility=5.0, debt_trend=0.0,
        id_verification=2, address_verification=2, phone_verification=2,
    )
    base.update(kw)
    return base


def test_emi_known_values():
    assert emi(12000, 0, 12) == 1000.0
    assert emi(0, 12, 12) == 0.0
    # textbook case: 100k @ 12% over 12 months
    assert abs(emi(100000, 12, 12) - 8884.88) < 0.05


def test_emi_monotonic_in_rate():
    assert emi(100000, 15, 12) > emi(100000, 10, 12)


def test_full_analysis_deterministic_and_shaped():
    from lendsure.schema import DEFAULT_CONFIG
    a = full_analysis(_borrower(), [], [], False, DEFAULT_CONFIG)
    b = full_analysis(_borrower(), [], [], False, DEFAULT_CONFIG)
    assert a == b
    for key in ("risk", "fraud", "trust", "recommendation"):
        assert key in a, key
    assert 0 <= a["trust"]["trust_score"] <= 100


def test_terrible_profile_scores_worse():
    from lendsure.schema import DEFAULT_CONFIG
    good = full_analysis(_borrower(), [], [], False, DEFAULT_CONFIG)
    bad = full_analysis(_borrower(monthly_income=8000, late_payments=9,
                                  max_days_past_due=120, defaults=2), [], [], False,
                        DEFAULT_CONFIG)
    assert bad["trust"]["trust_score"] < good["trust"]["trust_score"]
    assert bad["recommendation"]["decision"] != "APPROVE" or \
        bad["recommendation"]["recommended_amount"] <= good["recommendation"]["recommended_amount"]
