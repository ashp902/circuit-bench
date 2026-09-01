from __future__ import annotations

import shutil

import pytest

from scripts.validate_agent_loops import rehearse


pytestmark = [pytest.mark.ngspice, pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")]


@pytest.mark.parametrize(
    ("challenge_id", "required_successes"),
    [("challenge_filter_01", 4), ("challenge_sensor_01", 3), ("challenge_debug_01", 3)],
)
def test_reliability_targets_with_primitive_webmcp_agent_workflows(tmp_path, challenge_id: str, required_successes: int) -> None:
    reports = [rehearse(challenge_id, tmp_path / f"{challenge_id}_{attempt}.db") for attempt in range(5)]
    assert sum(report.passed for report in reports) >= required_successes
    assert all(report.invalid_actions == 0 for report in reports)
    assert all(report.simulator_failures == 0 for report in reports)
    assert all(report.simulations_run > 0 for report in reports)
