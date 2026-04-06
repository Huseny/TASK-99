from datetime import date, datetime, timezone
import csv
import io
import uuid

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.authz import require_scope_access
from app.core.config import settings
from app.models.finance import BankStatementLine, EntryType, LedgerAccount, LedgerEntry, PaymentInstrument, ReconciliationReport
from app.models.user import User, UserRole


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_account(db: Session, student_id: int) -> LedgerAccount:
    account = db.query(LedgerAccount).filter(LedgerAccount.student_id == student_id).first()
    if account is None:
        account = LedgerAccount(student_id=student_id)
        db.add(account)
        db.flush()
    return account


def get_balance(db: Session, student_id: int) -> float:
    total = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0.0)).filter(LedgerEntry.student_id == student_id).scalar()
    return round(float(total or 0.0), 2)


def _parse_instrument(instrument: str) -> PaymentInstrument:
    try:
        return PaymentInstrument(instrument)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid payment instrument.") from exc


def _record_credit_entry(
    db: Session,
    student_id: int,
    amount: float,
    instrument: PaymentInstrument,
    reference_id: str | None,
    description: str | None,
    entry_date: date,
) -> LedgerEntry:
    account = ensure_account(db, student_id)
    entry = LedgerEntry(
        account_id=account.id,
        student_id=student_id,
        entry_type=EntryType.payment,
        amount=-abs(amount),
        instrument=instrument,
        external_reference_id=reference_id,
        description=description,
        entry_date=entry_date,
    )
    db.add(entry)
    db.flush()
    db.refresh(entry)
    return entry


def record_payment(
    db: Session,
    student_id: int,
    amount: float,
    instrument: str,
    reference_id: str | None,
    description: str | None,
    entry_date: date,
) -> LedgerEntry:
    payment_instrument = _parse_instrument(instrument)
    return _record_credit_entry(db, student_id, amount, payment_instrument, reference_id, description, entry_date)


def record_prepayment(
    db: Session,
    student_id: int,
    amount: float,
    instrument: str,
    reference_id: str | None,
    description: str | None,
    entry_date: date,
) -> LedgerEntry:
    payment_instrument = _parse_instrument(instrument)
    note = description or "Prepayment"
    return _record_credit_entry(db, student_id, amount, payment_instrument, reference_id, note, entry_date)


def record_deposit(
    db: Session,
    student_id: int,
    amount: float,
    instrument: str,
    reference_id: str | None,
    description: str | None,
    entry_date: date,
) -> LedgerEntry:
    payment_instrument = _parse_instrument(instrument)
    note = description or "Deposit"
    return _record_credit_entry(db, student_id, amount, payment_instrument, reference_id, note, entry_date)


def record_refund(
    db: Session,
    student_id: int,
    amount: float,
    reference_entry_id: int,
    description: str | None,
    entry_date: date,
) -> LedgerEntry:
    reference = db.query(LedgerEntry).filter(LedgerEntry.id == reference_entry_id, LedgerEntry.student_id == student_id).first()
    if reference is None:
        raise HTTPException(status_code=404, detail="Reference ledger entry not found.")
    if reference.entry_type != EntryType.payment:
        raise HTTPException(status_code=422, detail="Refund reference must be a payment entry.")
    if amount > abs(reference.amount):
        raise HTTPException(status_code=422, detail="Refund amount cannot exceed original payment amount.")

    account = ensure_account(db, student_id)
    entry = LedgerEntry(
        account_id=account.id,
        student_id=student_id,
        entry_type=EntryType.refund,
        amount=abs(amount),
        instrument=reference.instrument,
        reference_entry_id=reference_entry_id,
        description=description,
        entry_date=entry_date,
    )
    db.add(entry)
    db.flush()
    db.refresh(entry)
    return entry


def record_month_end_billing(
    db: Session,
    student_id: int,
    amount: float,
    description: str | None,
    entry_date: date,
) -> LedgerEntry:
    account = ensure_account(db, student_id)
    entry = LedgerEntry(
        account_id=account.id,
        student_id=student_id,
        entry_type=EntryType.charge,
        amount=abs(amount),
        instrument=None,
        description=description or "Month-end billing",
        entry_date=entry_date,
    )
    db.add(entry)
    db.flush()
    db.refresh(entry)
    return entry


def get_account_summary(db: Session, student_id: int) -> tuple[float, list[LedgerEntry]]:
    ensure_account(db, student_id)
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.student_id == student_id)
        .order_by(LedgerEntry.entry_date.desc(), LedgerEntry.id.desc())
        .all()
    )
    return get_balance(db, student_id), entries


def arrears_with_late_fee(db: Session) -> tuple[list[dict], int]:
    now = _utcnow().date()
    students = db.query(LedgerEntry.student_id).distinct().all()
    result: list[dict] = []
    generated_late_fees = 0
    for (student_id,) in students:
        balance = get_balance(db, student_id)
        if balance <= 0:
            continue
        latest_charge = (
            db.query(LedgerEntry)
            .filter(LedgerEntry.student_id == student_id, LedgerEntry.entry_type.in_([EntryType.charge, EntryType.late_fee]))
            .order_by(LedgerEntry.entry_date.desc())
            .first()
        )
        if latest_charge is None:
            overdue_days = 0
        else:
            overdue_days = (now - latest_charge.entry_date).days

        if overdue_days > settings.grace_period_days:
            month_start = now.replace(day=1)
            if month_start.month == 12:
                next_month_start = month_start.replace(year=month_start.year + 1, month=1, day=1)
            else:
                next_month_start = month_start.replace(month=month_start.month + 1, day=1)
            existing_late_fee = (
                db.query(LedgerEntry)
                .filter(
                    LedgerEntry.student_id == student_id,
                    LedgerEntry.entry_type == EntryType.late_fee,
                    LedgerEntry.entry_date >= month_start,
                    LedgerEntry.entry_date < next_month_start,
                )
                .first()
            )
            if existing_late_fee is None:
                account = ensure_account(db, student_id)
                fee_amount = round(balance * settings.late_fee_rate, 2)
                db.add(
                    LedgerEntry(
                        account_id=account.id,
                        student_id=student_id,
                        entry_type=EntryType.late_fee,
                        amount=fee_amount,
                        description="Monthly late fee",
                        entry_date=now,
                    )
                )
                db.flush()
                balance = get_balance(db, student_id)
                generated_late_fees += 1

        result.append({"student_id": student_id, "balance": round(balance, 2), "overdue_days": max(0, overdue_days)})
    return result, generated_late_fees


def import_reconciliation_csv(db: Session, csv_text: str, *, actor: User) -> ReconciliationReport:
    import_id = uuid.uuid4().hex
    reader = csv.DictReader(io.StringIO(csv_text))
    required_columns = {"student_id", "amount", "statement_date", "reference_id", "payment_method"}
    if not reader.fieldnames or not required_columns.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=422, detail="CSV must contain student_id, amount, statement_date, reference_id, payment_method columns.")

    matched_total = 0.0
    unmatched_total = 0.0
    statement_total = 0.0
    ledger_total = 0.0

    for idx, row in enumerate(reader, start=1):
        student_id = int(row["student_id"]) if row.get("student_id") else None
        if student_id is None and actor.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Non-admin reconciliation imports require student_id on every row.")
        if student_id is not None:
            require_scope_access(
                db,
                actor,
                type("StudentResource", (), {"student_id": student_id})(),
                detail="Access denied for one or more reconciliation rows.",
            )
        amount = float(row["amount"])
        statement_total += abs(amount)
        statement_date = datetime.strptime(row["statement_date"], "%Y-%m-%d").date()
        reference_id = row.get("reference_id") or None
        payment_method = row.get("payment_method") or None
        matched_entry = None
        explanation = "No matching ledger entry found."
        if student_id is not None:
            if payment_method is None or reference_id is None:
                raise HTTPException(status_code=422, detail="Every reconciliation row must include reference_id and payment_method.")
            instrument = _parse_instrument(payment_method)
            matched_entry = (
                db.query(LedgerEntry)
                .filter(
                    LedgerEntry.student_id == student_id,
                    func.abs(LedgerEntry.amount) == abs(amount),
                    LedgerEntry.external_reference_id == reference_id,
                    LedgerEntry.entry_date == statement_date,
                    LedgerEntry.instrument == instrument,
                )
                .first()
            )
            if matched_entry is not None:
                explanation = "Matched on student_id, reference_id, transaction_date, payment_method, and amount."
                ledger_total += abs(matched_entry.amount)
            else:
                explanation = "No ledger entry matched the full reconciliation key."

        matched = matched_entry is not None
        if matched:
            matched_total += abs(amount)
        else:
            unmatched_total += abs(amount)

        db.add(
            BankStatementLine(
                import_id=import_id,
                line_number=idx,
                student_id=student_id,
                amount=amount,
                reference_id=reference_id,
                payment_method=payment_method,
                statement_date=statement_date,
                raw_line=str(row),
                matched=matched,
                matched_entry_id=matched_entry.id if matched_entry is not None else None,
                explanation=explanation,
            )
        )

    report = ReconciliationReport(
        import_id=import_id,
        matched_total=round(matched_total, 2),
        unmatched_total=round(unmatched_total, 2),
        statement_total=round(statement_total, 2),
        ledger_total=round(ledger_total, 2),
        variance_total=round(statement_total - ledger_total, 2),
    )
    db.add(report)
    db.flush()
    db.refresh(report)
    return report


def get_reconciliation_report(db: Session, import_id: str, *, actor: User) -> ReconciliationReport:
    report = db.query(ReconciliationReport).filter(ReconciliationReport.import_id == import_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="Reconciliation report not found.")
    if actor.role != UserRole.admin:
        unresolved_rows = (
            db.query(BankStatementLine.id)
            .filter(BankStatementLine.import_id == import_id, BankStatementLine.student_id.is_(None))
            .first()
        )
        if unresolved_rows is not None:
            raise HTTPException(status_code=403, detail="Access denied for requested reconciliation report.")
        require_scope_access(
            db,
            actor,
            report,
            detail="Access denied for requested reconciliation report.",
        )
    return report


def get_reconciliation_lines(db: Session, import_id: str) -> list[BankStatementLine]:
    return db.query(BankStatementLine).filter(BankStatementLine.import_id == import_id).order_by(BankStatementLine.line_number.asc()).all()
