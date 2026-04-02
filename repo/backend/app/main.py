from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import check_db_connection
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.registration import router as registration_router


def create_app() -> FastAPI:
    app = FastAPI(title="CEMS API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    router = APIRouter(prefix="/api/v1")

    @router.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok", "service": "api", "env": settings.environment}

    @router.get("/health/ready", tags=["health"])
    def ready() -> dict[str, str]:
        check_db_connection()
        return {"status": "ready"}

    app.include_router(router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(registration_router, prefix="/api/v1")
    return app


app = create_app()
