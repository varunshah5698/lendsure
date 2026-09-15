"""Train + compare default-prediction models. Selection on REAL holdout only.

Run:  python -m ml_credit.train [--n-synth 1000000] [--quick]
--quick: 50k synthetic + tiny grids, for smoke-testing the pipeline.

Writes backend/models/credit_v4/: model.joblib, preprocessor.joblib,
features.json, city_encoder.json, metadata.json (full honest metrics).
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             confusion_matrix, fbeta_score, log_loss,
                             precision_recall_curve, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import UCI_URL, load_real, sha256_file
from .features import FEATURES, FEATURE_NOTES, GLOBAL_PRIOR, borrower_to_features
from .synthesize import CITY_W, fit_segments, fit_teacher, generate

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE.parent / "models" / "credit_v4"
SEED = 42

BANDS = [("Low", 0.0, 0.15), ("Medium", 0.15, 0.35),
         ("High", 0.35, 0.6), ("Critical", 0.6, 1.01)]


def pr_auc(y, p):
    return float(average_precision_score(y, p))


def evaluate(y, p, threshold):
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "pr_auc": pr_auc(y, p),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "logloss": float(log_loss(y, p)),
        "threshold": float(threshold),
        "f2": float(fbeta_score(y, pred, beta=2, zero_division=0)),
        "precision": float(tp / max(tp + fp, 1)),
        "recall": float(tp / max(tp + fn, 1)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "n": int(len(y)), "base_rate": float(np.mean(y)),
    }


def best_f2_threshold(y, p):
    prec, rec, thr = precision_recall_curve(y, p)
    f2 = 5 * prec * rec / np.maximum(4 * prec + rec, 1e-12)
    i = int(np.argmax(f2))
    return float(thr[max(i - 1, 0)]) if i > 0 else 0.5


def band_report(y, p):
    out = []
    for name, lo, hi in BANDS:
        m = (p >= lo) & (p < hi)
        out.append({"band": name, "n": int(m.sum()),
                    "share": float(m.mean()),
                    "default_rate": float(y[m].mean()) if m.sum() else 0.0,
                    "captured_defaults": float(y[m].sum() / max(y.sum(), 1))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-synth", type=int, default=1_000_000)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--exclude", default="",
                    help="comma-separated FEATURES to drop (fairness ablation, e.g. age,city_risk)")
    ap.add_argument("--out", default="credit_v4", help="models/<name> output dir")
    ap.add_argument("--only", default="",
                    help="comma subset of candidates to train (xgboost,lightgbm,hgb,random_forest_200k)")
    args = ap.parse_args()
    excluded = {f.strip() for f in args.exclude.split(",") if f.strip()}
    unknown = excluded - set(FEATURES)
    if unknown:
        raise SystemExit(f"unknown features in --exclude: {sorted(unknown)}")
    ACTIVE = [f for f in FEATURES if f not in excluded]
    print(f"[train] excluded features: {sorted(excluded) or 'none'} -> {len(ACTIVE)} active", flush=True)
    global OUT_DIR
    OUT_DIR = BASE.parent / "models" / args.out
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    real = load_real(DATA_DIR)
    xls = DATA_DIR / "default of credit card clients.xls"
    print(f"[train] real rows: {len(real)} default_rate={real['default'].mean():.4f}", flush=True)

    fit_df, sel_df = train_test_split(real, test_size=15000, stratify=real["default"], random_state=SEED)
    sel_df, test_df = train_test_split(sel_df, test_size=10000, stratify=sel_df["default"], random_state=SEED + 1)
    print(f"[train] split fit={len(fit_df)} select(REAL)={len(sel_df)} test(REAL)={len(test_df)}", flush=True)

    from .features import engineer_train
    fit_eng = engineer_train(fit_df)
    sel_eng = engineer_train(sel_df)
    test_eng = engineer_train(test_df)
    Xs, ys = sel_eng[ACTIVE].to_numpy(float), sel_eng["default"].to_numpy(int)
    Xt, yt = test_eng[ACTIVE].to_numpy(float), test_eng["default"].to_numpy(int)

    spec = fit_segments(fit_eng, k=16, seed=SEED, exclude=excluded)
    teacher = fit_teacher(fit_eng, seed=SEED, exclude=excluded)
    n_synth = 50_000 if args.quick else args.n_synth
    synth = generate(spec, teacher, fit_eng, n_synth, seed=7, exclude=excluded)
    print(f"[train] synthetic rows: {len(synth)} default_rate={synth['default'].mean():.4f}", flush=True)

    train_pool = pd.concat([fit_eng[ACTIVE + ["default"]], synth[ACTIVE + ["default"]]],
                           ignore_index=True)
    is_real = np.array([True] * len(fit_eng) + [False] * len(synth))
    # Real rows upweighted x20 so 15k real rows carry weight beside 1M synthetic.
    sample_weight = np.where(is_real, 20.0, 1.0)

    # city target-encoding fitted on TRAIN labels only (synthetic cities; real rows NaN->median)
    city_encoder = {"__median__": GLOBAL_PRIOR}
    if "city_risk" in ACTIVE:
        city_rates = synth.groupby("city")["default"].mean().to_dict()
        city_encoder = {**city_rates, "__median__": float(np.median(list(city_rates.values())))}
    Xtr_raw = train_pool[ACTIVE].copy()
    if "city_risk" in ACTIVE:
        mask_synth_city = ~is_real
        Xtr_raw.loc[mask_synth_city, "city_risk"] = synth["city_risk"].to_numpy()

    pre = Pipeline([("impute", SimpleImputer(strategy="median")),
                    ("scale", StandardScaler())])
    Xtr = pre.fit_transform(Xtr_raw)
    ytr = train_pool["default"].to_numpy(int)

    import xgboost as xgb
    import lightgbm as lgb

    only = {c.strip() for c in args.only.split(",") if c.strip()}
    cands = {}
    if not only or "xgboost" in only:
        print("[train] xgboost…", flush=True)
        x = xgb.XGBClassifier(n_estimators=3000, learning_rate=0.05, max_depth=6,
                              subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
                              scale_pos_weight=float((ytr == 0).sum() / max((ytr == 1).sum(), 1)),
                              tree_method="hist", n_jobs=8, random_state=SEED,
                              early_stopping_rounds=100, eval_metric="logloss")
        x.fit(Xtr, ytr, sample_weight=sample_weight, eval_set=[(pre.transform(Xs), ys)], verbose=False)
        cands["xgboost"] = x

    if not only or "lightgbm" in only:
        print("[train] lightgbm…", flush=True)
        l = lgb.LGBMClassifier(n_estimators=3000, learning_rate=0.05, num_leaves=63,
                               subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
                               scale_pos_weight=float((ytr == 0).sum() / max((ytr == 1).sum(), 1)),
                               n_jobs=8, random_state=SEED, verbose=-1)
        l.fit(Xtr, ytr, sample_weight=sample_weight,
              eval_set=[(pre.transform(Xs), ys)],
              callbacks=[lgb.early_stopping(100, verbose=False)])
        cands["lightgbm"] = l

    if not only or "hgb" in only:
        print("[train] hist-gradient-boosting…", flush=True)
        h = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06,
                                           max_leaf_nodes=63, l2_regularization=1.0,
                                           class_weight="balanced", random_state=SEED)
        h.fit(Xtr, ytr, sample_weight=sample_weight)
        cands["hgb"] = h

    if not only or "random_forest_200k" in only:
        print("[train] random-forest (200k stratified subsample)…", flush=True)
        sub_n = min(200_000, len(ytr))
        if sub_n >= len(ytr):
            sub_idx = np.arange(len(ytr))
        else:
            sub_idx = train_test_split(np.arange(len(ytr)), train_size=sub_n,
                                       stratify=ytr, random_state=SEED)[0]
        r = RandomForestClassifier(n_estimators=250, min_samples_leaf=20, n_jobs=8,
                                   class_weight="balanced_subsample", random_state=SEED)
        r.fit(Xtr[sub_idx], ytr[sub_idx])
        cands["random_forest_200k"] = r

    select_metrics = {}
    for name, m in cands.items():
        p = m.predict_proba(pre.transform(Xs))[:, 1]
        select_metrics[name] = evaluate(ys, p, best_f2_threshold(ys, p))
        sm = select_metrics[name]
        print(f"[select-REAL] {name:18s} PR-AUC={sm['pr_auc']:.4f} ROC-AUC={sm['roc_auc']:.4f} "
              f"Brier={sm['brier']:.4f} F2={sm['f2']:.4f} thr={sm['threshold']:.3f}", flush=True)

    best = max(select_metrics, key=lambda k: select_metrics[k]["pr_auc"])
    print(f"[train] selected on REAL PR-AUC: {best}", flush=True)
    winner = cands[best]
    thr = select_metrics[best]["threshold"]

    print("[train] isotonic calibration on REAL select…", flush=True)
    cal = CalibratedClassifierCV(winner, method="isotonic", cv="prefit")
    cal.fit(pre.transform(Xs), ys)
    p_test = cal.predict_proba(pre.transform(Xt))[:, 1]
    test_metrics = evaluate(yt, p_test, thr)
    tm = test_metrics
    print(f"[test-REAL] PR-AUC={tm['pr_auc']:.4f} ROC-AUC={tm['roc_auc']:.4f} Brier={tm['brier']:.4f} "
          f"F2={tm['f2']:.4f} P={tm['precision']:.4f} R={tm['recall']:.4f} "
          f"tn={tm['tn']} fp={tm['fp']} fn={tm['fn']} tp={tm['tp']}", flush=True)
    print("[test-REAL] bands:", json.dumps(band_report(yt, p_test)), flush=True)

    import sklearn, joblib as _jl
    joblib.dump(cal, OUT_DIR / "model.joblib")
    joblib.dump(pre, OUT_DIR / "preprocessor.joblib")
    (OUT_DIR / "features.json").write_text(json.dumps(ACTIVE, indent=1))
    (OUT_DIR / "city_encoder.json").write_text(json.dumps(city_encoder, indent=1))
    import xgboost as _x, lightgbm as _l
    metadata = {
        "model_id": "lendsure-credit-v4.0",
        "trained_at": pd.Timestamp.utcnow().isoformat(),
        "data_source": {
            "real": "UCI Default of Credit Card Clients (Yeh & Lien 2009)",
            "real_url": UCI_URL,
            "real_sha256": sha256_file(xls),
            "real_rows": len(real),
            "real_default_rate": float(real["default"].mean()),
            "synthetic_rows": len(synth),
            "synthetic_default_rate": float(synth["default"].mean()),
            "synthetic_method": ("segment-conditional bootstrap: KMeans(16) on real rows; resample members "
                "with replacement; jitter continuous dims only (~5% of std); discrete dims copied exactly; "
                "all dims clipped to real p1/p99 (heavy tails winsorized, disclosed); tenure conditioned on age; "
                "Indian city mix with documented prior multipliers; labels from real-fitted HGB teacher + 2% flip noise"),
            "real_rows_weight_x20_in_training": True,
        },
        "splits": {"fit_real": len(fit_df), "select_real": len(sel_df), "test_real": len(test_df),
                   "seed": SEED},
        "excluded_features": sorted(excluded),
        "active_features": ACTIVE,
        "fairness_note": ("Demo model; tuned to catch potential defaults, so some flags will be incorrect. "
                          "Age and city are included for demonstration purposes and must be "
                          "reviewed/removed before real-world lending decisions." if not excluded else
                          "Demo model; tuned to catch potential defaults, so some flags will be incorrect. "
                          "Retrained without " + ", ".join(sorted(excluded)) + " for fairness."),
        "candidates_select_real": select_metrics,
        "selected": best,
        "selection_criterion": "max PR-AUC on REAL select split (average precision; robust to imbalance)",
        "threshold_rule": "max F2 (beta=2, missing a default costs more than a false alarm) on REAL select",
        "test_real_metrics": test_metrics,
        "test_real_bands": band_report(yt, p_test),
        "bands": [{"name": n, "lo": lo, "hi": hi} for n, lo, hi in BANDS],
        "calibration": "isotonic on REAL select split (prefit)",
        "feature_notes": FEATURE_NOTES,
        "versions": {"sklearn": sklearn.__version__, "xgboost": _x.__version__,
                     "lightgbm": _l.__version__, "python": platform.python_version()},
        "train_seconds": round(time.time() - t0, 1),
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=1))
    print(f"[train] artifacts -> {OUT_DIR} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
