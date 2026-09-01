from pathlib import Path

from fastapi.testclient import TestClient

from app.main import _cors_origins_from_environment, _database_path_from_environment, app, create_app


def test_health_returns_ready_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "electronics-lab-api"}


def test_lab_db_path_overrides_legacy_database_url(monkeypatch) -> None:
    monkeypatch.setenv("LAB_DB_PATH", "/mounted/lab.db")
    monkeypatch.setenv("LAB_DATABASE_URL", "sqlite:////legacy/lab.db")

    assert _database_path_from_environment() == Path("/mounted/lab.db")


def test_production_defaults_to_mounted_data_directory(monkeypatch) -> None:
    monkeypatch.delenv("LAB_DB_PATH", raising=False)
    monkeypatch.delenv("LAB_DATABASE_URL", raising=False)
    monkeypatch.setenv("LAB_ENV", "production")

    assert _database_path_from_environment() == Path("/data/lab.db")


def test_production_defaults_to_same_origin_requests(monkeypatch) -> None:
    monkeypatch.delenv("LAB_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("LAB_ENV", "production")

    assert _cors_origins_from_environment() == []


def test_production_app_serves_exported_frontend_without_shadowing_api(monkeypatch, tmp_path) -> None:
    frontend_directory = tmp_path / "static"
    frontend_directory.mkdir()
    (frontend_directory / "index.html").write_text("<main>Circuit Bench</main>")
    monkeypatch.setenv("LAB_FRONTEND_DIR", str(frontend_directory))

    client = TestClient(create_app(tmp_path / "lab.db"))

    assert client.get("/").text == "<main>Circuit Bench</main>"
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/webmcp/tools").status_code == 200
