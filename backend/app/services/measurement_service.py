from __future__ import annotations

import bisect
import math
from typing import Literal

from app.models.circuit import SimulationResult
from app.services.errors import CircuitError


VoltageMode = Literal["dc", "max", "min", "final"]
CurrentMode = Literal["dc", "max", "min", "final"]


class MeasurementService:
    """Convert simulator vectors into small, deterministic engineering facts."""

    def measure_voltage(self, simulation: SimulationResult, node: str, mode: VoltageMode) -> float:
        self._require_success(simulation)
        if mode == "dc":
            key = f"voltage_v:{node}"
            if simulation.analysis != "operating_point" or key not in simulation.measurements:
                raise self._unavailable(f"DC voltage for node {node} is not present in this simulation.")
            return simulation.measurements[key]

        values = self._series(simulation, f"voltage_v:{node}")
        if simulation.analysis != "transient":
            raise self._unavailable(f"Transient voltage for node {node} is not present in this simulation.")
        if mode == "max":
            return max(values)
        if mode == "min":
            return min(values)
        return values[-1]

    def measure_current(self, simulation: SimulationResult, component_id: str, mode: CurrentMode) -> float:
        self._require_success(simulation)
        if mode == "dc":
            key = f"current_a:{component_id}"
            if simulation.analysis != "operating_point" or key not in simulation.measurements:
                raise self._unavailable(f"DC branch current for {component_id} is not present in this simulation.")
            return simulation.measurements[key]
        series_key = f"current_magnitude_a:{component_id}" if simulation.analysis == "ac" else f"current_a:{component_id}"
        values = self._series(simulation, series_key)
        if mode == "max":
            return max(values)
        if mode == "min":
            return min(values)
        return values[-1]

    def measure_gain(self, simulation: SimulationResult, frequency_hz: float) -> float:
        self._require_analysis(simulation, "ac")
        frequencies = self._series(simulation, "frequency_hz")
        gains = self._series(simulation, "output_gain_db")
        return self._interpolate(frequencies, gains, frequency_hz)

    def measure_cutoff_frequency(self, simulation: SimulationResult) -> float | None:
        self._require_analysis(simulation, "ac")
        frequencies = self._series(simulation, "frequency_hz")
        gains = self._series(simulation, "output_gain_db")
        if len(frequencies) < 2 or len(frequencies) != len(gains):
            raise self._unavailable("AC simulation does not contain enough matched points.")

        target_gain = gains[0] - 3.0
        for index in range(1, len(gains)):
            previous_gain = gains[index - 1]
            current_gain = gains[index]
            if previous_gain >= target_gain >= current_gain:
                return self._interpolate_pair(
                    previous_gain,
                    frequencies[index - 1],
                    current_gain,
                    frequencies[index],
                    target_gain,
                )
        return None

    def measure_rise_time(self, simulation: SimulationResult, node: str) -> float:
        self._require_analysis(simulation, "transient")
        times = self._series(simulation, "time_s")
        values = self._series(simulation, f"voltage_v:{node}")
        if len(times) < 2 or len(times) != len(values):
            raise self._unavailable("Transient simulation does not contain enough matched points.")

        initial = values[0]
        final = values[-1]
        span = final - initial
        if math.isclose(span, 0.0, abs_tol=1e-15):
            raise self._unavailable("Rise time requires a non-zero transition.")
        level_10 = initial + 0.1 * span
        level_90 = initial + 0.9 * span
        time_10 = self._crossing_time(times, values, level_10, rising=span > 0)
        time_90 = self._crossing_time(times, values, level_90, rising=span > 0)
        rise_time = time_90 - time_10
        if rise_time < 0:
            raise self._unavailable("Waveform does not contain an ordered 10% to 90% transition.")
        return rise_time

    def measure_overshoot(self, simulation: SimulationResult, node: str) -> float:
        self._require_analysis(simulation, "transient")
        values = self._series(simulation, f"voltage_v:{node}")
        initial = values[0]
        final = values[-1]
        transition = abs(final - initial)
        if math.isclose(transition, 0.0, abs_tol=1e-15):
            raise self._unavailable("Overshoot requires a non-zero transition.")
        peak_excursion = max(values) - final if final >= initial else final - min(values)
        return max(0.0, peak_excursion / transition * 100)

    def _crossing_time(self, times: list[float], values: list[float], level: float, *, rising: bool) -> float:
        for index in range(1, len(values)):
            previous = values[index - 1]
            current = values[index]
            crossed = previous <= level <= current if rising else previous >= level >= current
            if crossed:
                return self._interpolate_pair(previous, times[index - 1], current, times[index], level)
        raise self._unavailable(f"Waveform never crosses {level:.6g} V.")

    def _interpolate(self, x_values: list[float], y_values: list[float], target_x: float) -> float:
        if len(x_values) < 2 or len(x_values) != len(y_values):
            raise self._unavailable("Measurement series are missing or mismatched.")
        if target_x < x_values[0] or target_x > x_values[-1]:
            raise self._unavailable(f"Requested value {target_x:g} is outside the simulated range.")
        right = bisect.bisect_left(x_values, target_x)
        if right < len(x_values) and x_values[right] == target_x:
            return y_values[right]
        return self._interpolate_pair(x_values[right - 1], y_values[right - 1], x_values[right], y_values[right], target_x)

    @staticmethod
    def _interpolate_pair(x0: float, y0: float, x1: float, y1: float, target_x: float) -> float:
        if math.isclose(x0, x1):
            return y0
        fraction = (target_x - x0) / (x1 - x0)
        return y0 + fraction * (y1 - y0)

    def _require_analysis(self, simulation: SimulationResult, analysis: str) -> None:
        self._require_success(simulation)
        if simulation.analysis != analysis:
            raise self._unavailable(f"Measurement requires {analysis} analysis, not {simulation.analysis}.")

    @staticmethod
    def _require_success(simulation: SimulationResult) -> None:
        if not simulation.success:
            raise CircuitError("MEASUREMENT_UNAVAILABLE", "Measurements are unavailable for a failed simulation.")

    def _series(self, simulation: SimulationResult, key: str) -> list[float]:
        values = simulation.series.get(key)
        if not values:
            raise self._unavailable(f"Simulation series {key} is unavailable.")
        return values

    @staticmethod
    def _unavailable(message: str) -> CircuitError:
        return CircuitError("MEASUREMENT_UNAVAILABLE", message, "Run the required simulation over a suitable range.")
