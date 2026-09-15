"""LendSure ML inference — loads the versioned artifact (trained by train_model.py).

Pure function at inference time: same 51 features -> same probability.
If the artifact is missing, returns None and engines fall back to rules.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).parent.parent
MODELS = BASE / "models"
ARTIFACT = MODELS / "risk_model.joblib"
METRICS = MODELS / "metrics.json"

MODEL_ID = "lendsure-ml-v3.2"

try:
    from data_gen import FEATURES  # noqa: F401
except Exception:  # pragma: no cover
    FEATURES = []


@lru_cache(maxsize=1)
def _load():
    if not ARTIFACT.exists():
        return None
    import joblib
    try:
        return joblib.load(ARTIFACT)
    except Exception:
        return None


def loaded() -> bool:
    return _load() is not None


def metrics() -> dict:
    if METRICS.exists():
        try:
            return json.loads(METRICS.read_text())
        except Exception:
            pass
    return {"model_id": MODEL_ID, "loaded": False}


def predict_proba(b: dict) -> float | None:
    """P(default within 12m) from all 51 input features + engineered ratios.
    Applies the stored Platt-sigmoid calibrator when the artifact carries one."""
    obj = _load()
    if obj is None or not FEATURES:
        return None
    try:
        import pandas as pd

        from .features import engineer_row
        row = {f: b.get(f) for f in FEATURES}
        row.update(engineer_row(b))
        if isinstance(obj, dict):  # calibrated v3.1+ artifact
            import numpy as np
            p = float(obj["pipe"].predict_proba(pd.DataFrame([row]))[0][1])
            p = max(1e-6, min(1 - 1e-6, p))
            p = 1 / (1 + np.exp(-(obj["platt_a"] * p + obj["platt_b"])))
        else:  # legacy bare-pipeline artifact
            p = float(obj.predict_proba(pd.DataFrame([row]))[0][1])
        return round(max(0.0, min(1.0, p)), 4)
    except Exception:
        return None
