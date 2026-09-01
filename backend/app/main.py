import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.services.errors import CircuitError
from app.services.session_service import AnonymousSessionManager, SESSION_LIFETIME
from app.webmcp.tools import WebMCPToolRegistry


SESSION_COOKIE_NAME = "circuit_bench_session"


def create_app(database_path: Path | None = None) -> FastAPI:
    application = FastAPI(
        title="Autonomous Electronics Lab API",
        version="0.1.0",
        description="Canonical backend for session-isolated circuit state and simulations.",
    )
    cors_origins = _cors_origins_from_environment()
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    resolved_path = database_path or _database_path_from_environment()
    session_manager = AnonymousSessionManager(resolved_path)
    application.state.session_manager = session_manager

    @application.middleware("http")
    async def anonymous_lab_session(request: Request, call_next):
        if not _requires_lab_session(request):
            return await call_next(request)
        session = session_manager.resolve(request.cookies.get(SESSION_COOKIE_NAME))
        lab_service = session_manager.service_for(session)
        request.state.lab_service = lab_service
        request.state.webmcp_tools = WebMCPToolRegistry(lab_service)
        response = await call_next(request)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session.token,
            max_age=int(SESSION_LIFETIME.total_seconds()),
            httponly=True,
            secure=_secure_session_cookie(),
            samesite="lax",
            path="/",
        )
        return response

    if _cleanup_sessions_enabled():
        session_manager.cleanup_inactive()
    application.include_router(router)

    @application.exception_handler(CircuitError)
    async def circuit_error_handler(_request: Request, error: CircuitError) -> JSONResponse:
        status_code = 409 if error.code == "STALE_REVISION" else 404 if error.code.endswith("NOT_FOUND") else 422
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "recovery_hint": error.recovery_hint,
                }
            },
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "electronics-lab-api"}

    frontend_directory = _frontend_directory_from_environment()
    if frontend_directory.is_dir():
        application.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")

    return application


def _database_path_from_environment() -> Path:
    database_path = os.environ.get("LAB_DB_PATH")
    if database_path:
        return Path(database_path).expanduser()
    database_url = os.environ.get("LAB_DATABASE_URL")
    if database_url and database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///"))
    if os.environ.get("LAB_ENV", "").lower() == "production":
        return Path("/data/lab.db")
    return Path(__file__).resolve().parents[1] / "lab.db"


def _cors_origins_from_environment() -> list[str]:
    configured = os.environ.get("LAB_CORS_ORIGINS")
    if configured is not None:
        return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    if os.environ.get("LAB_ENV", "").lower() == "production":
        return []
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def _frontend_directory_from_environment() -> Path:
    configured = os.environ.get("LAB_FRONTEND_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "static"


def _requires_lab_session(request: Request) -> bool:
    return request.method != "OPTIONS" and (request.url.path == "/" or request.url.path.startswith("/api/"))


def _secure_session_cookie() -> bool:
    return os.environ.get("LAB_ENV", "").lower() == "production"


def _cleanup_sessions_enabled() -> bool:
    return os.environ.get("LAB_CLEANUP_INACTIVE_SESSIONS", "").lower() in {"1", "true", "yes"}


app = create_app()
