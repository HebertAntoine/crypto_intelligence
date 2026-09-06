"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .api.routes_lot2 import router as lot2_router
from .api.routes_lot3 import router as lot3_router
from .api.routes_lot4 import router as lot4_router
from .api.routes_lot5 import router as lot5_router
from .db.session import init_db
from .knowledge.store import ensure_fts
from .logging_setup import get_logger, setup_logging
from .providers.http import get_http
from .settings import get_settings

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level, json_logs=settings.env != "local")
    init_db()
    ensure_fts()
    log.info(
        "startup", mock_mode=settings.mock_mode, database=settings.resolved_database_url,
        port=settings.api_port,
    )

    scheduler = None
    if settings.scheduler_enabled:
        from .scheduler import start_scheduler

        scheduler = start_scheduler()
        log.info("scheduler_started")

    yield

    if scheduler:
        scheduler.shutdown(wait=False)
    await get_http().close()
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Crypto Intelligence",
        description=(
            "Personal AI-assisted crypto market analysis (BTC/ETH/SOL). "
            "Analysis only - this service never places orders."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    app.include_router(lot2_router, prefix="/api")
    app.include_router(lot3_router, prefix="/api")
    app.include_router(lot4_router, prefix="/api")
    app.include_router(lot5_router, prefix="/api")

    @app.exception_handler(Exception)
    async def unhandled(request, exc: Exception):
        # Surface the reason instead of an opaque 500 - this is a local tool and
        # the user is the developer.
        log.warning("unhandled_error", path=str(request.url), error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": type(exc).__name__, "detail": str(exc)[:500]},
        )

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React app from the same origin as the API.

    One origin means no CORS in production and no separate web server. When
    `frontend/dist` has not been built, the API still runs and `/` returns a
    JSON banner instead - useful in development, where Vite serves the UI on
    its own port and proxies `/api` here.
    """
    from pathlib import Path

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    index = dist / "index.html"

    if not index.exists():
        @app.get("/")
        async def root() -> dict[str, str]:
            return {
                "name": "Crypto Intelligence API",
                "version": "0.1.0",
                "docs": "/docs",
                "api": "/api/health",
                "frontend": "not built - run `npm run build` in frontend/",
                "note": "Analysis only. No orders are ever placed.",
            }

        return

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        """Return index.html for any non-API path.

        React Router owns the client-side routes (/chart, /trader-knowledge,
        ...), so a deep link must reach the app rather than 404. API and docs
        routes are registered before this catch-all and therefore win.
        """
        if full_path.startswith(("api/", "docs", "openapi.json", "redoc")):
            raise HTTPException(status_code=404, detail="Not found")

        # Serve a real file when one exists (favicon, manifest, ...).
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)

    log.info("frontend_mounted", path=str(dist))


app = create_app()
