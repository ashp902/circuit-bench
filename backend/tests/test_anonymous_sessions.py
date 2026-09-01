from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.repository import LabRepository
from app.main import SESSION_COOKIE_NAME, create_app
from app.services.session_service import AnonymousSessionManager


def _invoke(client: TestClient, tool: str, arguments: dict[str, object] | None = None):
    return client.post("/api/webmcp/invoke", json={"tool": tool, "arguments": arguments or {}})


def test_anonymous_browser_sessions_isolate_all_lab_owned_state(tmp_path) -> None:
    database_path = tmp_path / "sessions.db"
    application = create_app(database_path)
    assert not hasattr(application.state, "lab_service")
    assert not hasattr(application.state, "webmcp_tools")

    with TestClient(application) as browser_a, TestClient(application) as browser_b:
        state_a = browser_a.get("/api/lab")
        state_b = browser_b.get("/api/lab")
        assert state_a.status_code == state_b.status_code == 200
        assert state_a.json()["circuit"]["components"] == []
        assert state_b.json()["circuit"]["components"] == []
        assert browser_a.cookies.get(SESSION_COOKIE_NAME) != browser_b.cookies.get(SESSION_COOKIE_NAME)

        circuit_a = browser_a.post("/api/circuits/blank", json={"name": "Circuit A"}).json()
        circuit_a_id = circuit_a["active_saved_circuit_id"]
        added_a = _invoke(
            browser_a,
            "add_component",
            {"type": "resistor", "params": {"resistance_ohm": 4_700}, "expected_revision": 0},
        )
        assert added_a.status_code == 200

        assert browser_b.get("/api/circuits").json() == []
        forbidden_open = browser_b.post(f"/api/circuits/{circuit_a_id}/open", json={})
        assert forbidden_open.status_code == 404
        assert forbidden_open.json()["error"]["code"] == "CIRCUIT_NOT_FOUND"

        circuit_b = _invoke(browser_b, "create_blank_circuit", {"name": "Circuit B"}).json()
        assert circuit_b["circuit"]["name"] == "Circuit B"
        added_b = _invoke(
            browser_b,
            "add_component",
            {"type": "capacitor", "params": {"capacitance_f": 1e-7}, "expected_revision": 0},
        )
        assert added_b.status_code == 200

        assert [item["name"] for item in browser_a.get("/api/circuits").json()] == ["Circuit A"]
        assert [item["name"] for item in browser_b.get("/api/circuits").json()] == ["Circuit B"]
        assert [item["type"] for item in _invoke(browser_a, "get_circuit").json()["components"]] == ["resistor"]
        assert [item["type"] for item in _invoke(browser_b, "get_circuit").json()["components"]] == ["capacitor"]

        experiment_a = browser_a.post(
            "/api/experiment-definitions",
            json={"name": "A-only experiment", "circuit_revision": 1},
        )
        assert experiment_a.status_code == 200
        experiment_a_id = experiment_a.json()["id"]
        assert len(browser_a.get("/api/experiments").json()) == 1
        assert browser_b.get("/api/experiments").json() == []

        forbidden_report = _invoke(browser_b, "get_report", {"experiment_id": experiment_a_id})
        assert forbidden_report.status_code == 404
        assert forbidden_report.json()["error"]["code"] == "EXPERIMENT_NOT_FOUND"

        experiment_b = browser_b.post(
            "/api/experiment-definitions",
            json={"name": "B-only experiment", "circuit_revision": 1},
        )
        assert experiment_b.status_code == 200
        assert experiment_b.json()["id"] == experiment_a_id
        assert browser_a.get("/api/experiments").json()[0]["name"] == "A-only experiment"
        assert browser_b.get("/api/experiments").json()[0]["name"] == "B-only experiment"


def test_session_cookie_is_secure_opaque_and_survives_app_restart(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "persistent-sessions.db"
    monkeypatch.setenv("LAB_ENV", "production")
    first_app = create_app(database_path)
    first_client = TestClient(first_app, base_url="https://testserver")

    response = first_client.post("/api/circuits/blank", json={"name": "Persistent Circuit"})
    token = first_client.cookies.get(SESSION_COOKIE_NAME)
    assert response.status_code == 200
    assert token
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Max-Age=2592000" in set_cookie

    with sqlite3.connect(database_path) as connection:
        stored_hash, = connection.execute("SELECT token_hash FROM anonymous_sessions").fetchone()
    assert stored_hash != token
    assert token not in json.dumps(stored_hash)

    second_client = TestClient(create_app(database_path), base_url="https://testserver")
    second_client.cookies.set(SESSION_COOKIE_NAME, token, domain="testserver.local", path="/")
    restored = second_client.get("/api/lab")
    assert restored.status_code == 200
    assert restored.json()["circuit"]["name"] == "Persistent Circuit"


def test_webmcp_schemas_do_not_expose_session_identifiers(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "tool-schemas.db"))
    definitions = client.get("/api/webmcp/tools")
    assert definitions.status_code == 200
    assert "session_id" not in json.dumps(definitions.json()).lower()


def test_health_checks_do_not_allocate_anonymous_labs(tmp_path) -> None:
    database_path = tmp_path / "health.db"
    client = TestClient(create_app(database_path))
    assert client.get("/health").status_code == 200
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM anonymous_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM labs").fetchone()[0] == 0


def test_optional_cleanup_removes_only_inactive_session_labs(tmp_path) -> None:
    database_path = tmp_path / "cleanup.db"
    manager = AnonymousSessionManager(database_path)
    inactive = manager.resolve(None)
    active = manager.resolve(None)
    now = datetime.now(timezone.utc)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE anonymous_sessions SET last_seen_at = ? WHERE lab_id = ?",
            ((now - timedelta(days=31)).isoformat(), inactive.lab_id),
        )

    assert manager.cleanup_inactive(now=now) == 1
    with sqlite3.connect(database_path) as connection:
        lab_ids = {row[0] for row in connection.execute("SELECT id FROM labs")}
        session_lab_ids = {row[0] for row in connection.execute("SELECT lab_id FROM anonymous_sessions")}
    assert inactive.lab_id not in lab_ids
    assert lab_ids == session_lab_ids == {active.lab_id}


def test_existing_global_database_is_migrated_without_losing_rows(tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE labs (id TEXT PRIMARY KEY, challenge_json TEXT NOT NULL, active_saved_circuit_id TEXT);
            CREATE TABLE circuits (lab_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, circuit_json TEXT NOT NULL);
            CREATE TABLE simulations (id TEXT PRIMARY KEY, lab_id TEXT NOT NULL, circuit_revision INTEGER NOT NULL, success INTEGER NOT NULL, result_json TEXT NOT NULL);
            CREATE TABLE experiments (id TEXT PRIMARY KEY, lab_id TEXT NOT NULL, sequence INTEGER NOT NULL, experiment_json TEXT NOT NULL, UNIQUE(lab_id, sequence));
            CREATE TABLE saved_circuits (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, saved_circuit_json TEXT NOT NULL);
            INSERT INTO labs VALUES ('default', '{}', NULL);
            INSERT INTO circuits VALUES ('default', 0, '{}');
            INSERT INTO experiments VALUES ('exp_001', 'default', 1, '{}');
            INSERT INTO saved_circuits VALUES ('circuit_001', 'Legacy', '2026-01-01', '2026-01-01', '{}');
            """
        )

    LabRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        experiment_pk = [row[1] for row in sorted(connection.execute("PRAGMA table_info(experiments)"), key=lambda row: row[5]) if row[5]]
        saved_pk = [row[1] for row in sorted(connection.execute("PRAGMA table_info(saved_circuits)"), key=lambda row: row[5]) if row[5]]
        assert connection.execute("SELECT id, lab_id FROM experiments").fetchall() == [("exp_001", "default")]
        assert connection.execute("SELECT id, lab_id FROM saved_circuits").fetchall() == [("circuit_001", "default")]
    assert experiment_pk == ["lab_id", "id"]
    assert saved_pk == ["lab_id", "id"]
