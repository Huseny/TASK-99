#!/bin/sh
set -e

python -c "from app.core.config import settings; settings.validate_required()"

python - <<'PY'
import time
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url)
for _ in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database is ready")
        break
    except Exception:
        time.sleep(2)
else:
    raise RuntimeError("Database not ready after retries")
PY

alembic upgrade head
uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
