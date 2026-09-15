"""Load + clean the real UCI credit-default dataset."""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

import pandas as pd

UCI_URL = ("https://archive.ics.uci.edu/static/public/350/"
           "default+of+credit+card+clients.zip")
XLS_NAME = "default of credit card clients.xls"

PAY_COLS = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
BILL_COLS = [f"BILL_AMT{i}" for i in range(1, 7)]
PAYAMT_COLS = [f"PAY_AMT{i}" for i in range(1, 7)]
LABEL = "default payment next month"


def fetch_uci(data_dir: Path) -> Path:
    """Download the UCI zip (idempotent). Returns path to extracted .xls."""
    data_dir.mkdir(parents=True, exist_ok=True)
    zip_path = data_dir / "uci_default.zip"
    xls_path = data_dir / XLS_NAME
    if not xls_path.exists():
        if not zip_path.exists():
            print(f"[data] downloading {UCI_URL}", flush=True)
            urllib.request.urlretrieve(UCI_URL, zip_path)
        import zipfile
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(data_dir)
    return xls_path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_real(data_dir: Path) -> pd.DataFrame:
    """Cleaned real frame. Documented fixes only — no silent surgery."""
    xls = fetch_uci(data_dir)
    df = pd.read_excel(xls, header=1)
    df = df.drop(columns=["ID"])
    df = df.rename(columns={LABEL: "default"})
    # Documented UCI quirks: education {0,5,6} and marriage {0} are
    # uncoded/unknown levels. Collapse to level 4 (others) / 3 (others).
    df["EDUCATION"] = df["EDUCATION"].where(df["EDUCATION"].isin([1, 2, 3, 4]), 4)
    df["MARRIAGE"] = df["MARRIAGE"].where(df["MARRIAGE"].isin([1, 2, 3]), 3)
    # PAY_* == -2 means "no consumption that month" -> treat as on-time (-1).
    for c in PAY_COLS:
        df[c] = df[c].replace(-2, -1)
    df = df.dropna().reset_index(drop=True)
    assert df["default"].isin([0, 1]).all()
    return df
