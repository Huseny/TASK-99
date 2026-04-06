import hashlib
import json

from sqlalchemy.orm import Session

from app.models.admin import AuditLog


def _hash_payload(payload: dict | None) -> str | None:
    if payload is None:
        return None
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_audit_log(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_name: str,
    entity_id: int | None,
    before: dict | None,
    after: dict | None,
    metadata: dict | None = None,
    allow_actorless: bool = False,
) -> None:
    if actor_id is None and not allow_actorless:
        raise ValueError(f"Audit actor_id is required for action '{action}'.")
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        before_hash=_hash_payload(before),
        after_hash=_hash_payload(after),
        metadata_json=json.dumps(metadata, sort_keys=True, default=str) if metadata else None,
    )
    db.add(entry)
