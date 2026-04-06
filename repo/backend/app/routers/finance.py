from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.auth import get_current_user
from app.core.authz import can_access_student, require_student_access
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User, UserRole
from app.schemas.finance import (
    AccountSummaryOut,
    ArrearsItem,
    DepositIn,
    LedgerEntryOut,
    MonthEndBillingIn,
    PaymentIn,
    PrepaymentIn,
    ReconciliationImportOut,
    ReconciliationLineOut,
    RefundIn,
)
from app.services import data_quality_service, finance_service

router = APIRouter(prefix="/finance", tags=["finance"])
logger = get_logger("app.finance")


def _ensure_finance_or_admin(user: User) -> None:
    if user.role not in {UserRole.finance_clerk, UserRole.admin}:
        raise HTTPException(status_code=403, detail="Finance clerk or admin access required.")


def _enforce_finance_write_quality(entity_type: str, payload: dict, db: Session) -> None:
    ranges = {"amount": {"min": 0.01, "max": 100000.0}}
    required_fields = ["student_id", "amount", "entry_date"]
    if entity_type == "FinanceRefundWrite":
        required_fields = [*required_fields, "reference_entry_id"]
    data_quality_service.enforce_write_quality(
        db,
        entity_type=entity_type,
        payload=payload,
        required_fields=required_fields,
        ranges=ranges,
        unique_keys=[],
    )


@router.get("/accounts/{student_id}", response_model=AccountSummaryOut)
def get_account(student_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    require_student_access(db, user, student_id)
    balance, entries = finance_service.get_account_summary(db, student_id)
    return AccountSummaryOut(
        student_id=student_id,
        balance=balance,
        entries=[
            LedgerEntryOut(
                id=e.id,
                entry_type=e.entry_type.value,
                amount=e.amount,
                instrument=e.instrument.value if e.instrument else None,
                external_reference_id=e.external_reference_id,
                reference_entry_id=e.reference_entry_id,
                description=e.description,
                entry_date=e.entry_date,
                created_at=e.created_at,
            )
            for e in entries
        ],
    )


@router.post("/payments", response_model=LedgerEntryOut)
def post_payment(payload: PaymentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    require_student_access(db, user, payload.student_id)
    _enforce_finance_write_quality("FinancePaymentWrite", payload.model_dump(), db)
    entry = finance_service.record_payment(
        db,
        student_id=payload.student_id,
        amount=payload.amount,
        instrument=payload.instrument,
        reference_id=payload.reference_id,
        description=payload.description,
        entry_date=payload.entry_date,
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="finance.payment.record",
        entity_name="LedgerEntry",
        entity_id=entry.id,
        before=None,
        after={"id": entry.id, "student_id": entry.student_id, "amount": entry.amount, "entry_type": entry.entry_type.value},
    )
    logger.info(
        "finance_payment_recorded",
        extra={"event": "finance.payment.recorded", "fields": {"entry_id": entry.id, "student_id": entry.student_id, "actor_id": user.id}},
    )
    db.commit()
    return LedgerEntryOut(
        id=entry.id,
        entry_type=entry.entry_type.value,
        amount=entry.amount,
        instrument=entry.instrument.value if entry.instrument else None,
        external_reference_id=entry.external_reference_id,
        reference_entry_id=entry.reference_entry_id,
        description=entry.description,
        entry_date=entry.entry_date,
        created_at=entry.created_at,
    )


@router.post("/prepayments", response_model=LedgerEntryOut)
def post_prepayment(payload: PrepaymentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    require_student_access(db, user, payload.student_id)
    _enforce_finance_write_quality("FinancePrepaymentWrite", payload.model_dump(), db)
    entry = finance_service.record_prepayment(
        db,
        student_id=payload.student_id,
        amount=payload.amount,
        instrument=payload.instrument,
        reference_id=payload.reference_id,
        description=payload.description,
        entry_date=payload.entry_date,
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="finance.prepayment.record",
        entity_name="LedgerEntry",
        entity_id=entry.id,
        before=None,
        after={"id": entry.id, "student_id": entry.student_id, "amount": entry.amount, "entry_type": entry.entry_type.value},
    )
    logger.info(
        "finance_prepayment_recorded",
        extra={"event": "finance.prepayment.recorded", "fields": {"entry_id": entry.id, "student_id": entry.student_id, "actor_id": user.id}},
    )
    db.commit()
    return LedgerEntryOut(
        id=entry.id,
        entry_type=entry.entry_type.value,
        amount=entry.amount,
        instrument=entry.instrument.value if entry.instrument else None,
        external_reference_id=entry.external_reference_id,
        reference_entry_id=entry.reference_entry_id,
        description=entry.description,
        entry_date=entry.entry_date,
        created_at=entry.created_at,
    )


@router.post("/deposits", response_model=LedgerEntryOut)
def post_deposit(payload: DepositIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    require_student_access(db, user, payload.student_id)
    _enforce_finance_write_quality("FinanceDepositWrite", payload.model_dump(), db)
    entry = finance_service.record_deposit(
        db,
        student_id=payload.student_id,
        amount=payload.amount,
        instrument=payload.instrument,
        reference_id=payload.reference_id,
        description=payload.description,
        entry_date=payload.entry_date,
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="finance.deposit.record",
        entity_name="LedgerEntry",
        entity_id=entry.id,
        before=None,
        after={"id": entry.id, "student_id": entry.student_id, "amount": entry.amount, "entry_type": entry.entry_type.value},
    )
    logger.info(
        "finance_deposit_recorded",
        extra={"event": "finance.deposit.recorded", "fields": {"entry_id": entry.id, "student_id": entry.student_id, "actor_id": user.id}},
    )
    db.commit()
    return LedgerEntryOut(
        id=entry.id,
        entry_type=entry.entry_type.value,
        amount=entry.amount,
        instrument=entry.instrument.value if entry.instrument else None,
        external_reference_id=entry.external_reference_id,
        reference_entry_id=entry.reference_entry_id,
        description=entry.description,
        entry_date=entry.entry_date,
        created_at=entry.created_at,
    )


@router.post("/refunds", response_model=LedgerEntryOut)
def post_refund(payload: RefundIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    require_student_access(db, user, payload.student_id)
    _enforce_finance_write_quality("FinanceRefundWrite", payload.model_dump(), db)
    entry = finance_service.record_refund(
        db,
        student_id=payload.student_id,
        amount=payload.amount,
        reference_entry_id=payload.reference_entry_id,
        description=payload.description,
        entry_date=payload.entry_date,
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="finance.refund.record",
        entity_name="LedgerEntry",
        entity_id=entry.id,
        before=None,
        after={"id": entry.id, "student_id": entry.student_id, "amount": entry.amount, "entry_type": entry.entry_type.value},
    )
    logger.info(
        "finance_refund_recorded",
        extra={"event": "finance.refund.recorded", "fields": {"entry_id": entry.id, "student_id": entry.student_id, "actor_id": user.id}},
    )
    db.commit()
    return LedgerEntryOut(
        id=entry.id,
        entry_type=entry.entry_type.value,
        amount=entry.amount,
        instrument=entry.instrument.value if entry.instrument else None,
        external_reference_id=entry.external_reference_id,
        reference_entry_id=entry.reference_entry_id,
        description=entry.description,
        entry_date=entry.entry_date,
        created_at=entry.created_at,
    )


@router.post("/month-end-billing", response_model=LedgerEntryOut)
def post_month_end_billing(payload: MonthEndBillingIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    require_student_access(db, user, payload.student_id)
    _enforce_finance_write_quality("FinanceMonthEndWrite", payload.model_dump(), db)
    entry = finance_service.record_month_end_billing(
        db,
        student_id=payload.student_id,
        amount=payload.amount,
        description=payload.description,
        entry_date=payload.entry_date,
    )
    write_audit_log(
        db,
        actor_id=user.id,
        action="finance.month_end_billing.record",
        entity_name="LedgerEntry",
        entity_id=entry.id,
        before=None,
        after={"id": entry.id, "student_id": entry.student_id, "amount": entry.amount, "entry_type": entry.entry_type.value},
    )
    logger.info(
        "finance_month_end_billing_recorded",
        extra={"event": "finance.month_end_billing.recorded", "fields": {"entry_id": entry.id, "student_id": entry.student_id, "actor_id": user.id}},
    )
    db.commit()
    return LedgerEntryOut(
        id=entry.id,
        entry_type=entry.entry_type.value,
        amount=entry.amount,
        instrument=entry.instrument.value if entry.instrument else None,
        external_reference_id=entry.external_reference_id,
        reference_entry_id=entry.reference_entry_id,
        description=entry.description,
        entry_date=entry.entry_date,
        created_at=entry.created_at,
    )


@router.get("/arrears", response_model=list[ArrearsItem])
def get_arrears(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    rows, generated_late_fees = finance_service.arrears_with_late_fee(db)
    if user.role != UserRole.admin:
        rows = [row for row in rows if can_access_student(db, user, row["student_id"])]
    if generated_late_fees > 0:
        write_audit_log(
            db,
            actor_id=user.id,
            action="finance.late_fee.generate",
            entity_name="LedgerEntry",
            entity_id=None,
            before=None,
            after={"generated_late_fees": generated_late_fees},
        )
        db.commit()
    return [ArrearsItem(**row) for row in rows]


@router.post("/reconciliation/import", response_model=ReconciliationImportOut)
async def import_reconciliation(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
): 
    _ensure_finance_or_admin(user)
    filename = str(file.filename or "")
    if not filename.lower().endswith(".csv"):
        logger.info("finance_reconciliation_invalid_file", extra={"event": "finance.reconciliation.invalid_file"})
        raise HTTPException(status_code=422, detail="Only CSV files are supported.")
    content = await file.read()
    report = finance_service.import_reconciliation_csv(db, content.decode("utf-8"), actor=user)
    write_audit_log(
        db,
        actor_id=user.id,
        action="finance.reconciliation.import",
        entity_name="ReconciliationReport",
        entity_id=report.id,
        before=None,
        after={"import_id": report.import_id, "matched_total": report.matched_total, "unmatched_total": report.unmatched_total},
    )
    logger.info(
        "finance_reconciliation_imported",
        extra={
            "event": "finance.reconciliation.imported",
            "fields": {"import_id": report.import_id, "actor_id": user.id, "matched_total": report.matched_total},
        },
    )
    db.commit()
    return ReconciliationImportOut(
        import_id=report.import_id,
        matched_total=report.matched_total,
        unmatched_total=report.unmatched_total,
        statement_total=report.statement_total,
        ledger_total=report.ledger_total,
        variance_total=report.variance_total,
    )


@router.get("/reconciliation/{import_id}/report", response_model=ReconciliationImportOut)
def get_reconciliation(import_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_finance_or_admin(user)
    report = finance_service.get_reconciliation_report(db, import_id, actor=user)
    lines = finance_service.get_reconciliation_lines(db, import_id)
    return ReconciliationImportOut(
        import_id=report.import_id,
        matched_total=report.matched_total,
        unmatched_total=report.unmatched_total,
        statement_total=report.statement_total,
        ledger_total=report.ledger_total,
        variance_total=report.variance_total,
        lines=[
            ReconciliationLineOut(
                line_number=line.line_number,
                student_id=line.student_id,
                amount=line.amount,
                reference_id=line.reference_id,
                payment_method=line.payment_method,
                statement_date=line.statement_date,
                matched=line.matched,
                matched_entry_id=line.matched_entry_id,
                explanation=line.explanation,
            )
            for line in lines
        ],
    )
