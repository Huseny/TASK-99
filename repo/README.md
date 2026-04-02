# Collegiate Enrollment & Assessment Management System

## Services
- `db`: PostgreSQL 15
- `api`: FastAPI backend (`http://localhost:8000`)
- `web`: React + MUI frontend (`http://localhost:5173`)

## Quick Start
1. Copy `.env.example` to `.env` if needed.
2. Build and start services:
   - `docker compose up --build -d`
3. Check API health:
   - `http://localhost:8000/api/v1/health/live`
   - `http://localhost:8000/api/v1/health/ready`
4. Open frontend:
   - `http://localhost:5173`

## Run Tests
- `./run_tests.sh`

## Notes
- The backend runs Alembic migrations at startup.
- The frontend is served by an independent `web` container.
