from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.access import ScopeGrant, ScopeType
from app.models.admin import AuditLog
from app.models.data_quality import QuarantineEntry
from app.models.finance import LedgerEntry
from app.models.user import User, UserRole


def _create_user(db: Session, username: str, role: UserRole, password: str, org_id: int | None = None) -> User:
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True, org_id=org_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _grant_org_scope(db: Session, user_id: int, org_id: int) -> None:
    db.add(ScopeGrant(user_id=user_id, scope_type=ScopeType.organization, scope_id=org_id))
    db.commit()


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_payment_refund_arrears_reconciliation(client, db_session: Session) -> None:
    org_id = 101
    finance = _create_user(db_session, "finance1", UserRole.finance_clerk, "FinancePass1!", org_id=org_id)
    student = _create_user(db_session, "finance_student", UserRole.student, "StudentPass1!", org_id=org_id)
    _grant_org_scope(db_session, finance.id, org_id)
    headers = _login(client, "finance1", "FinancePass1!")

    prepayment = client.post(
        "/api/v1/finance/prepayments",
        json={
            "student_id": student.id,
            "amount": 300.0,
            "instrument": "CASH",
            "reference_id": "prepay-1",
            "description": "Prepayment",
            "entry_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert prepayment.status_code == 200

    deposit = client.post(
        "/api/v1/finance/deposits",
        json={
            "student_id": student.id,
            "amount": 100.0,
            "instrument": "CHECK",
            "reference_id": "deposit-1",
            "description": "Lab deposit",
            "entry_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert deposit.status_code == 200

    payment = client.post(
        "/api/v1/finance/payments",
        json={
            "student_id": student.id,
            "amount": 200.0,
            "instrument": "CASH",
            "reference_id": "payment-1",
            "description": "Prepayment",
            "entry_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert payment.status_code == 200
    payment_id = payment.json()["id"]
    assert db_session.query(LedgerEntry).filter(LedgerEntry.id == payment_id).first() is not None
    payment_audit = db_session.query(AuditLog).filter(AuditLog.action == "finance.payment.record", AuditLog.entity_id == payment_id).first()
    assert payment_audit is not None

    refund = client.post(
        "/api/v1/finance/refunds",
        json={
            "student_id": student.id,
            "amount": 50.0,
            "reference_entry_id": payment_id,
            "description": "Partial refund",
            "entry_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert refund.status_code == 200

    over_refund = client.post(
        "/api/v1/finance/refunds",
        json={
            "student_id": student.id,
            "amount": 300.0,
            "reference_entry_id": payment_id,
            "description": "Too much",
            "entry_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert over_refund.status_code == 422

    account = client.get(f"/api/v1/finance/accounts/{student.id}", headers=headers)
    assert account.status_code == 200
    assert len(account.json()["entries"]) >= 4

    month_end = client.post(
        "/api/v1/finance/month-end-billing",
        json={
            "student_id": student.id,
            "amount": 900.0,
            "description": "Month-end tuition",
            "entry_date": (date.today() - timedelta(days=20)).isoformat(),
        },
        headers=headers,
    )
    assert month_end.status_code == 200

    arrears = client.get("/api/v1/finance/arrears", headers=headers)
    assert arrears.status_code == 200
    assert any(item["student_id"] == student.id for item in arrears.json())

    csv_content = (
        "student_id,amount,statement_date,reference_id,payment_method\n"
        f"{student.id},200.00,{date.today().isoformat()},payment-1,CASH\n"
        f"{student.id},999.00,{date.today().isoformat()},missing-1,CASH\n"
    )
    import_response = client.post(
        "/api/v1/finance/reconciliation/import",
        headers=headers,
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )
    assert import_response.status_code == 200
    import_id = import_response.json()["import_id"]

    report = client.get(f"/api/v1/finance/reconciliation/{import_id}/report", headers=headers)
    assert report.status_code == 200
    assert report.json()["matched_total"] >= 200.0
    assert report.json()["statement_total"] >= 1199.0
    assert report.json()["variance_total"] >= 999.0
    assert any(line["matched"] is False for line in report.json()["lines"])

    scoped_denied_user = _create_user(db_session, "other_finance_student", UserRole.student, "StudentPass1!", org_id=999)
    denied = client.get(f"/api/v1/finance/accounts/{scoped_denied_user.id}", headers=headers)
    assert denied.status_code == 403


def test_finance_rbac_denied_for_student(client, db_session: Session) -> None:
    _create_user(db_session, "student_no_fin", UserRole.student, "StudentPass1!")
    headers = _login(client, "student_no_fin", "StudentPass1!")

    response = client.get("/api/v1/finance/arrears", headers=headers)
    assert response.status_code == 403


def test_finance_payment_rejected_by_data_quality(client, db_session: Session) -> None:
    org_id = 202
    finance = _create_user(db_session, "finance_dq", UserRole.finance_clerk, "FinancePass1!", org_id=org_id)
    student = _create_user(db_session, "finance_dq_student", UserRole.student, "StudentPass1!", org_id=org_id)
    _grant_org_scope(db_session, finance.id, org_id)
    headers = _login(client, "finance_dq", "FinancePass1!")

    response = client.post(
        "/api/v1/finance/payments",
        json={
            "student_id": student.id,
            "amount": 250000.0,
            "instrument": "CASH",
            "reference_id": "outlier-1",
            "description": "Outlier amount",
            "entry_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["accepted"] is False
    quarantine_id = response.json()["detail"]["quarantine_id"]
    assert quarantine_id is not None

    row = db_session.query(QuarantineEntry).filter(QuarantineEntry.id == quarantine_id).first()
    assert row is not None
    assert row.entity_type == "FinancePaymentWrite"


def test_reconciliation_report_scope_isolation(client, db_session: Session) -> None:
    scoped_finance = _create_user(db_session, "finance_scope", UserRole.finance_clerk, "FinancePass1!", org_id=301)
    other_student = _create_user(db_session, "finance_scope_student_other", UserRole.student, "StudentPass1!", org_id=302)
    admin = _create_user(db_session, "finance_scope_admin", UserRole.admin, "AdminPass1!")
    _grant_org_scope(db_session, scoped_finance.id, 301)

    finance_headers = _login(client, "finance_scope", "FinancePass1!")
    admin_headers = _login(client, "finance_scope_admin", "AdminPass1!")

    csv_content = f"student_id,amount,statement_date,reference_id,payment_method\n{other_student.id},125.00,{date.today().isoformat()},scope-1,CASH\n"
    import_response = client.post(
        "/api/v1/finance/reconciliation/import",
        headers=admin_headers,
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )
    assert import_response.status_code == 200

    denied = client.get(
        f"/api/v1/finance/reconciliation/{import_response.json()['import_id']}/report",
        headers=finance_headers,
    )
    assert denied.status_code == 403


def test_reconciliation_prevents_false_positive_on_amount_only_match(client, db_session: Session) -> None:
    org_id = 401
    finance = _create_user(db_session, "finance_false_positive", UserRole.finance_clerk, "FinancePass1!", org_id=org_id)
    student = _create_user(db_session, "finance_student_false_positive", UserRole.student, "StudentPass1!", org_id=org_id)
    _grant_org_scope(db_session, finance.id, org_id)
    headers = _login(client, "finance_false_positive", "FinancePass1!")

    payment = client.post(
        "/api/v1/finance/payments",
        json={
            "student_id": student.id,
            "amount": 200.0,
            "instrument": "CASH",
            "reference_id": "ledger-match-1",
            "description": "Reference payment",
            "entry_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert payment.status_code == 200

    csv_content = (
        "student_id,amount,statement_date,reference_id,payment_method\n"
        f"{student.id},200.00,{date.today().isoformat()},different-ref,CASH\n"
    )
    import_response = client.post(
        "/api/v1/finance/reconciliation/import",
        headers=headers,
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )
    assert import_response.status_code == 200

    report = client.get(f"/api/v1/finance/reconciliation/{import_response.json()['import_id']}/report", headers=headers)
    assert report.status_code == 200
    assert report.json()["matched_total"] == 0
    assert report.json()["lines"][0]["matched"] is False
