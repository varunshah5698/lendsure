"""
LendSure ML training — supervised default-prediction on ALL 51 input features.

Honest setup (mirrors real life):
  * borrowers.csv holds INPUTS only.
  * Labels below simulate *observed* 12-month default outcomes drawn from a latent
    risk process + noise, with their own seed. They are stored separately in
    data/labels.csv and never mixed into the borrower feature table.
  * A HistGradientBoosting model learns P(default) from the features with a
    stratified train/test split. Metrics are persisted; the fitted pipeline
    (preprocessing + model) is saved as a versioned artifact the backend loads
    for inference. Inference is a pure function: same input -> same output.

Run: python train_model.py
"""
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.inspection import permutation_importance
from sklearn.metrics import (accuracy_score, auc, average_precision_score,
                             brier_score_loss, classification_report, log_loss,
                             precision_score, recall_score, roc_curve)
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from lendsure.features import ENGINEERED, add_engineered

BASE = Path(__file__).parent
DATA = BASE / "data"
MODELS = BASE / "models"
MODEL_ID = "lendsure-ml-v3.2"
LABEL_SEED = 7

CAT = ["city", "employment_type", "purpose"]
DROP = ["borrower_id", "name"]
TARGET_RATE = (0.12, 0.26)


def make_labels(df: pd.DataFrame) -> pd.Series:
    """Latent default process + noise -> Bernoulli outcomes (own seed)."""
    rng = np.random.default_rng(LABEL_SEED)
    ver = df[["id_verification", "address_verification", "phone_verification"]].sum(axis=1)
    dti = df["avg_debt_6m"] / df["avg_income_6m"].clip(lower=1)
    lti = df["requested_amount"] / df["avg_income_6m"].clip(lower=1)
    S = 1.7  # signal strength: separates outcomes while keeping realistic noise
    logit = (
        -4.6 + S * (0.85 * df["defaults"] + 0.22 * df["late_payments"] + 0.02 * df["max_days_past_due"])
        + S * (1.5 * dti + 0.09 * lti)
        + S * (1.1 * df["income_volatility"] + 0.9 * df["transaction_variance"])
        + S * (0.25 * (6 - ver) + 0.14 * df["bounced_payments_6m"] + 0.18 * df["disputed_txns_6m"])
        + S * (0.35 * df["new_device_90d"] + 0.10 * df["applications_30d"])
        - S * (0.05 * df["ontime_streak_months"] + 0.004 * df["account_age_months"])
        - S * (0.10 * df["salary_credits_6m"] + 0.15 * (df["avg_vouch_trust"] * (df["vouches_count"] > 0)))
        + rng.normal(0, 0.35, len(df))
    )
    p = 1 / (1 + np.exp(-logit))
    return pd.Series((rng.random(len(df)) < p).astype(int), index=df.index), p


def validate_dataset(df: pd.DataFrame, y: pd.Series) -> dict:
    """Dataset quality report + target-leakage guard. Raises on leakage."""
    n = len(df)
    missing = {c: round(float(df[c].isna().mean()), 4) for c in df.columns if df[c].isna().any()}
    dup = int(df.duplicated().sum())
    impossible = {
        "negative_income": int((df["monthly_income"] < 0).sum()),
        "age_out_of_range": int(((df["age"] < 10) | (df["age"] > 100)).sum()),
        "repaid_gt_prev": int((df["loans_repaid"] > df["prev_loans"]).sum()),
        "disputes_lost_gt_raised": int((df["disputes_lost"] > df["disputes_raised"]).sum()),
    }
    allowed = {"employment_type": {"salaried", "self-employed", "business", "daily-wage"},
               "purpose": {"personal", "business", "medical", "education", "home-repair"}}
    invalid_cats = {c: sorted(set(map(str, df[c].unique())) - allowed[c]) for c in allowed}
    leak = [c for c in df.columns
            if c.lower() in ("label", "target", "outcome", "defaulted_12m", "default_flag", "y")]
    assert not leak, f"target leakage columns in features: {leak}"
    return {"n_rows": n, "missing": missing or "none", "duplicate_rows": dup,
            "duplicate_pct": round(dup / n, 4), "impossible_values": impossible,
            "invalid_categories": invalid_cats, "leakage_check": "pass",
            "label_rate": round(float(y.mean()), 4)}


def main():
    MODELS.mkdir(exist_ok=True)
    df = pd.read_csv(DATA / "borrowers.csv")
    y, p_true = make_labels(df)
    lab = pd.DataFrame({"borrower_id": df["borrower_id"], "defaulted_12m": y})
    lab.to_csv(DATA / "labels.csv", index=False)
    print(f"label rate: {y.mean():.1%} (target {TARGET_RATE[0]:.0%}-{TARGET_RATE[1]:.0%})")
    assert TARGET_RATE[0] <= y.mean() <= TARGET_RATE[1], "label rate out of band — retune latent process"

    X = add_engineered(df.drop(columns=DROP))
    num = [c for c in X.columns if c not in CAT]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
        ("num", StandardScaler(), num),
    ])

    # v3.2: balanced classes (recall was the weak spot) + stronger ensemble
    clf = HistGradientBoostingClassifier(
        max_iter=1000, learning_rate=0.035, max_leaf_nodes=31,
        min_samples_leaf=12, l2_regularization=1.0,
        max_depth=8, early_stopping=True, random_state=42,
        class_weight="balanced",
    )
    gbm2 = GradientBoostingClassifier(
        n_estimators=200, learning_rate=0.05, max_depth=5,
        min_samples_leaf=15, subsample=0.8, random_state=42
    )
    lin = LogisticRegression(max_iter=3000, C=0.3, solver="lbfgs")

    from sklearn.ensemble import VotingClassifier, StackingClassifier
    # Use stacking for better performance
    estimators = [("gbm", clf), ("gbm2", gbm2), ("logreg", lin)]
    vote = VotingClassifier(estimators, voting="soft", weights=[2, 1.5, 1])
    pipe = Pipeline([("pre", pre), ("model", vote)])

    # ---- dataset validation (quality report + leakage guard) ----
    validation = validate_dataset(df, y)
    (MODELS / "validation.json").write_text(json.dumps(validation, indent=2))
    print("validation:", json.dumps(validation))

    # train 60% / calibration 20% / test 20% (stratified, leakage-free)
    Xtr, Xtmp, ytr, ytmp = train_test_split(X, y, test_size=0.40, stratify=y, random_state=42)
    Xcal, Xte, ycal, yte = train_test_split(Xtmp, ytmp, test_size=0.50, stratify=ytmp, random_state=43)
    pipe.fit(Xtr, ytr)

    # Cross-validation for better estimate
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(pipe, X, y, cv=cv, scoring="roc_auc")

    # ---- Platt (sigmoid) calibration on the held-out calibration split ----
    from sklearn.linear_model import LogisticRegression as _LR
    raw_cal = pipe.predict_proba(Xcal)[:, 1].reshape(-1, 1)
    platt = _LR().fit(raw_cal, ycal)
    pa, pb = float(platt.coef_[0][0]), float(platt.intercept_[0])

    def calibrate(p):
        p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
        return 1 / (1 + np.exp(-(pa * p + pb)))

    raw = pipe.predict_proba(Xte)[:, 1]
    proba = calibrate(raw)
    # Tune the decision threshold for F1 on the calibration split (v3.1 used
    # a fixed 0.5, which starved recall on the imbalanced labels).
    from sklearn.metrics import f1_score as _f1
    cal_p = calibrate(pipe.predict_proba(Xcal)[:, 1])
    best_t, best_f1 = 0.5, -1.0
    for t in [round(x, 2) for x in np.arange(0.15, 0.65, 0.01)]:
        f1 = _f1(ycal, (cal_p >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_t, best_f1 = t, f1
    pred = (proba >= best_t).astype(int)
    fpr, tpr, _ = roc_curve(yte, proba)
    brier = float(brier_score_loss(yte, proba))
    ll = float(log_loss(yte, proba))
    curve = []
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        m = (proba > lo) & (proba <= hi) if lo > 0 else (proba <= hi)
        if m.sum() > 0:
            curve.append({"bin": [lo, hi], "mean_pred": round(float(proba[m].mean()), 4),
                          "frac_pos": round(float(np.asarray(yte)[m].mean()), 4),
                          "n": int(m.sum())})
    perm = permutation_importance(pipe, Xte, yte, n_repeats=8, random_state=42, scoring="roc_auc")
    feat_names = list(pipe.named_steps["pre"].get_feature_names_out())
    imp = sorted(zip(feat_names, perm.importances_mean), key=lambda t: -t[1])[:15]

    metrics = {
        "model_id": MODEL_ID,
        "trained_at": datetime.utcnow().isoformat(),
        "n_features_in": 51,
        "n_features_model": len(X.columns),
        "engineered": ENGINEERED,
        "n_rows": len(df),
        "label_rate": round(float(y.mean()), 4),
        "test_auc": round(float(auc(fpr, tpr)), 4),
        "test_ap": round(float(average_precision_score(yte, proba)), 4),
        "test_accuracy": round(float(accuracy_score(yte, pred)), 4),
        "test_precision": round(float(precision_score(yte, pred, zero_division=0)), 4),
        "test_recall": round(float(recall_score(yte, pred, zero_division=0)), 4),
        "brier_score": round(brier, 4),
        "log_loss": round(ll, 4),
        "calibration_method": "platt-sigmoid",
        "decision_threshold": best_t,
        "calibration": curve,
        "validation": validation,
        "cv_auc_mean": round(float(cv_scores.mean()), 4),
        "cv_auc_std": round(float(cv_scores.std()), 4),
        "top_drivers": [{"feature": f, "importance": round(float(v), 4)} for f, v in imp],
    }
    joblib.dump({"pipe": pipe, "platt_a": pa, "platt_b": pb, "model_id": MODEL_ID,
                 "threshold": best_t},
                MODELS / "risk_model.joblib")
    (MODELS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: v for k, v in metrics.items() if k != "top_drivers"}, indent=2))
    print("top drivers:", [d["feature"] for d in metrics["top_drivers"][:8]])
    print(f"\nartifact -> {MODELS/'risk_model.joblib'}")
    print(classification_report(yte, pred, target_names=["repaid", "defaulted"]))


if __name__ == "__main__":
    main()
