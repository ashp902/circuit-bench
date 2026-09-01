import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.db.repository import LabRepository
from app.services.errors import CircuitError
from app.services.challenge_catalog import blank_circuit
from app.services.lab_service import LabService
from app.webmcp.tools import WebMCPToolRegistry


def create_app(database_path: Path | None = None) -> FastAPI:
    application = FastAPI(
        title="Autonomous Electronics Lab API",
        version="0.1.0",
        description="Canonical backend for shared circuit state and simulations.",
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
    repository = LabRepository(resolved_path)
    challenge, circuit = blank_circuit()
    repository.initialize(challenge, circuit)
    application.state.lab_service = LabService(repository)
    application.state.webmcp_tools = WebMCPToolRegistry(application.state.lab_service)
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


app = create_app()
