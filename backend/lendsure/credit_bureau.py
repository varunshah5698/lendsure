from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator


Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=240)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=1e12)]
Percent = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=100)]
Count = Annotated[StrictInt, Field(ge=0, le=10000)]


class ProviderUnavailable(Exception):
    pass


class NormalizedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreditAccount(NormalizedModel):
    type: Text | None = None
    status: Literal["active", "closed", "defaulted"] | None = None
    secured: bool | None = Field(default=None, strict=True)
    balance: Number | None = None
    credit_limit: Number | None = None
    overdue_amount: Number | None = None
    opened_at: date | None = None
    closed_at: date | None = None

    @model_validator(mode="after")
    def dates_valid(self):
        if self.opened_at and self.closed_at and self.closed_at < self.opened_at:
            raise ValueError("Account dates are inconsistent")
        return self


class Inquiry(NormalizedModel):
    date: date
    purpose: Text | None = None


class CreditEvent(NormalizedModel):
    date: date
    type: Text
    description: Text | None = None


class UtilizationPoint(NormalizedModel):
    date: date
    value: Percent


class CreditReport(NormalizedModel):
    source: Literal["DEMO/SANDBOX", "CREDIT BUREAU"]
    provider: Text
    reference_id: Text | None = None
    fetched_at: datetime
    report_date: date | None = None
    stale: bool = False
    score: Number | None = None
    score_min: Number | None = None
    score_max: Number | None = None
    history_months: Count | None = None
    active_accounts: Count | None = None
    closed_accounts: Count | None = None
    secured_loans: Count | None = None
    unsecured_loans: Count | None = None
    utilization_pct: Percent | None = None
    on_time_payment_pct: Percent | None = None
    overdue_amount: Number | None = None
    default_indicators: list[Text] | None = Field(default=None, max_length=500)
    accounts: list[CreditAccount] | None = Field(default=None, max_length=500)
    inquiries: list[Inquiry] | None = Field(default=None, max_length=500)
    events: list[CreditEvent] | None = Field(default=None, max_length=500)
    utilization_trend: list[UtilizationPoint] | None = Field(default=None, max_length=500)
    recent_changes: list[Text] | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_report(self):
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at requires a timezone")
        if self.fetched_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Future fetch timestamp")
        if self.report_date and self.report_date > self.fetched_at.date():
            raise ValueError("Future report date")
        if (self.score_min is None) != (self.score_max is None):
            raise ValueError("Both score bounds are required together")
        if self.score_min is not None and self.score_min >= self.score_max:
            raise ValueError("Invalid score range")
        if self.score is not None and (self.score_min is None or not self.score_min <= self.score <= self.score_max):
            raise ValueError("Score outside known bounds")
        for items in (self.inquiries, self.events, self.utilization_trend):
            if items and any(item.date > (self.report_date or self.fetched_at.date()) for item in items):
                raise ValueError("Future report event")
        for account in self.accounts or []:
            if any(d and d > (self.report_date or self.fetched_at.date())
                   for d in (account.opened_at, account.closed_at)):
                raise ValueError("Future account date")
        return self


def demo_enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return env.get("LENDSURE_INTELLIGENCE_DEMO") == "1" and env.get("LENDSURE_ENV", "").lower() in {"development", "test"}


def normalize_report(data: dict, today: date | None = None) -> dict:
    report = CreditReport.model_validate(data)
    today = today or datetime.now(timezone.utc).date()
    report.stale = report.report_date is None or (today - report.report_date).days > 30
    return report.model_dump(mode="json")


class CreditBureauProvider(ABC):
    name = "unavailable"
    status = "unavailable"

    @abstractmethod
    def fetch(self, borrower_id: str) -> dict:
        raise NotImplementedError


class UnavailableCreditProvider(CreditBureauProvider):
    def fetch(self, borrower_id: str) -> dict:
        raise ProviderUnavailable("Credit bureau collection is unavailable")


class TransUnionProvider(UnavailableCreditProvider):
    name = "TransUnion CIBIL"

    def fetch(self, borrower_id: str) -> dict:
        raise ProviderUnavailable("Authorized contract-specific TransUnion adapter is not configured")


class SandboxCreditProvider(CreditBureauProvider):
    name = "Fictional sandbox bureau"
    status = "sandbox"

    def __init__(self, environment=None):
        self.environment = dict(os.environ if environment is None else environment)

    def fetch(self, borrower_id: str) -> dict:
        if not demo_enabled(self.environment) or not borrower_id.startswith("DEMO-"):
            raise ProviderUnavailable("Sandbox requires a fictional DEMO- borrower")
        now = datetime.now(timezone.utc)
        return normalize_report({
            "source": "DEMO/SANDBOX", "provider": self.name,
            "reference_id": "FICTIONAL-REPORT-V1", "fetched_at": now.isoformat(),
            "report_date": now.date().isoformat(), "score": 710, "score_min": 300,
            "score_max": 900, "history_months": 24, "active_accounts": 2,
            "closed_accounts": 1, "secured_loans": 1, "unsecured_loans": 1,
            "utilization_pct": 32, "on_time_payment_pct": 95, "overdue_amount": 0,
            "default_indicators": [], "accounts": [
                {"type": "Fictional secured loan", "status": "active", "secured": True,
                 "balance": 48000, "overdue_amount": 0},
                {"type": "Fictional revolving credit", "status": "active", "secured": False,
                 "balance": 16000, "credit_limit": 50000, "overdue_amount": 0},
                {"type": "Fictional closed loan", "status": "closed", "balance": 0}],
            "inquiries": [{"date": (now.date() - timedelta(days=15)).isoformat(), "purpose": "Fictional loan inquiry"}],
            "events": [{"date": now.date().isoformat(), "type": "FICTIONAL_FIXTURE",
                        "description": "Entire report is fictional; not a production credit score"}],
            "utilization_trend": [{"date": now.date().isoformat(), "value": 32}],
            "recent_changes": ["Fictional sandbox fixture; no live bureau information"],
        })


def credit_provider(env=None) -> CreditBureauProvider:
    env = os.environ if env is None else env
    selected = env.get("LENDSURE_CIBIL_PROVIDER", "unavailable").strip().lower()
    if selected == "sandbox" and demo_enabled(env):
        return SandboxCreditProvider(env)
    if selected in {"transunion", "cibil"}:
        return TransUnionProvider()
    return UnavailableCreditProvider()
