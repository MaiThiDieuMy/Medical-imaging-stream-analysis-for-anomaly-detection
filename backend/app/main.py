from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.monitoring import metrics_router, router as monitoring_router
from app.core.config import settings
from app.monitoring.metrics import record_request


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    cors_origins = [
        origin.strip()
        for origin in settings.backend_cors_origins.split(",")
        if origin.strip()
    ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            record_request(
                path=request.url.path,
                method=request.method,
                status_code=500,
            )
            raise
        record_request(
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
        )
        return response

    @app.get("/", tags=["root"])
    def read_root() -> dict[str, str]:
        return {
            "project_name": "Medical-imaging-stream-analysis-for-nomaly-detection",
            "status": "ok",
            "docs_url": "/docs",
            "health_url": "/health",
            "metrics_url": "/metrics",
            "frontend_url": settings.frontend_url,
        }

    app.include_router(health_router)
    app.include_router(health_router, prefix=settings.api_v1_prefix)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(analysis_router, prefix=settings.api_v1_prefix)
    app.include_router(admin_router, prefix=settings.api_v1_prefix)
    app.include_router(monitoring_router, prefix=settings.api_v1_prefix)
    app.include_router(metrics_router)
    return app


app = create_app()
