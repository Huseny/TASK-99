from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decrypt_integration_secret, encrypt_integration_secret, hash_password
from app.models.integration import IntegrationClient, IntegrationImport, NonceLog
from app.models.review import ScoringForm
from app.models.user import User, UserRole
from app.services import data_quality_service


logger = get_logger("app.integrations")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_secret(secret: str) -> str:
    return _sha256_hex(secret.encode("utf-8"))


def _integration_secret_key_material() -> str:
    return settings.integration_secret_enc_key or settings.secret_key


def _integration_actor_username(client_id: str) -> str:
    return f"__integration_actor__{client_id}"


def ensure_client_actor(db: Session, client: IntegrationClient) -> int:
    if client.actor_user_id is not None:
        return int(client.actor_user_id)
    actor = db.query(User).filter(User.username == _integration_actor_username(client.client_id)).first()
    if actor is None:
        actor = User(
            username=_integration_actor_username(client.client_id),
            password_hash=hash_password(secrets.token_urlsafe(24)),
            role=UserRole.admin,
            is_active=False,
            org_id=client.organization_id,
        )
        db.add(actor)
        db.flush()
    client.actor_user_id = actor.id
    db.flush()
    return int(actor.id)


def create_client(db: Session, name: str, rate_limit_rpm: int | None, organization_id: int | None) -> tuple[IntegrationClient, str]:
    raw_secret = secrets.token_urlsafe(36)
    client_id = f"cli_{secrets.token_hex(8)}"
    client = IntegrationClient(
        client_id=client_id,
        name=name,
        organization_id=organization_id,
        secret_ciphertext=encrypt_integration_secret(raw_secret, _integration_secret_key_material()),
        secret_hash=_hash_secret(raw_secret),
        rate_limit_rpm=rate_limit_rpm or settings.rate_limit_rpm,
        is_active=True,
    )
    db.add(client)
    db.flush()
    client.actor_user_id = ensure_client_actor(db, client)
    db.commit()
    db.refresh(client)
    return client, raw_secret


def _canonical_string(method: str, path: str, timestamp: str, nonce: str, body_hash: str) -> str:
    return f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"


def verify_request_signature(
    *,
    request: Request,
    body: bytes,
    client: IntegrationClient,
    timestamp: str,
    nonce: str,
    signature: str,
) -> None:
    body_hash = _sha256_hex(body)
    canonical = _canonical_string(request.method, request.url.path, timestamp, nonce, body_hash)
    client_secret = decrypt_integration_secret(client.secret_ciphertext, _integration_secret_key_material())
    expected = hmac.new(
        key=client_secret.encode("utf-8"),
        msg=canonical.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected.lower()):
        logger.info(
            "integration_signature_invalid",
            extra={"event": "integrations.auth.signature_invalid", "fields": {"client_id": client.client_id, "path": request.url.path}},
        )
        raise HTTPException(status_code=401, detail="Invalid signature.")


def enforce_timestamp(timestamp: str) -> datetime:
    try:
        ts_int = int(timestamp)
    except ValueError as exc:
        logger.info("integration_timestamp_invalid", extra={"event": "integrations.auth.timestamp_invalid"})
        raise HTTPException(status_code=401, detail="Invalid timestamp header.") from exc
    requested_at = datetime.fromtimestamp(ts_int, tz=timezone.utc)
    now = _utcnow()
    tolerance = timedelta(seconds=settings.hmac_timestamp_tolerance)
    if requested_at < (now - tolerance) or requested_at > (now + tolerance):
        logger.info("integration_timestamp_outside_window", extra={"event": "integrations.auth.timestamp_outside_window"})
        raise HTTPException(status_code=401, detail="Request timestamp outside allowed window.")
    return requested_at


def enforce_rate_limit(db: Session, client: IntegrationClient, requested_at: datetime) -> None:
    window_start = requested_at - timedelta(minutes=1)
    count = (
        db.query(func.count(NonceLog.id))
        .filter(NonceLog.client_id == client.client_id, NonceLog.requested_at >= window_start)
        .scalar()
    )
    if int(count or 0) >= client.rate_limit_rpm:
        logger.info(
            "integration_rate_limit_exceeded",
            extra={"event": "integrations.auth.rate_limited", "fields": {"client_id": client.client_id}},
        )
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")


def enforce_nonce_available(db: Session, client_id: str, nonce: str) -> None:
    existing = db.query(NonceLog.id).filter(NonceLog.client_id == client_id, NonceLog.nonce == nonce).first()
    if existing is not None:
        logger.info(
            "integration_nonce_reuse",
            extra={"event": "integrations.auth.nonce_reused", "fields": {"client_id": client_id}},
        )
        raise HTTPException(status_code=409, detail="Nonce has already been used.")


def consume_nonce(db: Session, client_id: str, nonce: str, requested_at: datetime, body: bytes, path: str) -> None:
    try:
        db.add(
            NonceLog(
                client_id=client_id,
                nonce=nonce,
                requested_at=requested_at,
                body_hash=_sha256_hex(body),
                path=path,
            )
        )
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Nonce has already been used.") from exc


def authenticate_integration_request(db: Session, request: Request, body: bytes) -> IntegrationClient:
    client_id = request.headers.get("X-Client-ID")
    signature = request.headers.get("X-Signature-256")
    nonce = request.headers.get("X-Nonce")
    timestamp = request.headers.get("X-Timestamp")
    if not client_id or not signature or not nonce or not timestamp:
        logger.info("integration_headers_missing", extra={"event": "integrations.auth.headers_missing"})
        raise HTTPException(status_code=401, detail="Missing integration authentication headers.")

    client = db.query(IntegrationClient).filter(IntegrationClient.client_id == client_id, IntegrationClient.is_active.is_(True)).first()
    if client is None:
        logger.info("integration_client_unknown", extra={"event": "integrations.auth.client_unknown", "fields": {"client_id": client_id}})
        raise HTTPException(status_code=401, detail="Unknown integration client.")
    ensure_client_actor(db, client)

    requested_at = enforce_timestamp(timestamp)
    verify_request_signature(
        request=request,
        body=body,
        client=client,
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
    )
    enforce_nonce_available(db, client_id, nonce)
    enforce_rate_limit(db, client, requested_at)
    consume_nonce(db, client_id, nonce, requested_at, body, request.url.path)
    db.commit()
    logger.info(
        "integration_auth_succeeded",
        extra={"event": "integrations.auth.success", "fields": {"client_id": client.client_id, "path": request.url.path}},
    )
    return client


def rotate_client_secret(db: Session, client_id: str) -> tuple[IntegrationClient, str]:
    client = db.query(IntegrationClient).filter(IntegrationClient.client_id == client_id).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Integration client not found.")

    raw_secret = secrets.token_urlsafe(36)
    ensure_client_actor(db, client)
    client.secret_ciphertext = encrypt_integration_secret(raw_secret, _integration_secret_key_material())
    client.secret_hash = _hash_secret(raw_secret)
    db.commit()
    db.refresh(client)
    return client, raw_secret


def parse_json_body(body: bytes) -> dict:
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail={"message": "Request body must be valid UTF-8 JSON.", "error": "invalid_json"}) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail={"message": "Malformed JSON payload.", "error": "invalid_json"}) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail={"message": "JSON body must be an object.", "error": "invalid_json"})
    return payload


def _register_import(db: Session, *, client: IntegrationClient, import_type: str, import_id: str, body: bytes) -> IntegrationImport | None:
    payload_hash = _sha256_hex(body)
    existing = (
        db.query(IntegrationImport)
        .filter(
            IntegrationImport.client_id == client.client_id,
            IntegrationImport.import_type == import_type,
            IntegrationImport.import_id == import_id,
        )
        .first()
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="Import ID has already been used with different payload.")
        return existing

    entry = IntegrationImport(
        client_id=client.client_id,
        import_type=import_type,
        import_id=import_id,
        payload_hash=payload_hash,
    )
    db.add(entry)
    db.flush()
    return None


def _ensure_client_org(client: IntegrationClient) -> int:
    if client.organization_id is None:
        raise HTTPException(status_code=403, detail="Integration client is not bound to an organization.")
    return int(client.organization_id)


def sync_students(db: Session, *, client: IntegrationClient, import_id: str, body: bytes, students: list[dict]) -> dict:
    organization_id = _ensure_client_org(client)
    existing = _register_import(db, client=client, import_type="sis.students", import_id=import_id, body=body)
    if existing is not None:
        return json.loads(existing.result_json or "{}")

    created = 0
    updated = 0
    for item in students:
        row = (
            db.query(User)
            .filter(User.source_client_id == client.client_id, User.external_id == item["external_id"])
            .first()
        )
        quality_payload = {
            "external_id": item["external_id"],
            "username": item["username"],
            "org_id": organization_id,
            "source_client_id": client.client_id,
        }
        if row is None:
            data_quality_service.enforce_write_quality(
                db,
                entity_type="IntegrationSISStudentWrite",
                payload=quality_payload,
                required_fields=["external_id", "username", "org_id", "source_client_id"],
                unique_keys=["username"],
            )
        conflicting_username = (
            db.query(User.id)
            .filter(
                User.username == item["username"],
                User.org_id == organization_id,
                ~(
                    (User.source_client_id == client.client_id)
                    & (User.external_id == item["external_id"])
                ),
            )
            .first()
        )
        if conflicting_username is not None:
            raise HTTPException(status_code=409, detail=f"Username '{item['username']}' is already assigned in this organization.")
        if row is None:
            row = User(
                username=item["username"],
                password_hash=hash_password(secrets.token_urlsafe(24)),
                role=UserRole.student,
                is_active=bool(item.get("is_active", True)),
                org_id=organization_id,
                source_client_id=client.client_id,
                external_id=item["external_id"],
            )
            db.add(row)
            created += 1
        else:
            row.username = item["username"]
            row.is_active = bool(item.get("is_active", True))
            row.org_id = organization_id
            row.role = UserRole.student
            updated += 1
        db.flush()

    result = {"import_id": import_id, "created": created, "updated": updated, "processed": len(students), "ignored": 0}
    db.query(IntegrationImport).filter(
        IntegrationImport.client_id == client.client_id,
        IntegrationImport.import_type == "sis.students",
        IntegrationImport.import_id == import_id,
    ).update({"result_json": json.dumps(result, sort_keys=True)})
    db.flush()
    return result


def import_forms(db: Session, *, client: IntegrationClient, import_id: str, body: bytes, forms: list[dict]) -> dict:
    organization_id = _ensure_client_org(client)
    existing = _register_import(db, client=client, import_type="qbank.forms", import_id=import_id, body=body)
    if existing is not None:
        return json.loads(existing.result_json or "{}")

    created = 0
    updated = 0
    for item in forms:
        row = (
            db.query(ScoringForm)
            .filter(ScoringForm.source_client_id == client.client_id, ScoringForm.external_id == item["external_id"])
            .first()
        )
        quality_payload = {
            "external_id": item["external_id"],
            "name": item["name"],
            "organization_id": organization_id,
            "source_client_id": client.client_id,
        }
        if row is None:
            data_quality_service.enforce_write_quality(
                db,
                entity_type="IntegrationQbankFormWrite",
                payload=quality_payload,
                required_fields=["external_id", "name", "organization_id", "source_client_id"],
                unique_keys=["name"],
            )
        if row is None:
            row = ScoringForm(
                name=item["name"],
                criteria=item["criteria"],
                organization_id=organization_id,
                source_client_id=client.client_id,
                external_id=item["external_id"],
            )
            db.add(row)
            created += 1
        else:
            row.name = item["name"]
            row.criteria = item["criteria"]
            row.organization_id = organization_id
            updated += 1
        db.flush()

    result = {"import_id": import_id, "created": created, "updated": updated, "processed": len(forms), "ignored": 0}
    db.query(IntegrationImport).filter(
        IntegrationImport.client_id == client.client_id,
        IntegrationImport.import_type == "qbank.forms",
        IntegrationImport.import_id == import_id,
    ).update({"result_json": json.dumps(result, sort_keys=True)})
    db.flush()
    return result
