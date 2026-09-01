from __future__ import annotations

from app.db.repository import LabRepository
from app.models.circuit import Experiment
from app.services.errors import CircuitError
from app.services.experiment_service import ExperimentService
from app.services.lab_service import LabService, default_lab


def test_restoring_a_run_creates_a_new_revision_without_mutating_history(tmp_path) -> None:
    repository = LabRepository(tmp_path / "history.db")
    challenge, circuit = default_lab()
    repository.initialize(challenge, circuit)
    experiment = Experiment(
        id="exp_001",
        sequence=1,
        hypothesis="Sweep the source voltage.",
        circuit_revision=0,
        circuit_snapshot=circuit,
        generated_runs=[{"index": 1, "values": {"V1.voltage_v": 5.0}, "enabled": True}],
        run_results=[{"run_index": 1, "status": "COMPLETED", "parameters": {"V1.voltage_v": 5.0}, "measurements": {"voltage_v:out": 2.5}}],
    )
    repository.save_experiment(experiment)

    restored = ExperimentService(repository).restore_run("exp_001", 1, expected_revision=0)

    assert restored.revision == 1
    assert next(component for component in restored.components if component.id == "V1").params["voltage_v"] == 5.0
    assert repository.get_experiment("exp_001").circuit_snapshot.revision == 0
    assert repository.get_experiment("exp_001").run_results[0]["parameters"] == {"V1.voltage_v": 5.0}


def test_executed_experiment_definition_cannot_be_rewritten(tmp_path) -> None:
    repository = LabRepository(tmp_path / "immutable.db")
    challenge, circuit = default_lab()
    repository.initialize(challenge, circuit)
    experiment = Experiment(
        id="exp_001",
        sequence=1,
        hypothesis="Existing result.",
        circuit_revision=0,
        circuit_snapshot=circuit,
        run_results=[{"run_index": 1, "status": "COMPLETED", "parameters": {}, "measurements": {"voltage_v:out": 0.0}}],
    )
    repository.save_experiment(experiment)

    class Payload:
        def model_dump(self) -> dict[str, object]:
            return {"circuit_revision": 0}

    try:
        ExperimentService(repository).update_definition("exp_001", circuit, Payload())
    except CircuitError as error:
        assert error.code == "EXPERIMENT_IMMUTABLE"
    else:
        raise AssertionError("Executed experiment definitions must be immutable")


def test_experiment_criterion_modes_are_evaluated() -> None:
    evaluate = ExperimentService._requirement_passes
    assert evaluate(5.0, ">=", 4.75)
    assert evaluate(5.0, "<=", 5.25)
    assert evaluate(5.0, "between", [4.75, 5.25])
    assert not evaluate(5.5, "between", [4.75, 5.25])
    assert evaluate(5.02, "approximately", 5.0, 0.05)
    assert not evaluate(5.08, "approximately", 5.0, 0.05)


def test_experiment_traceability_metadata_persists_with_a_definition(tmp_path) -> None:
    repository = LabRepository(tmp_path / "traceability.db")
    challenge, circuit = default_lab()
    repository.initialize(challenge, circuit)

    class Payload:
        def model_dump(self) -> dict[str, object]:
            return {
                "name": "Bias tolerance sweep",
                "description": "Confirm operating margin.",
                "experiment_type": "validation",
                "circuit_revision": 0,
                "variables": [{"component_id": "R1", "parameter": "resistance_ohm"}],
                "measurement_definitions": ["Output Voltage"],
                "requirement_definitions": [],
                "generated_runs": [{"index": 1, "values": {"R1.resistance_ohm": 1_000}, "enabled": True}],
                "collection_name": "Release validation",
                "run_by": "A. Engineer",
                "notes": "Bench configuration checked before execution.",
            }

    saved = ExperimentService(repository).save_definition(circuit, Payload())
    reloaded = repository.get_experiment(saved.id)

    assert reloaded.collection_name == "Release validation"
    assert reloaded.run_by == "A. Engineer"
    assert reloaded.notes == "Bench configuration checked before execution."


def test_custom_experiment_type_does_not_break_lab_state_loading(tmp_path) -> None:
    repository = LabRepository(tmp_path / "custom-type.db")
    challenge, circuit = default_lab()
    repository.initialize(challenge, circuit)
    repository.save_experiment(
        Experiment(
            id="exp_001",
            sequence=1,
            hypothesis="Sweep RC tolerance.",
            circuit_id=circuit.id,
            circuit_revision=circuit.revision,
            circuit_snapshot=circuit,
            experiment_type="ac_tolerance",
        )
    )

    state = LabService(repository).get_state()

    assert state["latest_experiment"].experiment_type == "ac_tolerance"


def test_legacy_completed_run_missing_required_measurements_loads_as_incomplete(tmp_path) -> None:
    repository = LabRepository(tmp_path / "legacy-incomplete.db")
    challenge, circuit = default_lab()
    repository.initialize(challenge, circuit)
    repository.save_experiment(
        Experiment(
            id="exp_001",
            sequence=1,
            hypothesis="Legacy broken AC run.",
            circuit_id=circuit.id,
            circuit_revision=circuit.revision,
            circuit_snapshot=circuit,
            measurement_definitions=[{"id": "gain_800_hz", "type": "ac_gain_db", "frequency_hz": 800.0}],
            generated_runs=[{"index": 1, "values": {}, "enabled": True}],
            run_results=[{"run_index": 1, "status": "COMPLETED", "measurements": {}}],
            execution_status="completed",
        )
    )

    loaded = repository.get_experiment("exp_001")

    assert loaded.run_results[0]["status"] == "INCOMPLETE"
    assert "gain_800_hz" in loaded.run_results[0]["incomplete_reason"]
    assert loaded.execution_status == "failed"
