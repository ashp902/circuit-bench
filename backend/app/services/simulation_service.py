from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from app.models.circuit import Circuit, SimulationError, SimulationResult
from app.services.netlist_service import AcAnalysis, NetlistService, TransientAnalysis


class NgspiceSimulator:
    """Run generated netlists in isolated temporary directories."""

    def __init__(
        self,
        netlists: NetlistService | None = None,
        executable: str | None = None,
        timeout_seconds: float = 5,
        simulation_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._netlists = netlists or NetlistService()
        self._executable = executable or os.environ.get("NGSPICE_BIN", "ngspice")
        self._timeout_seconds = timeout_seconds
        self._simulation_id_factory = simulation_id_factory or (lambda: f"sim_{uuid.uuid4().hex}")

    def run_operating_point(self, circuit: Circuit, output_nodes: list[str], current_components: list[str] | None = None) -> SimulationResult:
        current_components = current_components or []
        netlist = self._netlists.build_operating_point(circuit, output_nodes, current_components)
        rows, error = self._execute(netlist)
        result = self._base_result("operating_point", circuit, error)
        if error is not None:
            return result
        values = rows[0][1:]
        result.measurements = {f"voltage_v:{node}": value for node, value in zip(output_nodes, values)}
        offset = len(output_nodes)
        result.measurements.update({f"current_a:{component_id}": value for component_id, value in zip(current_components, values[offset:])})
        return result

    def run_ac(self, circuit: Circuit, analysis: AcAnalysis, current_components: list[str] | None = None) -> SimulationResult:
        current_components = current_components or []
        netlist = self._netlists.build_ac(circuit, analysis, current_components)
        rows, error = self._execute(netlist)
        result = self._base_result("ac", circuit, error)
        if error is not None:
            return result
        frequencies = [row[0] for row in rows]
        input_real_values = [row[1] for row in rows]
        input_imaginary_values = [row[2] for row in rows]
        output_real_values = [row[3] for row in rows]
        output_imaginary_values = [row[4] for row in rows]
        input_magnitudes = [math.hypot(real, imaginary) for real, imaginary in zip(input_real_values, input_imaginary_values)]
        output_magnitudes = [math.hypot(real, imaginary) for real, imaginary in zip(output_real_values, output_imaginary_values)]
        transfer_real_values = []
        transfer_imaginary_values = []
        gains_db = []
        phases_deg = []
        for input_real, input_imaginary, output_real, output_imaginary, input_magnitude, output_magnitude in zip(
            input_real_values,
            input_imaginary_values,
            output_real_values,
            output_imaginary_values,
            input_magnitudes,
            output_magnitudes,
        ):
            denominator = max(input_magnitude**2, 1e-300)
            # The AC source is normalized to 1 V in the netlist, but gain is
            # always derived from the measured complex ratio VOUT / VIN.
            transfer_real = (output_real * input_real + output_imaginary * input_imaginary) / denominator
            transfer_imaginary = (output_imaginary * input_real - output_real * input_imaginary) / denominator
            transfer_real_values.append(transfer_real)
            transfer_imaginary_values.append(transfer_imaginary)
            transfer_magnitude = math.hypot(transfer_real, transfer_imaginary)
            gains_db.append(20 * math.log10(max(transfer_magnitude, 1e-300)))
            phases_deg.append(math.degrees(math.atan2(transfer_imaginary, transfer_real)))
        result.series = {
            "frequency_hz": frequencies,
            "input_real_v": input_real_values,
            "input_imag_v": input_imaginary_values,
            "output_real_v": output_real_values,
            "output_imag_v": output_imaginary_values,
            "output_magnitude_v": output_magnitudes,
            "transfer_real": transfer_real_values,
            "transfer_imaginary": transfer_imaginary_values,
            "output_gain_db": gains_db,
            "output_phase_deg": phases_deg,
        }
        for index, component_id in enumerate(current_components):
            real = [row[5 + index * 2] for row in rows]
            imaginary = [row[6 + index * 2] for row in rows]
            result.series[f"current_magnitude_a:{component_id}"] = [math.hypot(real_value, imaginary_value) for real_value, imaginary_value in zip(real, imaginary)]
        return result

    def run_transient(self, circuit: Circuit, analysis: TransientAnalysis, current_components: list[str] | None = None) -> SimulationResult:
        current_components = current_components or []
        netlist = self._netlists.build_transient(circuit, analysis, current_components)
        rows, error = self._execute(netlist)
        result = self._base_result("transient", circuit, error)
        if error is not None:
            return result
        result.series = {"time_s": [row[0] for row in rows]}
        for index, node in enumerate(analysis.output_nodes, start=1):
            result.series[f"voltage_v:{node}"] = [row[index] for row in rows]
        offset = 1 + len(analysis.output_nodes)
        for index, component_id in enumerate(current_components):
            result.series[f"current_a:{component_id}"] = [row[offset + index] for row in rows]
        return result

    def _execute(self, netlist: str) -> tuple[list[list[float]], SimulationError | None]:
        executable = shutil.which(self._executable)
        if executable is None:
            return [], SimulationError(code="SIMULATION_FAILED", message="ngspice executable was not found.")
        with tempfile.TemporaryDirectory(prefix="electronics-lab-simulation-") as directory:
            workdir = Path(directory)
            netlist_path = workdir / "circuit.cir"
            log_path = workdir / "ngspice.log"
            result_path = workdir / self._netlists.result_filename
            netlist_path.write_text(netlist, encoding="utf-8")
            try:
                completed = subprocess.run(
                    [executable, "-b", "-o", str(log_path), str(netlist_path)],
                    cwd=workdir,
                    timeout=self._timeout_seconds,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except subprocess.TimeoutExpired:
                return [], SimulationError(code="SIMULATION_TIMEOUT", message="ngspice exceeded the simulation timeout.")
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else completed.stderr
            if completed.returncode != 0 or not result_path.exists():
                return [], SimulationError(code="SIMULATION_FAILED", message="ngspice could not complete the simulation.", details=log[-2_000:])
            try:
                rows = self._parse_rows(result_path.read_text(encoding="utf-8"))
            except (ValueError, IndexError) as parse_error:
                return [], SimulationError(code="SIMULATION_FAILED", message="ngspice returned unreadable data.", details=str(parse_error))
        return rows, None

    @staticmethod
    def _parse_rows(data: str) -> list[list[float]]:
        lines = [line.strip() for line in data.splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError("Result file contains no numeric rows.")
        rows = [[float(token) for token in line.split()] for line in lines[1:]]
        width = len(rows[0])
        if width < 2 or any(len(row) != width for row in rows):
            raise ValueError("Result rows have inconsistent columns.")
        return rows

    def _base_result(self, analysis: str, circuit: Circuit, error: SimulationError | None) -> SimulationResult:
        return SimulationResult(
            success=error is None,
            analysis=analysis,
            circuit_revision=circuit.revision,
            simulation_id=self._simulation_id_factory(),
            errors=[] if error is None else [error],
        )
