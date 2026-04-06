import asyncio

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import check_db_connection
from app.core.logging import clear_request_id, configure_logging, ensure_request_id, get_logger
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.data_quality import router as data_quality_router
from app.routers.finance import router as finance_router
from app.routers.integrations import router as integrations_router
from app.routers.messaging import router as messaging_router
from app.routers.registration import router as registration_router
from app.routers.reviews import router as reviews_router
from app.services import messaging_service


def create_app() -> FastAPI:
    configure_logging()
    logger = get_logger("app.main")
    app = FastAPI(title="CEMS API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = ensure_request_id(request.headers.get("X-Request-ID"))
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                extra={
                    "event": "http.request.completed",
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                    },
                },
            )
            return response
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "event": "http.request.failed",
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                    },
                },
            )
            return JSONResponse(status_code=500, content={"detail": "Internal server error."}, headers={"X-Request-ID": request_id})
        finally:
            clear_request_id()

    @app.on_event("startup")
    async def start_background_jobs() -> None:
        if not settings.messaging_poller_enabled:
            return
        stop_event = asyncio.Event()
        app.state.messaging_poller_stop_event = stop_event
        app.state.messaging_poller_task = asyncio.create_task(
            messaging_service.run_due_notification_poller(stop_event, settings.messaging_poller_interval_seconds)
        )

    @app.on_event("shutdown")
    async def stop_background_jobs() -> None:
        stop_event = getattr(app.state, "messaging_poller_stop_event", None)
        task = getattr(app.state, "messaging_poller_task", None)
        if stop_event is None or task is None:
            return
        stop_event.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()

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
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(finance_router, prefix="/api/v1")
    app.include_router(messaging_router, prefix="/api/v1")
    app.include_router(data_quality_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    return app


app = create_app()
