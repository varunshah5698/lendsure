"""Credit-v4 model serving: single + batch default predictions.

Every number returned is computed live from backend/models/credit_v4
artifacts (see ml_credit/metadata.json for how they were trained).
If artifacts are missing the endpoints answer 503 — never placeholder data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ls", tags=["credit-ml"])

_DB = None
_RESOLVE = lambda auth: None  # noqa: E731


def configure(db_factory, session_resolver):
    global _DB, _RESOLVE
    _DB = db_factory
    _RESOLVE = session_resolver


def now() -> str:
    return datetime.utcnow().isoformat()


def _need(authorization: Optional[str], x_api_key: Optional[str], *perms: str) -> str:
    from .api import require_perm
    return require_perm(authorization, x_api_key, *perms)


def _actor(authorization: Optional[str], x_api_key: Optional[str] = None) -> str:
    from .api import actor_of
    return actor_of(authorization, x_api_key)


def _engine():
    from ml_credit import serve as _serve
    if not _serve.loaded():
        raise HTTPException(503, "Credit model artifacts are not installed on this server")
    return _serve


def _borrower_row(conn, bid: str) -> dict:
    b = conn.execute("SELECT * FROM ls_borrowers WHERE borrower_id=?", (bid,)).fetchone()
    if not b:
        raise HTTPException(404, "Borrower not found")
    return dict(b)


def _score_and_log(conn, bid: str, actor: str) -> dict:
    serve = _engine()
    out = serve.predict_borrower(_borrower_row(conn, bid))
    out["borrower_id"] = bid
    conn.execute("INSERT INTO ls_predictions (borrower_id, analysis_id, model_id, proba, created_at)"
                 " VALUES (?,?,?, ?,?)", (bid, None, out["model_id"], out["default_probability"], now()))
    conn.commit()
    return out


class BatchIn(BaseModel):
    borrower_ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/ml/credit/predict")
def predict_single(body: dict, authorization: str | None = Header(default=None),
                   x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "analysis.read")
    bid = (body.get("borrower_id") or "").strip()
    if not bid:
        raise HTTPException(400, "borrower_id is required")
    conn = _DB()
    try:
        return _score_and_log(conn, bid, _actor(authorization, x_api_key))
    finally:
        conn.close()


@router.post("/ml/credit/predict-batch")
def predict_batch(body: BatchIn, authorization: str | None = Header(default=None),
                  x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "analysis.run")
    actor = _actor(authorization, x_api_key)
    conn = _DB()
    try:
        out, errors = [], {}
        for bid in dict.fromkeys(b.strip() for b in body.borrower_ids if b and b.strip()):
            try:
                out.append(_score_and_log(conn, bid, actor))
            except HTTPException as e:
                errors[bid] = e.detail
        return {"results": out, "errors": errors, "model_id": out[0]["model_id"] if out else None}
    finally:
        conn.close()


@router.get("/ml/credit/model")
def model_info(authorization: str | None = Header(default=None),
               x_api_key: str | None = Header(default=None)):
    _need(authorization, x_api_key, "analysis.read")
    serve = _engine()
    m = serve.metadata()
    return {
        "model_id": m["model_id"],
        "trained_at": m["trained_at"],
        "selected": m["selected"],
        "selection_criterion": m["selection_criterion"],
        "threshold_rule": m["threshold_rule"],
        "data_source": m["data_source"],
        "splits": m["splits"],
        "candidates_select_real": m["candidates_select_real"],
        "test_real_metrics": m["test_real_metrics"],
        "test_real_bands": m["test_real_bands"],
        "bands": m["bands"],
        "calibration": m["calibration"],
        "feature_notes": m["feature_notes"],
    }


@router.get("/ml/credit/public")
def model_public():
    """Public model facts for the landing page — aggregate metrics only,
    no borrower data. Same numbers as /model, no login needed."""
    serve = _engine()
    m = serve.metadata()
    tm = m["test_real_metrics"]
    train_rows = m["data_source"]["real_rows"] + m["data_source"]["synthetic_rows"]
    return {
        "model_id": m["model_id"],
        "n_features": serve.feature_count(),
        "train_rows": train_rows,
        "test_rows": tm["n"],
        "roc_auc": round(tm["roc_auc"], 2),
        "pr_auc": round(tm["pr_auc"], 2),
        "trained_at": m["trained_at"][:10],
    }
