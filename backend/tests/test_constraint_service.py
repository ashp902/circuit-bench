from __future__ import annotations

import pytest

from app.models.circuit import Constraint
from app.services.constraint_service import ConstraintService


@pytest.mark.parametrize(
    ("operator", "target", "actual", "expected"),
    [
        ("<", 5.0, 4.0, "PASS"),
        ("<=", 5.0, 5.0, "PASS"),
        (">", 5.0, 4.0, "FAIL"),
        (">=", 5.0, 5.0, "PASS"),
        ("between", (1.0, 3.0), 2.0, "PASS"),
        ("between", (1.0, 3.0), 4.0, "FAIL"),
        ("approximately", 10.0, 10.05, "PASS"),
        ("approximately", 10.0, 10.2, "FAIL"),
    ],
)
def test_constraint_operators(operator: str, target: float | tuple[float, float], actual: float, expected: str) -> None:
    constraint = Constraint(id="requirement", metric="value", operator=operator, target=target)

    result = ConstraintService().evaluate_one(constraint, actual)

    assert result.status == expected


def test_missing_measurement_is_not_evaluated() -> None:
    constraint = Constraint(id="cutoff", metric="cutoff_frequency_hz", operator="<=", target=500)

    evaluation = ConstraintService().evaluate([constraint], {})

    assert evaluation.all_pass is False
    assert evaluation.not_evaluated == 1
    assert evaluation.results[0].status == "NOT_EVALUATED"


def test_rc_cutoff_acceptance_constraints_pass_and_fail() -> None:
    constraints = [
        Constraint(id="expected_band", metric="cutoff_frequency_hz", operator="between", target=(1_400, 1_800)),
        Constraint(id="too_slow", metric="cutoff_frequency_hz", operator="<=", target=500),
    ]

    evaluation = ConstraintService().evaluate(constraints, {"cutoff_frequency_hz": 1_591.5})

    assert evaluation.passed == 1
    assert evaluation.failed == 1
    assert [result.status for result in evaluation.results] == ["PASS", "FAIL"]
