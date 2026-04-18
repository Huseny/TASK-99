"""Unit tests for app.services.integration_service.

Pure service-layer tests – no HTTP, in-memory SQLite.
Exercises HMAC signing, timestamp enforcement, rate limiting,
nonce replay detection, and JSON body parsing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.integration_service import (
    _canonical_string,
    _hash_secret,
    _sha256_hex,
    enforce_nonce_available,
    enforce_rate_limit,
    enforce_timestamp,
    parse_json_body,
)


# ---------------------------------------------------------------------------
# _sha256_hex / _hash_secret / _canonical_string  (pure functions)
# ---------------------------------------------------------------------------

class TestPureFunctions:
    def test_sha256_hex_matches_hashlib(self):
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256_hex(data) == expected

    def test_hash_secret_is_deterministic(self):
        assert _hash_secret("mysecret") == _hash_secret("mysecret")

    def test_hash_secret_differs_for_different_inputs(self):
        assert _hash_secret("secret1") != _hash_secret("secret2")

    def test_canonical_string_format(self):
        result = _canonical_string("POST", "/api/v1/integrations/sis/students", "1700000000", "nonce123", "abcdef")
        lines = result.split("\n")
        assert lines[0] == "POST"
        assert lines[1] == "/api/v1/integrations/sis/students"
        assert lines[2] == "1700000000"
        assert lines[3] == "nonce123"
        assert lines[4] == "abcdef"

    def test_canonical_string_uppercases_method(self):
        result = _canonical_string("post", "/path", "ts", "n", "bh")
        assert result.startswith("POST\n")


# ---------------------------------------------------------------------------
# enforce_timestamp
# ---------------------------------------------------------------------------

class TestEnforceTimestamp:
    def _now_ts(self, delta_seconds=0):
        return str(int((datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).timestamp()))

    def test_valid_timestamp_returns_datetime(self):
        ts = self._now_ts()
        result = enforce_timestamp(ts)
        assert isinstance(result, datetime)

    def test_future_within_tolerance_accepted(self):
        ts = self._now_ts(+100)  # 100 seconds into the future (within default 300s window)
        enforce_timestamp(ts)  # should not raise

    def test_past_within_tolerance_accepted(self):
        ts = self._now_ts(-100)  # 100 seconds in the past
        enforce_timestamp(ts)  # should not raise

    def test_expired_timestamp_raises(self):
        ts = self._now_ts(-400)  # beyond default 300s tolerance
        with pytest.raises(HTTPException) as exc:
            enforce_timestamp(ts)
        assert exc.value.status_code == 401

    def test_far_future_timestamp_raises(self):
        ts = self._now_ts(+400)
        with pytest.raises(HTTPException) as exc:
            enforce_timestamp(ts)
        assert exc.value.status_code == 401

    def test_non_integer_timestamp_raises(self):
        with pytest.raises(HTTPException) as exc:
            enforce_timestamp("not-a-number")
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# enforce_nonce_available / enforce_rate_limit  (require DB)
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.integration import IntegrationClient, NonceLog


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_client(db, client_id="cli_test", rate_limit_rpm=5):
    from app.core.security import encrypt_integration_secret
    from app.services.integration_service import _hash_secret, _integration_secret_key_material
    raw_secret = "test-secret-value-xyz"
    client = IntegrationClient(
        client_id=client_id,
        name="Test Client",
        organization_id=None,
        secret_ciphertext=encrypt_integration_secret(raw_secret, _integration_secret_key_material()),
        secret_hash=_hash_secret(raw_secret),
        rate_limit_rpm=rate_limit_rpm,
        is_active=True,
    )
    db.add(client)
    db.flush()
    return client, raw_secret


class TestEnforceNonceAvailable:
    def test_new_nonce_passes(self):
        db = _make_db()
        # Should not raise
        enforce_nonce_available(db, "cli_test", "unique-nonce-1")

    def test_duplicate_nonce_raises(self):
        db = _make_db()
        now = datetime.now(timezone.utc)
        db.add(NonceLog(client_id="cli_test", nonce="reused-nonce", requested_at=now, body_hash="bh", path="/path"))
        db.flush()
        with pytest.raises(HTTPException) as exc:
            enforce_nonce_available(db, "cli_test", "reused-nonce")
        assert exc.value.status_code == 409

    def test_same_nonce_different_client_is_ok(self):
        db = _make_db()
        now = datetime.now(timezone.utc)
        db.add(NonceLog(client_id="cli_a", nonce="shared-nonce", requested_at=now, body_hash="bh", path="/p"))
        db.flush()
        # Different client_id → should not raise
        enforce_nonce_available(db, "cli_b", "shared-nonce")


class TestEnforceRateLimit:
    def test_first_request_passes(self):
        db = _make_db()
        client, _ = _make_client(db, rate_limit_rpm=5)
        now = datetime.now(timezone.utc)
        # Should not raise
        enforce_rate_limit(db, client, now)

    def test_exceeding_rpm_raises(self):
        db = _make_db()
        client, _ = _make_client(db, rate_limit_rpm=2)
        now = datetime.now(timezone.utc)
        # Add 2 nonce logs (= at the limit)
        for i in range(2):
            db.add(NonceLog(client_id=client.client_id, nonce=f"n{i}", requested_at=now, body_hash="bh", path="/p"))
        db.flush()
        with pytest.raises(HTTPException) as exc:
            enforce_rate_limit(db, client, now)
        assert exc.value.status_code == 429

    def test_old_requests_outside_window_not_counted(self):
        db = _make_db()
        client, _ = _make_client(db, rate_limit_rpm=1)
        now = datetime.now(timezone.utc)
        old = now - timedelta(minutes=2)
        db.add(NonceLog(client_id=client.client_id, nonce="old-n", requested_at=old, body_hash="bh", path="/p"))
        db.flush()
        # Old request is outside the 1-minute window → should not raise
        enforce_rate_limit(db, client, now)


# ---------------------------------------------------------------------------
# parse_json_body
# ---------------------------------------------------------------------------

class TestParseJsonBody:
    def test_valid_json_object(self):
        body = json.dumps({"key": "value"}).encode()
        result = parse_json_body(body)
        assert result == {"key": "value"}

    def test_empty_body_returns_empty_dict(self):
        result = parse_json_body(b"")
        assert result == {}

    def test_malformed_json_raises(self):
        with pytest.raises(HTTPException) as exc:
            parse_json_body(b"{not valid json")
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "invalid_json"

    def test_json_array_raises(self):
        with pytest.raises(HTTPException) as exc:
            parse_json_body(b"[1, 2, 3]")
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "invalid_json"

    def test_non_utf8_raises(self):
        with pytest.raises(HTTPException) as exc:
            parse_json_body(b"\xff\xfe invalid utf-8")
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "invalid_json"
