from datetime import date, datetime

from pydantic import BaseModel, Field


class PaymentIn(BaseModel):
    student_id: int
    amount: float = Field(gt=0)
    instrument: str
    reference_id: str | None = Field(default=None, max_length=120)
    description: str | None = None
    entry_date: date


class RefundIn(BaseModel):
    student_id: int
    amount: float = Field(gt=0)
    reference_entry_id: int
    description: str | None = None
    entry_date: date


class PrepaymentIn(BaseModel):
    student_id: int
    amount: float = Field(gt=0)
    instrument: str
    reference_id: str | None = Field(default=None, max_length=120)
    description: str | None = None
    entry_date: date


class DepositIn(BaseModel):
    student_id: int
    amount: float = Field(gt=0)
    instrument: str
    reference_id: str | None = Field(default=None, max_length=120)
    description: str | None = None
    entry_date: date


class MonthEndBillingIn(BaseModel):
    student_id: int
    amount: float = Field(gt=0)
    description: str | None = None
    entry_date: date


class LedgerEntryOut(BaseModel):
    id: int
    entry_type: str
    amount: float
    instrument: str | None
    external_reference_id: str | None
    reference_entry_id: int | None
    description: str | None
    entry_date: date
    created_at: datetime


class AccountSummaryOut(BaseModel):
    student_id: int
    balance: float
    entries: list[LedgerEntryOut]


class ArrearsItem(BaseModel):
    student_id: int
    balance: float
    overdue_days: int


class ReconciliationLineOut(BaseModel):
    line_number: int
    student_id: int | None
    amount: float
    reference_id: str | None
    payment_method: str | None
    statement_date: date
    matched: bool
    matched_entry_id: int | None
    explanation: str | None


class ReconciliationImportOut(BaseModel):
    import_id: str
    matched_total: float
    unmatched_total: float
    statement_total: float = 0
    ledger_total: float = 0
    variance_total: float = 0
    lines: list[ReconciliationLineOut] = Field(default_factory=list)
