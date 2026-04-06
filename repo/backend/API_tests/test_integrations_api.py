from datetime import datetime, timezone
import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.admin import AuditLog, Organization
from app.models.integration import IntegrationClient, IntegrationImport
from app.models.review import ScoringForm
from app.models.user import User, UserRole


def _create_user(db: Session, username: str, role: UserRole, password: str, org_id: int | None = None) -> User:
    user = User(username=username, password_hash=hash_password(password), role=role, is_active=True, org_id=org_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_org(db: Session, name: str, code: str) -> Organization:
    org = Organization(name=name, code=code, is_active=True)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _sign(secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _create_client(client, db_session: Session, *, username: str, org_id: int, name: str, rate_limit_rpm: int = 5) -> tuple[str, str]:
    _create_user(db_session, username, UserRole.admin, "AdminPass1!")
    admin_headers = _login(client, username, "AdminPass1!")
    create = client.post(
        "/api/v1/integrations/clients",
        json={"name": name, "organization_id": org_id, "rate_limit_rpm": rate_limit_rpm},
        headers=admin_headers,
    )
    assert create.status_code == 200
    return create.json()["client_id"], create.json()["client_secret"]


def _signed_headers(secret: str, client_id: str, path: str, body: bytes, nonce: str, timestamp: str | None = None) -> dict[str, str]:
    ts = timestamp or str(int(datetime.now(timezone.utc).timestamp()))
    return {
        "X-Client-ID": client_id,
        "X-Signature-256": _sign(secret, "POST", path, ts, nonce, body),
        "X-Nonce": nonce,
        "X-Timestamp": ts,
        "Content-Type": "application/json",
    }


def test_sis_sync_persists_users_and_is_idempotent(client, db_session: Session) -> None:
    org = _create_org(db_session, "Integration Org", "INTORG")
    client_id, secret = _create_client(client, db_session, username="int_admin", org_id=org.id, name="SIS Connector")

    path = "/api/v1/integrations/sis/students"
    payload = {
        "import_id": "sis-import-1",
        "students": [
            {"external_id": "S1", "username": "sis_student_1", "is_active": True},
            {"external_id": "S2", "username": "sis_student_2", "is_active": False},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    headers = _signed_headers(secret, client_id, path, body, "nonce-1")

    response = client.post(path, data=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["created"] == 2

    stored_users = db_session.query(User).filter(User.source_client_id == client_id).order_by(User.external_id.asc()).all()
    assert [row.external_id for row in stored_users] == ["S1", "S2"]
    assert all(row.org_id == org.id for row in stored_users)

    replay_headers = _signed_headers(secret, client_id, path, body, "nonce-2")
    replay = client.post(path, data=body, headers=replay_headers)
    assert replay.status_code == 200
    assert replay.json()["created"] == 2

    db_session.expire_all()
    assert db_session.query(User).filter(User.source_client_id == client_id).count() == 2
    import_rows = (
        db_session.query(IntegrationImport)
        .filter(IntegrationImport.client_id == client_id, IntegrationImport.import_type == "sis.students")
        .all()
    )
    assert len(import_rows) == 1

    sync_audit = db_session.query(AuditLog).filter(AuditLog.action == "integrations.sis.students.sync").all()
    assert len(sync_audit) == 2
    assert all(row.actor_id is not None for row in sync_audit)


def test_qbank_import_persists_forms_and_rejects_duplicate_import_id_mismatch(client, db_session: Session) -> None:
    org = _create_org(db_session, "QBank Org", "QBORG")
    client_id, secret = _create_client(client, db_session, username="int_admin_qb", org_id=org.id, name="QBank Connector")

    path = "/api/v1/integrations/qbank/forms"
    payload = {
        "import_id": "qbank-import-1",
        "forms": [{"external_id": "F1", "name": "Imported Form", "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]}],
    }
    body = json.dumps(payload).encode("utf-8")

    ok = client.post(path, data=body, headers=_signed_headers(secret, client_id, path, body, "qnonce-1"))
    assert ok.status_code == 200
    assert ok.json()["created"] == 1

    form = db_session.query(ScoringForm).filter(ScoringForm.source_client_id == client_id, ScoringForm.external_id == "F1").first()
    assert form is not None
    assert form.organization_id == org.id
    import_audit = db_session.query(AuditLog).filter(AuditLog.action == "integrations.qbank.forms.import").first()
    assert import_audit is not None
    assert import_audit.actor_id is not None

    different_payload = {
        "import_id": "qbank-import-1",
        "forms": [{"external_id": "F2", "name": "Other Form", "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]}],
    }
    different_body = json.dumps(different_payload).encode("utf-8")
    conflict = client.post(path, data=different_body, headers=_signed_headers(secret, client_id, path, different_body, "qnonce-2"))
    assert conflict.status_code == 409


def test_integration_invalid_payload_and_partial_failure_rolls_back(client, db_session: Session) -> None:
    org = _create_org(db_session, "Rollback Org", "RBORG")
    _create_user(db_session, "existing_student", UserRole.student, "StudentPass1!", org_id=org.id)
    client_id, secret = _create_client(client, db_session, username="int_admin_rb", org_id=org.id, name="Rollback Connector")

    path = "/api/v1/integrations/sis/students"
    invalid_schema_payload = {"import_id": "bad-1", "students": [{"external_id": "S1"}]}
    invalid_schema_body = json.dumps(invalid_schema_payload).encode("utf-8")
    invalid_schema = client.post(path, data=invalid_schema_body, headers=_signed_headers(secret, client_id, path, invalid_schema_body, "rbnonce-1"))
    assert invalid_schema.status_code == 422
    assert db_session.query(IntegrationImport).filter(IntegrationImport.client_id == client_id, IntegrationImport.import_id == "bad-1").count() == 0

    rollback_payload = {
        "import_id": "rollback-1",
        "students": [
            {"external_id": "S10", "username": "new_imported_student", "is_active": True},
            {"external_id": "S11", "username": "existing_student", "is_active": True},
        ],
    }
    rollback_body = json.dumps(rollback_payload).encode("utf-8")
    rollback = client.post(path, data=rollback_body, headers=_signed_headers(secret, client_id, path, rollback_body, "rbnonce-2"))
    assert rollback.status_code == 409

    db_session.expire_all()
    persisted = db_session.query(User).filter(User.source_client_id == client_id).all()
    assert persisted == []
    assert db_session.query(IntegrationImport).filter(IntegrationImport.client_id == client_id, IntegrationImport.import_id == "rollback-1").count() == 0


def test_malformed_json_returns_422(client, db_session: Session) -> None:
    org = _create_org(db_session, "JSON Org", "JSONORG")
    client_id, secret = _create_client(client, db_session, username="int_admin_json", org_id=org.id, name="JSON Connector")

    path = "/api/v1/integrations/qbank/forms"
    body = b'{"import_id":"bad-json","forms":[}'
    response = client.post(path, data=body, headers=_signed_headers(secret, client_id, path, body, "jsonnonce-1"))
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_json"


def test_invalid_signature_does_not_consume_rate_limit(client, db_session: Session) -> None:
    org = _create_org(db_session, "Rate Org", "RATEORG")
    client_id, secret = _create_client(client, db_session, username="int_admin_rate", org_id=org.id, name="Rate Connector", rate_limit_rpm=2)

    path = "/api/v1/integrations/qbank/forms"
    body = json.dumps(
        {"import_id": "rate-1", "forms": [{"external_id": "F1", "name": "Rate Form", "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]}]}
    ).encode("utf-8")
    base_ts = str(int(datetime.now(timezone.utc).timestamp()))

    bad_headers = _signed_headers(secret, client_id, path, body, "rate-bad", timestamp=base_ts)
    bad_headers["X-Signature-256"] = "deadbeef"
    bad = client.post(path, data=body, headers=bad_headers)
    assert bad.status_code == 401

    body_1 = json.dumps(
        {"import_id": "rate-2", "forms": [{"external_id": "F2", "name": "Rate Form 2", "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]}]}
    ).encode("utf-8")
    ok_1 = client.post(path, data=body_1, headers=_signed_headers(secret, client_id, path, body_1, "rate-1", timestamp=base_ts))
    assert ok_1.status_code == 200

    body_2 = json.dumps(
        {"import_id": "rate-3", "forms": [{"external_id": "F3", "name": "Rate Form 3", "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]}]}
    ).encode("utf-8")
    ok_2 = client.post(path, data=body_2, headers=_signed_headers(secret, client_id, path, body_2, "rate-2", timestamp=base_ts))
    assert ok_2.status_code == 200

    body_3 = json.dumps(
        {"import_id": "rate-4", "forms": [{"external_id": "F4", "name": "Rate Form 4", "criteria": [{"name": "Q", "weight": 1, "min": 0, "max": 5}]}]}
    ).encode("utf-8")
    over = client.post(path, data=body_3, headers=_signed_headers(secret, client_id, path, body_3, "rate-3", timestamp=base_ts))
    assert over.status_code == 429
