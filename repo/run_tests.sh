#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Ensure the core services (db + api + web) are running.
# docker compose up -d is idempotent: already-running containers are left
# untouched; stopped/missing ones are (re)started.
# ---------------------------------------------------------------------------
echo "==> Ensuring core services are up..."
docker compose up -d db api web

# ---------------------------------------------------------------------------
# Wait for the API container to report healthy (max 120 s / 40 × 3 s polls).
# The healthcheck is defined in docker-compose.yml and pings /health/live.
# ---------------------------------------------------------------------------
echo "==> Waiting for API to become healthy (up to 120s)..."
n=0
until docker inspect --format="{{.State.Health.Status}}" cems_api 2>/dev/null | grep -q "^healthy$"; do
  n=$((n + 1))
  if [ "$n" -ge 40 ]; then
    echo "ERROR: API did not become healthy within 120s" >&2
    exit 1
  fi
  sleep 3
done

# ---------------------------------------------------------------------------
# Backend tests — run inside the existing api container
# ---------------------------------------------------------------------------
echo ""
echo "==> Running backend unit tests..."
docker compose exec api pytest unit_tests/ -v --tb=short

echo ""
echo "==> Running backend API tests..."
docker compose exec api pytest API_tests/ -v --tb=short

echo ""
echo "==> Running backend integration tests..."
docker compose exec api pytest integration/ -v --tb=short

# ---------------------------------------------------------------------------
# Frontend unit tests — run inside a throwaway frontend-test container.
# docker compose run --rm starts a fresh container, waits for depends_on
# (api healthy), runs the command, then removes the container.
# ---------------------------------------------------------------------------
echo ""
echo "==> Running frontend unit tests (Vitest)..."
docker compose run --rm frontend-test npm run test

# ---------------------------------------------------------------------------
# Frontend E2E tests — Playwright starts its own Vite dev server (via the
# webServer config in playwright.config.js), which proxies /api/* to the api
# service using the VITE_API_PROXY_TARGET env var set in docker-compose.yml.
# BACKEND_URL tells the test setup code where to reach the API directly.
# ---------------------------------------------------------------------------
echo ""
echo "==> Running frontend E2E tests (Playwright)..."
docker compose run --rm frontend-test npm run test:e2e

echo ""
echo "All tests passed."
