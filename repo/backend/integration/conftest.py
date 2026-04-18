"""Session-scoped fixtures shared across external HTTP integration tests."""
from __future__ import annotations

import os
import time

import httpx
import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL_ENV = "BASE_URL"
_BASE_URL_DEFAULT = "http://localhost:8000"

# Stable credentials used for the integration-test admin account.
# Bootstrap creates this account on a fresh DB; subsequent runs re-use it.
_ADMIN_USERNAME = "ext_integration_admin"
_ADMIN_PASSWORD = "ExtInt3gration@2026!"

_BOOTSTRAP_TOKEN_ENV = "BOOTSTRAP_ADMIN_TOKEN"
_BOOTSTRAP_TOKEN_DEFAULT = "integration-test-bootstrap-2026"

_SERVICE_READY_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url() -> str:
    """Resolve the service base URL.

    Reads BASE_URL from the environment; defaults to http://localhost:8000.
    Trailing slash is stripped for consistent URL construction.
    """
    return os.environ.get(_BASE_URL_ENV, _BASE_URL_DEFAULT).rstrip("/")


@pytest.fixture(scope="session", autouse=True)
def wait_for_service(base_url: str) -> None:
    """Block until the service responds on /api/v1/health/live.

    Retries every second for up to 30 s and raises RuntimeError if the
    service remains unreachable, failing the entire session early with a
    clear message rather than cryptic connection errors per test.
    """
    deadline = time.monotonic() + _SERVICE_READY_TIMEOUT
    last_exc: Exception | None = None

    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/api/v1/health/live", timeout=3.0)
            if r.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        time.sleep(1)

    raise RuntimeError(
        f"Service at {base_url} did not become ready within {_SERVICE_READY_TIMEOUT} s. "
        f"Last error: {last_exc}"
    )


@pytest.fixture(scope="session")
def admin_token(base_url: str, wait_for_service: None) -> str:
    """Return a valid admin session token.

    On a fresh database the bootstrap endpoint creates the admin account.
    On subsequent runs (409 = admin already exists) we go straight to login,
    picking up the account created by a prior run.

    Skips the entire session with a clear message when neither bootstrap
    nor login succeeds so that CI reports exactly what is wrong.
    """
    bootstrap_token = os.environ.get(_BOOTSTRAP_TOKEN_ENV, _BOOTSTRAP_TOKEN_DEFAULT)

    # Attempt bootstrap – safe to ignore 409 (admin already exists).
    httpx.post(
        f"{base_url}/api/v1/auth/bootstrap-admin",
        json={
            "username": _ADMIN_USERNAME,
            "password": _ADMIN_PASSWORD,
            "bootstrap_token": bootstrap_token,
        },
        timeout=10.0,
    )

    login = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": _ADMIN_USERNAME, "password": _ADMIN_PASSWORD},
        timeout=10.0,
    )
    if login.status_code != 200:
        pytest.skip(
            f"Integration admin login failed (HTTP {login.status_code}). "
            "Ensure the Docker service is running with the correct BOOTSTRAP_ADMIN_TOKEN. "
            f"Response: {login.text[:200]}"
        )

    return login.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token: str) -> dict[str, str]:
    """Authorization headers carrying the integration admin bearer token."""
    return {"Authorization": f"Bearer {admin_token}"}
