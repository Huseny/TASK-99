from datetime import datetime, date
import enum

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EntryType(str, enum.Enum):
    charge = "CHARGE"
    payment = "PAYMENT"
    refund = "REFUND"
    late_fee = "LATE_FEE"


class PaymentInstrument(str, enum.Enum):
    cash = "CASH"
    check = "CHECK"
    internal_transfer = "INTERNAL_TRANSFER"


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("ledger_accounts.id"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    entry_type: Mapped[EntryType] = mapped_column(Enum(EntryType), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    instrument: Mapped[PaymentInstrument] = mapped_column(Enum(PaymentInstrument), nullable=True)
    external_reference_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    reference_entry_id: Mapped[int] = mapped_column(ForeignKey("ledger_entries.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    __table_args__ = (UniqueConstraint("import_id", "line_number", name="uq_statement_import_line"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matched_entry_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_entries.id"), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReconciliationReport(Base):
    __tablename__ = "reconciliation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    matched_total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    unmatched_total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    statement_total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    ledger_total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    variance_total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
