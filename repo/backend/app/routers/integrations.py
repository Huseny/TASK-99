import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.auth import require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.integration import (
    IntegrationClientCreateIn,
    IntegrationClientCreateOut,
    IntegrationClientRotateOut,
    QbankFormsImportIn,
    SISStudentsSyncIn,
)
from app.services import integration_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("/clients", response_model=IntegrationClientCreateOut)
def create_client(payload: IntegrationClientCreateIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    client, raw_secret = integration_service.create_client(db, payload.name, payload.rate_limit_rpm, payload.organization_id)
    write_audit_log(
        db,
        actor_id=admin.id,
        action="integrations.client.create",
        entity_name="IntegrationClient",
        entity_id=client.id,
        before=None,
        after={"client_id": client.client_id, "name": client.name, "rate_limit_rpm": client.rate_limit_rpm},
    )
    db.commit()
    return IntegrationClientCreateOut(client_id=client.client_id, client_secret=raw_secret, rate_limit_rpm=client.rate_limit_rpm)


@router.post("/clients/{client_id}/rotate-secret", response_model=IntegrationClientRotateOut)
def rotate_client_secret(client_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    client, raw_secret = integration_service.rotate_client_secret(db, client_id)
    write_audit_log(
        db,
        actor_id=admin.id,
        action="integrations.client.rotate_secret",
        entity_name="IntegrationClient",
        entity_id=client.id,
        before=None,
        after={"client_id": client.client_id},
    )
    db.commit()
    return IntegrationClientRotateOut(client_id=client.client_id, client_secret=raw_secret)


def _auth_integration(request: Request, db: Session):
    body = request.scope.get("_cached_body")
    if body is None:
        raise HTTPException(status_code=400, detail="Request body unavailable")
    return integration_service.authenticate_integration_request(db, request, body)


def _validate_payload(model_cls, body: bytes):
    try:
        return model_cls(**integration_service.parse_json_body(body))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"message": "Invalid integration payload.", "errors": exc.errors()}) from exc


@router.post("/sis/students")
async def sis_students_sync(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    request.scope["_cached_body"] = body
    client = _auth_integration(request, db)
    try:
        payload = _validate_payload(SISStudentsSyncIn, body)
        result = integration_service.sync_students(
            db,
            client=client,
            import_id=payload.import_id,
            body=body,
            students=[item.model_dump() for item in payload.students],
        )
        write_audit_log(
            db,
            actor_id=integration_service.ensure_client_actor(db, client),
            action="integrations.sis.students.sync",
            entity_name="IntegrationClient",
            entity_id=client.id,
            before=None,
            after={"client_id": client.client_id, **result},
            metadata={"client_id": client.client_id, "timestamp": integration_service._utcnow().isoformat(), "action_type": "sync"},
        )
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.post("/qbank/forms")
async def qbank_forms_import(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    request.scope["_cached_body"] = body
    client = _auth_integration(request, db)
    try:
        payload = _validate_payload(QbankFormsImportIn, body)
        result = integration_service.import_forms(
            db,
            client=client,
            import_id=payload.import_id,
            body=body,
            forms=[item.model_dump() for item in payload.forms],
        )
        write_audit_log(
            db,
            actor_id=integration_service.ensure_client_actor(db, client),
            action="integrations.qbank.forms.import",
            entity_name="IntegrationClient",
            entity_id=client.id,
            before=None,
            after={"client_id": client.client_id, **result},
            metadata={"client_id": client.client_id, "timestamp": integration_service._utcnow().isoformat(), "action_type": "import"},
        )
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
