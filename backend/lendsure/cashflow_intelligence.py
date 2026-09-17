from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import mean, pstdev
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .credit_bureau import ProviderUnavailable, demo_enabled


SOURCES = ("BANK-DERIVED", "DECLARED BY BORROWER", "DEMO/SANDBOX")
CATEGORIES = frozenset({"salary", "business", "cash_income", "other_income", "food", "housing",
                        "utilities", "transport", "health", "education", "business_expense",
                        "emi", "debt_payment", "insurance", "transfer", "loan_proceeds", "refund", "other"})
DEFAULT_TRANSFERS = frozenset({"transfer"})
MAX_RECORDS = 2000
MAX_CSV_BYTES = 1_000_000
Money = Annotated[float, Field(strict=True, allow_inf_nan=False, gt=0, le=1e12)]
Balance = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-1e12, le=1e12)]


class CashflowRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    direction: Literal["in", "out"]
    amount: Money
    category: str | None = None
    description: Annotated[str, StringConstraints(strict=True, max_length=240)] | None = None
    balance: Balance | None = None

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use YYYY-MM-DD")
        parsed = date.fromisoformat(value)
        if parsed.year < 2000 or parsed > datetime.now(timezone.utc).date():
            raise ValueError("Date must be between 2000-01-01 and today")
        return value

    @field_validator("category")
    @classmethod
    def valid_category(cls, value):
        if value is not None and value not in CATEGORIES:
            raise ValueError("Unknown category")
        return value


def normalized_record(data: dict) -> dict:
    record = CashflowRecord.model_validate(data).model_dump(exclude={"description"})
    record["category"] = record["category"] or "other"
    return record


def fingerprint(record: dict) -> str:
    return hashlib.sha256(json.dumps(normalized_record(record), sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def parse_statement(text: str) -> list[dict]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("Statement must not exceed 1MB")
    if "\x00" in text:
        raise ValueError("Invalid CSV")
    expected = ["date", "direction", "amount", "category", "description", "balance"]
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        if next(reader, None) != expected:
            raise ValueError("CSV columns must be date,direction,amount,category,description,balance")
        records = []
        for row in reader:
            if len(row) != len(expected) or len(records) >= MAX_RECORDS:
                raise ValueError("Invalid row or more than 2000 records")
            data = dict(zip(expected, row))
            if not re.fullmatch(r"\d+(?:\.\d{1,2})?", data["amount"]):
                raise ValueError("Amount must be a positive decimal with at most two decimal places")
            if data["balance"] and not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", data["balance"]):
                raise ValueError("Balance must be a decimal with at most two decimal places")
            data["amount"] = float(data["amount"])
            data["balance"] = float(data["balance"]) if data["balance"] else None
            data["category"] = data["category"] or None
            records.append(normalized_record(data))
        if not records:
            raise ValueError("Statement contains no records")
        return records
    except csv.Error as exc:
        raise ValueError("Malformed CSV") from exc


def transfer_categories(value=None) -> frozenset[str]:
    if value is None:
        return DEFAULT_TRANSFERS
    if not isinstance(value, (list, tuple, set, frozenset)) or any(not isinstance(v, str) for v in value):
        raise ValueError("Transfer categories must be a collection of category names")
    result = frozenset(value)
    if not result <= CATEGORIES:
        raise ValueError("Unknown transfer category")
    return result


def calendar_months(first: str, last: str) -> list[str]:
    year, month = map(int, first.split("-"))
    result = []
    while f"{year:04d}-{month:02d}" <= last:
        result.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def summarize(records: list[dict], source: str, fetched_at: str, transfers=None) -> dict:
    if source not in SOURCES:
        raise ValueError("Unknown cashflow provenance")
    excluded = transfer_categories(transfers)
    records = list({fingerprint(r): normalized_record(r) for r in records}.values())
    records.sort(key=lambda r: (r["date"], fingerprint(r)))
    buckets = defaultdict(list)
    for record in records:
        buckets[record["date"][:7]].append(record)
    months = []
    incomes, expenses = [], []
    income_categories, expense_categories = defaultdict(float), defaultdict(float)
    recurring = defaultdict(set)
    income_days = set()
    debt, emi = 0.0, 0.0
    for month, rows in sorted(buckets.items()):
        included = [r for r in rows if r["category"] not in excluded]
        inflow = sum(r["amount"] for r in included if r["direction"] == "in")
        outflow = sum(r["amount"] for r in included if r["direction"] == "out")
        income = 0.0
        for row in included:
            category, amount = row["category"], row["amount"]
            if row["direction"] == "in" and category not in {"loan_proceeds", "refund"}:
                income += amount
                income_categories[category] += amount
                income_days.add(row["date"])
            elif row["direction"] == "out":
                expense_categories[category] += amount
                recurring[category].add(month)
                if category in {"emi", "debt_payment"}:
                    debt += amount
                if category == "emi":
                    emi += amount
        last_date = max(r["date"] for r in rows)
        last_balances = {r["balance"] for r in rows if r["date"] == last_date}
        balance = next(iter(last_balances)) if len(last_balances) == 1 else None
        months.append({"month": month, "inflow": round(inflow, 2), "outflow": round(outflow, 2),
                       "net": round(inflow - outflow, 2), "balance": balance})
        incomes.append(income)
        expenses.append(outflow)
    observed = len(months)
    missing = [m for m in calendar_months(months[0]["month"], months[-1]["month"]) if m not in buckets] if months else []
    balances = [m["balance"] for m in months if m["balance"] is not None]
    all_balances = [r["balance"] for r in records if r["balance"] is not None]

    def volatility(values):
        return round(pstdev(values) / mean(values) * 100, 2) if len(values) >= 2 and mean(values) > 0 else None

    def largest(values):
        return sorted(values, key=lambda k: (-values[k], k))[0] if values else None

    income_volatility = volatility(incomes)
    total_income = sum(incomes)
    confidence = {
        "BANK-DERIVED": "Low: statement upload/unverified; not an authenticated bank feed",
        "DECLARED BY BORROWER": "Low: lender-entered borrower declaration; unverified and potentially incomplete",
        "DEMO/SANDBOX": "Fictional sandbox fixture; not evidence about a real borrower",
    }[source]
    return {
        "source": source, "fetched_at": fetched_at, "confidence": confidence, "months": months,
        "metrics": {
            "monthly_inflow": round(mean(m["inflow"] for m in months), 2) if observed else None,
            "monthly_outflow": round(mean(expenses), 2) if observed else None,
            "net_cash_flow": round(mean(m["net"] for m in months), 2) if observed else None,
            "average_monthly_balance": round(mean(balances), 2) if balances else None,
            "minimum_balance": min(all_balances) if all_balances else None,
            "income_consistency_pct": round(max(0, 100 - income_volatility), 2) if income_volatility is not None else None,
            "income_volatility_pct": income_volatility, "expense_volatility_pct": volatility(expenses),
            "debt_service_burden_pct": round(debt / total_income * 100, 2) if total_income else None,
            "emi_to_income_pct": round(emi / total_income * 100, 2) if total_income else None,
            "negative_months": sum(m["net"] < 0 for m in months), "income_days": len(income_days),
            "largest_income_source": largest(income_categories),
            "largest_expense_category": largest(expense_categories),
            "recurring_obligations": [{"category": c, "amount": round(expense_categories[c] / observed, 2),
                                       "months_observed": len(ms)} for c, ms in sorted(recurring.items()) if len(ms) >= 2],
        },
        "expense_categories": [{"category": c, "amount": round(v, 2)} for c, v in sorted(expense_categories.items())],
        "missing_months": missing, "record_count": len(records),
        "semantics": {
            "window": "Observed calendar months between first and last record; missing months excluded, not zero-filled",
            "flows": "Transfers excluded; loan proceeds and refunds included in inflow but excluded from income ratios",
            "transfer_categories": sorted(excluded),
            "volatility": "Population standard deviation / mean * 100 across observed months; null with fewer than two months or zero mean",
            "consistency": "max(0, 100 - income_volatility_pct)",
            "debt_ratios": "Observed outgoing emi plus debt_payment / observed income * 100; EMI ratio uses emi only; null for zero income",
            "balances": "Mean of known last-record-date monthly balances, not daily average; ambiguous same-day or absent balances are unknown; minimum is observed only",
            "recurring": "Categories with outgoing records in at least two months; amount is per observed month, not a contractual obligation",
            "income_days": "Count of distinct observed income dates; largest source means category, not payer identity",
            "deduplication": "Identical date/direction/amount/category/balance records collapse, even if descriptions differ",
        },
    }


def extract_features(credit: dict | None, summaries: list[dict]) -> dict:
    return {
        "credit": {k: credit.get(k) if credit else None for k in
                   ("score", "utilization_pct", "on_time_payment_pct", "overdue_amount", "history_months")},
        "cashflow_by_source": {s["source"]: {k: s["metrics"][k] for k in
                               ("monthly_inflow", "net_cash_flow", "income_volatility_pct", "debt_service_burden_pct")}
                               for s in summaries},
    }


class AccountDataProvider(ABC):
    name = "unavailable"
    status = "unavailable"

    @abstractmethod
    def fetch(self, borrower_id: str) -> list[dict]:
        raise NotImplementedError


class UnavailableAccountProvider(AccountDataProvider):
    def fetch(self, borrower_id: str) -> list[dict]:
        raise ProviderUnavailable("Authorized account-data provider is unavailable")


class SandboxAccountProvider(AccountDataProvider):
    name = "Fictional sandbox cashflow"
    status = "sandbox"

    def __init__(self, environment=None):
        self.environment = dict(os.environ if environment is None else environment)

    def fetch(self, borrower_id: str) -> list[dict]:
        if not demo_enabled(self.environment) or not borrower_id.startswith("DEMO-"):
            raise ProviderUnavailable("Sandbox requires a fictional DEMO- borrower")
        today = datetime.now(timezone.utc).date()
        index = today.year * 12 + today.month - 1
        records = []
        for offset in range(6, 0, -1):
            year, month = divmod(index - offset, 12)
            label = f"{year:04d}-{month + 1:02d}"
            records.extend([
                {"date": label + "-03", "direction": "in", "amount": 30000 + offset * 500, "category": "cash_income"},
                {"date": label + "-10", "direction": "out", "amount": 15000, "category": "business_expense"},
                {"date": label + "-20", "direction": "out", "amount": 3000, "category": "emi"},
            ])
        return [normalized_record(r) for r in records]


def account_provider() -> AccountDataProvider:
    return UnavailableAccountProvider()
