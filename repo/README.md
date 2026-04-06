# Collegiate Enrollment & Assessment Management System

## Services
- `db`: PostgreSQL 15
- `api`: FastAPI backend (`http://localhost:8000`)
- `web`: React + MUI frontend (`http://localhost:5173`)

## Quick Start (Docker)
1. Optional: copy `.env.example` to `.env` for local overrides.
2. Build and start services:
   - `docker compose up --build -d`
3. Check API health:
   - `http://localhost:8000/api/v1/health/live`
   - `http://localhost:8000/api/v1/health/ready`
4. Open frontend:
   - `http://localhost:5173`

Docker compose includes development-safe defaults for required backend settings; CI can override any value using environment variables.
`SECRET_KEY` must be at least 24 characters long and must not use weak placeholder values. The provided default is suitable for local development only and should be overridden in shared or production environments.

## Local Setup (No Docker)
- Backend prerequisites:
  - Python 3.11+
  - Create a virtual environment from repo root:
    - Windows PowerShell: `python -m venv .venv; .\.venv\Scripts\Activate.ps1`
    - Bash: `python -m venv .venv; source .venv/bin/activate`
  - Install backend dependencies: `python -m pip install -r backend/requirements.txt`
- Frontend prerequisites:
  - Node.js 20+
  - Install frontend dependencies: `cd frontend && npm ci`

## Run Tests
- Docker: `./run_tests.sh`
- Windows non-Docker one-shot verifier: `powershell -ExecutionPolicy Bypass -File .\verify_local_windows.ps1`
- Windows verifier modes:
  - Prerequisites only: `powershell -ExecutionPolicy Bypass -File .\verify_local_windows.ps1 -PrereqOnly`
  - Backend only: `powershell -ExecutionPolicy Bypass -File .\verify_local_windows.ps1 -SkipFrontend`
  - Frontend only: `powershell -ExecutionPolicy Bypass -File .\verify_local_windows.ps1 -SkipBackend`
- Local backend (no Docker):
  - `cd backend`
  - `python -m pytest unit_tests/ -v --tb=short`
  - `python -m pytest API_tests/ -v --tb=short`
- Local frontend checks (no Docker):
  - `cd frontend`
  - `npm run test`
  - `npm run build`
  - `npm run test:e2e`

## Troubleshooting
- `No module named pytest`:
  - Run prerequisite validation: `powershell -ExecutionPolicy Bypass -File .\verify_local_windows.ps1 -PrereqOnly`
  - Reinstall backend deps via verifier: `powershell -ExecutionPolicy Bypass -File .\verify_local_windows.ps1 -SkipFrontend`
  - If needed manually: `.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt`
- `spawn EPERM` during frontend build/test on Windows:
  - Re-run backend-only checks first: `powershell -ExecutionPolicy Bypass -File .\verify_local_windows.ps1 -SkipFrontend`
  - Close editors/terminals that may lock `node_modules/.bin`.
  - Remove and reinstall deps: `Remove-Item -Recurse -Force .\frontend\node_modules; npm --prefix .\frontend ci`
  - Re-run frontend checks manually: `npm --prefix .\frontend run test` then `npm --prefix .\frontend run build`
- First-time Playwright run prompts for browser install:
  - `cd frontend && npx playwright install`

## Notes
- The backend runs Alembic migrations at startup.
- The frontend is served by an independent `web` container.
- Audit retention policy is 7 years with archive-then-purge, runnable by admin via `POST /api/v1/admin/audit-log/retention`.
- If `SECRET_KEY` is missing or invalid, the API fails fast during startup with a configuration error.
