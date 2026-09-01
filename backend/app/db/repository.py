from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.circuit import Challenge, Circuit, Experiment, SavedCircuit, SimulationResult
from app.services.errors import CircuitError


class LabRepository:
    """Small SQLite repository using JSON snapshots at stable service boundaries."""

    lab_id = "default"

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def initialize(self, challenge: Challenge, circuit: Circuit) -> None:
        with self._connect() as connection:
            existing = connection.execute("SELECT 1 FROM labs WHERE id = ?", (self.lab_id,)).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO labs (id, challenge_json, active_saved_circuit_id) VALUES (?, ?, NULL)",
                    (self.lab_id, challenge.model_dump_json()),
                )
                connection.execute(
                    "INSERT INTO circuits (lab_id, revision, circuit_json) VALUES (?, ?, ?)",
                    (self.lab_id, circuit.revision, circuit.model_dump_json()),
                )

    def reset(self, challenge: Challenge, circuit: Circuit) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM experiments WHERE lab_id = ?", (self.lab_id,))
            connection.execute("DELETE FROM simulations WHERE lab_id = ?", (self.lab_id,))
            connection.execute(
                "INSERT OR REPLACE INTO labs (id, challenge_json, active_saved_circuit_id) VALUES (?, ?, NULL)",
                (self.lab_id, challenge.model_dump_json()),
            )
            connection.execute(
                "INSERT OR REPLACE INTO circuits (lab_id, revision, circuit_json) VALUES (?, ?, ?)",
                (self.lab_id, circuit.revision, circuit.model_dump_json()),
            )

    def activate_saved_circuit(self, saved: SavedCircuit) -> None:
        """Switch the active workbench without deleting experiment history."""
        self.activate_lab(saved.challenge_snapshot, saved.circuit_snapshot, saved.id)

    def activate_lab(self, challenge: Challenge, circuit: Circuit, active_saved_circuit_id: str | None = None) -> None:
        """Switch the active workbench without deleting experiment history."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE labs SET challenge_json = ?, active_saved_circuit_id = ? WHERE id = ?",
                (challenge.model_dump_json(), active_saved_circuit_id, self.lab_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO circuits (lab_id, revision, circuit_json) VALUES (?, ?, ?)",
                (self.lab_id, circuit.revision, circuit.model_dump_json()),
            )

    def get_active_saved_circuit_id(self) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT active_saved_circuit_id FROM labs WHERE id = ?", (self.lab_id,)).fetchone()
        return str(row[0]) if row and row[0] is not None else None

    def get_challenge(self) -> Challenge:
        with self._connect() as connection:
            row = connection.execute("SELECT challenge_json FROM labs WHERE id = ?", (self.lab_id,)).fetchone()
        if row is None:
            raise RuntimeError("Lab repository has not been initialized.")
        return Challenge.model_validate_json(row[0])

    def get_circuit(self) -> Circuit:
        with self._connect() as connection:
            row = connection.execute("SELECT circuit_json FROM circuits WHERE lab_id = ?", (self.lab_id,)).fetchone()
        if row is None:
            raise RuntimeError("Lab repository has not been initialized.")
        return Circuit.model_validate_json(row[0])

    def save_circuit(self, circuit: Circuit, previous_revision: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE circuits SET revision = ?, circuit_json = ? WHERE lab_id = ? AND revision = ?",
                (circuit.revision, circuit.model_dump_json(), self.lab_id, previous_revision),
            )
            if cursor.rowcount != 1:
                raise CircuitError(
                    "STALE_REVISION",
                    f"Circuit changed since revision {previous_revision}.",
                    "Call get_circuit and retry using the latest revision.",
                )

    def save_simulation(self, simulation: SimulationResult) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO simulations (id, lab_id, circuit_revision, success, result_json) VALUES (?, ?, ?, ?, ?)",
                (
                    simulation.simulation_id,
                    self.lab_id,
                    simulation.circuit_revision,
                    int(simulation.success),
                    simulation.model_dump_json(),
                ),
            )

    def get_simulation(self, simulation_id: str) -> SimulationResult:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM simulations WHERE id = ? AND lab_id = ?",
                (simulation_id, self.lab_id),
            ).fetchone()
        if row is None:
            raise CircuitError("MEASUREMENT_UNAVAILABLE", f"Simulation {simulation_id} does not exist.")
        return SimulationResult.model_validate_json(row[0])

    def successful_simulation_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM simulations WHERE lab_id = ? AND success = 1",
                (self.lab_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def save_experiment(self, experiment: Experiment) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO experiments (id, lab_id, sequence, experiment_json) VALUES (?, ?, ?, ?)",
                (experiment.id, self.lab_id, experiment.sequence, experiment.model_dump_json()),
            )

    def save_saved_circuit(self, saved: SavedCircuit) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO saved_circuits (id, name, created_at, updated_at, saved_circuit_json) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at, saved_circuit_json = excluded.saved_circuit_json",
                (saved.id, saved.name, saved.created_at.isoformat(), saved.updated_at.isoformat(), saved.model_dump_json()),
            )

    def get_saved_circuit(self, circuit_id: str) -> SavedCircuit:
        with self._connect() as connection:
            row = connection.execute("SELECT saved_circuit_json FROM saved_circuits WHERE id = ?", (circuit_id,)).fetchone()
        if row is None:
            raise CircuitError("CIRCUIT_NOT_FOUND", f"Saved circuit {circuit_id} does not exist.")
        return SavedCircuit.model_validate_json(row[0])

    def list_saved_circuits(self) -> list[SavedCircuit]:
        with self._connect() as connection:
            rows = connection.execute("SELECT saved_circuit_json FROM saved_circuits ORDER BY updated_at DESC, name COLLATE NOCASE").fetchall()
        return [SavedCircuit.model_validate_json(row[0]) for row in rows]

    def delete_saved_circuit(self, circuit_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM saved_circuits WHERE id = ?", (circuit_id,))
            if cursor.rowcount != 1:
                raise CircuitError("CIRCUIT_NOT_FOUND", f"Saved circuit {circuit_id} does not exist.")

    def next_saved_circuit_sequence(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM saved_circuits").fetchone()
        return (int(row[0]) if row else 0) + 1

    def update_experiment(self, experiment: Experiment) -> None:
        with self._connect() as connection:
            cursor = connection.execute("UPDATE experiments SET experiment_json = ? WHERE id = ? AND lab_id = ?", (experiment.model_dump_json(), experiment.id, self.lab_id))
            if cursor.rowcount != 1:
                raise CircuitError("EXPERIMENT_NOT_FOUND", f"Experiment {experiment.id} does not exist.")

    def delete_experiment(self, experiment_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM experiments WHERE id = ? AND lab_id = ?", (experiment_id, self.lab_id))
            if cursor.rowcount != 1:
                raise CircuitError("EXPERIMENT_NOT_FOUND", f"Experiment {experiment_id} does not exist.")

    def next_experiment_sequence(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM experiments WHERE lab_id = ?",
                (self.lab_id,),
            ).fetchone()
        return int(row[0]) if row else 1

    def get_experiment(self, experiment_id: str) -> Experiment:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT experiment_json FROM experiments WHERE id = ? AND lab_id = ?",
                (experiment_id, self.lab_id),
            ).fetchone()
        if row is None:
            raise CircuitError("EXPERIMENT_NOT_FOUND", f"Experiment {experiment_id} does not exist.")
        return Experiment.model_validate_json(row[0])

    def list_experiments(self, active_circuit_id: str | None = None) -> list[Experiment]:
        with self._connect() as connection:
            rows = connection.execute("SELECT experiment_json FROM experiments WHERE lab_id = ? ORDER BY sequence DESC", (self.lab_id,)).fetchall()
        experiments = [Experiment.model_validate_json(row[0]) for row in rows]
        if active_circuit_id is not None:
            experiments = [e for e in experiments if (e.circuit_id or e.circuit_snapshot.id) == active_circuit_id]
        return experiments

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS labs (
                    id TEXT PRIMARY KEY,
                    challenge_json TEXT NOT NULL,
                    active_saved_circuit_id TEXT
                );
                CREATE TABLE IF NOT EXISTS circuits (
                    lab_id TEXT PRIMARY KEY REFERENCES labs(id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    circuit_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS simulations (
                    id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
                    circuit_revision INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    experiment_json TEXT NOT NULL,
                    UNIQUE(lab_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS saved_circuits (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    saved_circuit_json TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(labs)")}
            if "active_saved_circuit_id" not in columns:
                connection.execute("ALTER TABLE labs ADD COLUMN active_saved_circuit_id TEXT")
