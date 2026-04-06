from datetime import datetime, timezone
import hashlib
import json
from difflib import SequenceMatcher

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.admin import Course, Section
from app.models.data_quality import QuarantineEntry, QuarantineStatus
from app.models.review import ScoringForm
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _domain_candidate_values(db: Session, entity_type: str, key: str, payload: dict) -> list[str]:
    if entity_type == "AdminCourseWrite":
        title_query = db.query(Course.title).filter(Course.organization_id == payload.get("organization_id"))
        code_query = db.query(Course.code).filter(Course.organization_id == payload.get("organization_id"))
        if payload.get("existing_entity_id") is not None:
            title_query = title_query.filter(Course.id != payload["existing_entity_id"])
            code_query = code_query.filter(Course.id != payload["existing_entity_id"])
        if key == "title":
            return [str(row[0]) for row in title_query.all() if row[0]]
        if key == "code":
            return [str(row[0]) for row in code_query.all() if row[0]]
    if entity_type == "AdminSectionWrite" and key == "code":
        query = db.query(Section.code).filter(Section.term_id == payload.get("term_id"))
        if payload.get("existing_entity_id") is not None:
            query = query.filter(Section.id != payload["existing_entity_id"])
        rows = query.all()
        return [str(row[0]) for row in rows if row[0]]
    if entity_type == "AdminUserWrite" and key == "username":
        query = db.query(User.username)
        if payload.get("existing_entity_id") is not None:
            query = query.filter(User.id != payload["existing_entity_id"])
        rows = query.all()
        return [str(row[0]) for row in rows if row[0]]
    if entity_type in {"ReviewFormWrite", "IntegrationQbankFormWrite"} and key == "name":
        query = db.query(ScoringForm.name)
        org_id = payload.get("organization_id")
        if org_id is not None:
            query = query.filter(ScoringForm.organization_id == org_id)
        rows = query.all()
        return [str(row[0]) for row in rows if row[0]]
    if entity_type == "IntegrationSISStudentWrite" and key == "username":
        rows = db.query(User.username).filter(User.org_id == payload.get("org_id")).all()
        return [str(row[0]) for row in rows if row[0]]
    return []


def _has_authoritative_duplicate(db: Session, entity_type: str, payload: dict, fingerprint: str) -> bool:
    if entity_type == "AdminCourseWrite":
        query = db.query(Course.id).filter(Course.organization_id == payload.get("organization_id"), Course.code == payload.get("code"))
        if payload.get("existing_entity_id") is not None:
            query = query.filter(Course.id != payload["existing_entity_id"])
        return query.first() is not None
    if entity_type == "AdminSectionWrite":
        query = db.query(Section.id).filter(Section.term_id == payload.get("term_id"), Section.code == payload.get("code"))
        if payload.get("existing_entity_id") is not None:
            query = query.filter(Section.id != payload["existing_entity_id"])
        return query.first() is not None
    if entity_type == "AdminUserWrite":
        query = db.query(User.id).filter(User.username == payload.get("username"))
        if payload.get("existing_entity_id") is not None:
            query = query.filter(User.id != payload["existing_entity_id"])
        return query.first() is not None
    if entity_type == "ReviewFormWrite":
        return db.query(ScoringForm.id).filter(ScoringForm.name == payload.get("name")).first() is not None
    if entity_type == "IntegrationSISStudentWrite":
        source_client_id = payload.get("source_client_id")
        external_id = payload.get("external_id")
        username = payload.get("username")
        if source_client_id and external_id:
            if (
                db.query(User.id)
                .filter(User.source_client_id == source_client_id, User.external_id == external_id)
                .first()
                is not None
            ):
                return True
        if username:
            return (
                db.query(User.id)
                .filter(
                    User.username == username,
                    User.org_id == payload.get("org_id"),
                    User.source_client_id != source_client_id if source_client_id else True,
                )
                .first()
                is not None
            )
    if entity_type == "IntegrationQbankFormWrite":
        source_client_id = payload.get("source_client_id")
        external_id = payload.get("external_id")
        if source_client_id and external_id:
            return (
                db.query(ScoringForm.id)
                .filter(ScoringForm.source_client_id == source_client_id, ScoringForm.external_id == external_id)
                .first()
                is not None
            )
    existing_fingerprint = (
        db.query(QuarantineEntry)
        .filter(QuarantineEntry.entity_type == entity_type, QuarantineEntry.fingerprint == fingerprint)
        .first()
    )
    return existing_fingerprint is not None


def evaluate_payload(
    db: Session,
    *,
    entity_type: str,
    payload: dict,
    required_fields: list[str],
    ranges: dict[str, dict[str, float]],
    unique_keys: list[str],
) -> tuple[bool, int, list[str], str]:
    reasons: list[str] = []
    score = 100

    for field in required_fields:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            reasons.append(f"Missing required field: {field}")
            score -= 20

    for field, bounds in ranges.items():
        if field not in payload:
            continue
        try:
            value = float(payload[field])
        except (TypeError, ValueError):
            reasons.append(f"Range validation failed for {field}: non-numeric")
            score -= 15
            continue
        min_value = bounds.get("min")
        max_value = bounds.get("max")
        if min_value is not None and value < min_value:
            reasons.append(f"Range validation failed for {field}: below minimum")
            score -= 15
        if max_value is not None and value > max_value:
            reasons.append(f"Range validation failed for {field}: above maximum")
            score -= 15

    fingerprint = _fingerprint(payload)
    if _has_authoritative_duplicate(db, entity_type, payload, fingerprint):
        reasons.append("Duplicate record detected")
        score -= 20

    for key in unique_keys:
        if key not in payload:
            continue
        value = str(payload[key])
        authoritative_candidates = _domain_candidate_values(db, entity_type, key, payload)
        for candidate in authoritative_candidates:
            if candidate and _similarity(value.lower(), candidate.lower()) >= settings.dedup_threshold:
                reasons.append(f"Potential duplicate by similarity on '{key}'")
                score -= 15
                break
        if any("Potential duplicate by similarity" in reason for reason in reasons):
            continue
        similar_rows = (
            db.query(QuarantineEntry)
            .filter(QuarantineEntry.entity_type == entity_type)
            .order_by(QuarantineEntry.id.desc())
            .limit(50)
            .all()
        )
        for row in similar_rows:
            try:
                row_payload = json.loads(row.payload_json)
            except json.JSONDecodeError:
                continue
            candidate = str(row_payload.get(key, ""))
            if candidate and _similarity(value.lower(), candidate.lower()) >= settings.dedup_threshold:
                reasons.append(f"Potential duplicate by similarity on '{key}'")
                score -= 15
                break

    score = max(0, min(100, score))
    accepted = len(reasons) == 0
    return accepted, score, reasons, fingerprint


def quarantine_write(
    db: Session,
    *,
    entity_type: str,
    payload: dict,
    reasons: list[str],
    quality_score: int,
    fingerprint: str,
) -> QuarantineEntry:
    entry = QuarantineEntry(
        entity_type=entity_type,
        payload_json=json.dumps(payload, sort_keys=True, default=str),
        rejection_reason="; ".join(reasons),
        quality_score=quality_score,
        fingerprint=fingerprint,
        status=QuarantineStatus.open,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def enforce_write_quality(
    db: Session,
    *,
    entity_type: str,
    payload: dict,
    required_fields: list[str] | None = None,
    ranges: dict[str, dict[str, float]] | None = None,
    unique_keys: list[str] | None = None,
) -> None:
    accepted, score, reasons, fingerprint = evaluate_payload(
        db,
        entity_type=entity_type,
        payload=payload,
        required_fields=required_fields or [],
        ranges=ranges or {},
        unique_keys=unique_keys or [],
    )
    if accepted:
        return
    entry = quarantine_write(
        db,
        entity_type=entity_type,
        payload=payload,
        reasons=reasons,
        quality_score=score,
        fingerprint=fingerprint,
    )
    raise HTTPException(
        status_code=422,
        detail={"accepted": False, "quality_score": score, "reasons": reasons, "quarantine_id": entry.id},
    )


def list_quarantine(db: Session, status: str | None, limit: int, offset: int) -> list[QuarantineEntry]:
    query = db.query(QuarantineEntry)
    if status:
        try:
            parsed = QuarantineStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid status filter") from exc
        query = query.filter(QuarantineEntry.status == parsed)
    return query.order_by(QuarantineEntry.id.desc()).offset(offset).limit(limit).all()


def resolve_quarantine(db: Session, entry_id: int, action: str, resolver_id: int) -> QuarantineEntry:
    entry = db.query(QuarantineEntry).filter(QuarantineEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Quarantine entry not found")
    action_upper = action.upper()
    if action_upper not in {"ACCEPT", "DISCARD"}:
        raise HTTPException(status_code=422, detail="Action must be ACCEPT or DISCARD")
    entry.status = QuarantineStatus.accepted if action_upper == "ACCEPT" else QuarantineStatus.discarded
    entry.resolved_at = _utcnow()
    entry.resolved_by = resolver_id
    db.commit()
    db.refresh(entry)
    return entry


def quality_report(db: Session) -> list[dict]:
    entity_types = [row[0] for row in db.query(QuarantineEntry.entity_type).distinct().all()]
    result: list[dict] = []
    for entity_type in entity_types:
        total = db.query(func.count(QuarantineEntry.id)).filter(QuarantineEntry.entity_type == entity_type).scalar() or 0
        open_items = (
            db.query(func.count(QuarantineEntry.id))
            .filter(QuarantineEntry.entity_type == entity_type, QuarantineEntry.status == QuarantineStatus.open)
            .scalar()
            or 0
        )
        avg_score = (
            db.query(func.avg(QuarantineEntry.quality_score))
            .filter(QuarantineEntry.entity_type == entity_type)
            .scalar()
        )
        result.append(
            {
                "entity_type": entity_type,
                "total_records": int(total),
                "quarantined": int(total),
                "open_items": int(open_items),
                "avg_quality_score": round(float(avg_score or 0.0), 2),
            }
        )
    return result


def flush_or_raise_conflict(db: Session, *, detail: str = "Duplicate record detected.") -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc
