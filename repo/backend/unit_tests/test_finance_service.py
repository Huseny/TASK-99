"""Unit tests for app.services.finance_service.

Pure service-layer tests – no HTTP, in-memory SQLite.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.security import hash_password
from app.models.finance import EntryType, LedgerEntry
from app.models.user import User, UserRole
from app.services import finance_service


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _student(db, username="stu1"):
    u = User(username=username, password_hash=hash_password("Pass@1234567"), role=UserRole.student, is_active=True)
    db.add(u)
    db.flush()
    return u


TODAY = date(2026, 4, 17)


# ---------------------------------------------------------------------------
# ensure_account
# ---------------------------------------------------------------------------

class TestEnsureAccount:
    def test_creates_account_on_first_call(self):
        db = _make_db()
        stu = _student(db)
        acc = finance_service.ensure_account(db, stu.id)
        assert acc.id is not None
        assert acc.student_id == stu.id

    def test_returns_same_account_on_repeat_calls(self):
        db = _make_db()
        stu = _student(db)
        acc1 = finance_service.ensure_account(db, stu.id)
        acc2 = finance_service.ensure_account(db, stu.id)
        assert acc1.id == acc2.id


# ---------------------------------------------------------------------------
# record_payment
# ---------------------------------------------------------------------------

class TestRecordPayment:
    def test_records_negative_amount(self):
        db = _make_db()
        stu = _student(db)
        entry = finance_service.record_payment(db, stu.id, 100.0, "BANK_TRANSFER", "REF001", "Fee", TODAY)
        assert entry.amount == -100.0
        assert entry.entry_type == EntryType.payment

    def test_invalid_instrument_raises(self):
        db = _make_db()
        stu = _student(db)
        with pytest.raises(HTTPException) as exc:
            finance_service.record_payment(db, stu.id, 50.0, "INVALID_INST", None, None, TODAY)
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# record_refund
# ---------------------------------------------------------------------------

class TestRecordRefund:
    def test_valid_refund(self):
        db = _make_db()
        stu = _student(db)
        payment = finance_service.record_payment(db, stu.id, 200.0, "BANK_TRANSFER", "REF002", None, TODAY)
        db.commit()
        refund = finance_service.record_refund(db, stu.id, 50.0, payment.id, "Partial refund", TODAY)
        assert refund.amount == 50.0
        assert refund.entry_type == EntryType.refund
        assert refund.reference_entry_id == payment.id

    def test_refund_exceeds_original_raises(self):
        db = _make_db()
        stu = _student(db)
        payment = finance_service.record_payment(db, stu.id, 100.0, "BANK_TRANSFER", "REF003", None, TODAY)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            finance_service.record_refund(db, stu.id, 200.0, payment.id, None, TODAY)
        assert exc.value.status_code == 422

    def test_refund_with_unknown_reference_raises(self):
        db = _make_db()
        stu = _student(db)
        with pytest.raises(HTTPException) as exc:
            finance_service.record_refund(db, stu.id, 10.0, 9999, None, TODAY)
        assert exc.value.status_code == 404

    def test_refund_non_payment_entry_raises(self):
        db = _make_db()
        stu = _student(db)
        charge = finance_service.record_month_end_billing(db, stu.id, 100.0, "Billing", TODAY)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            finance_service.record_refund(db, stu.id, 10.0, charge.id, None, TODAY)
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# record_month_end_billing
# ---------------------------------------------------------------------------

class TestRecordMonthEndBilling:
    def test_records_positive_charge(self):
        db = _make_db()
        stu = _student(db)
        entry = finance_service.record_month_end_billing(db, stu.id, 75.0, None, TODAY)
        assert entry.amount == 75.0
        assert entry.entry_type == EntryType.charge

    def test_default_description(self):
        db = _make_db()
        stu = _student(db)
        entry = finance_service.record_month_end_billing(db, stu.id, 50.0, None, TODAY)
        assert entry.description == "Month-end billing"

    def test_custom_description(self):
        db = _make_db()
        stu = _student(db)
        entry = finance_service.record_month_end_billing(db, stu.id, 50.0, "Custom desc", TODAY)
        assert entry.description == "Custom desc"


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------

class TestGetBalance:
    def test_zero_balance_for_new_student(self):
        db = _make_db()
        stu = _student(db)
        assert finance_service.get_balance(db, stu.id) == 0.0

    def test_balance_after_charge_and_payment(self):
        db = _make_db()
        stu = _student(db)
        finance_service.record_month_end_billing(db, stu.id, 300.0, None, TODAY)
        finance_service.record_payment(db, stu.id, 100.0, "BANK_TRANSFER", None, None, TODAY)
        db.commit()
        balance = finance_service.get_balance(db, stu.id)
        assert balance == 200.0


# ---------------------------------------------------------------------------
# import_reconciliation_csv
# ---------------------------------------------------------------------------

class TestImportReconciliationCsv:
    def _make_admin(self, db):
        u = User(username="admin_recon", password_hash=hash_password("Pass@1234567"), role=UserRole.admin, is_active=True)
        db.add(u)
        db.flush()
        return u

    def test_valid_csv_creates_report(self):
        db = _make_db()
        stu = _student(db, "recon_stu")
        admin = self._make_admin(db)
        payment = finance_service.record_payment(db, stu.id, 500.0, "BANK_TRANSFER", "REF-CSV-01", None, TODAY)
        db.commit()

        csv_text = (
            "student_id,amount,statement_date,reference_id,payment_method\n"
            f"{stu.id},500.0,2026-04-17,REF-CSV-01,BANK_TRANSFER\n"
        )
        report = finance_service.import_reconciliation_csv(db, csv_text, actor=admin)
        assert report.import_id is not None
        assert report.matched_total == 500.0
        assert report.statement_total == 500.0

    def test_missing_columns_raises(self):
        db = _make_db()
        admin = self._make_admin(db)
        with pytest.raises(HTTPException) as exc:
            finance_service.import_reconciliation_csv(db, "student_id,amount\n1,100\n", actor=admin)
        assert exc.value.status_code == 422
