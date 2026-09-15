"""Vercel serverless entrypoint: exposes the LendSure FastAPI app.

Vercel imports this module and serves the ``app`` object. The backend lives
in ``backend/`` (``lendsure`` + ``ml_credit`` packages, seed DB, ML models),
so it is put on ``sys.path`` first. No code changes to the app itself.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import app  # noqa: E402,F401  (Vercel looks for `app`)
