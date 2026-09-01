from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from app.models.circuit import Constraint, ConstraintEvaluation, ConstraintResult


class ConstraintService:
    """Evaluate numeric requirements without delegating pass/fail decisions to an agent."""

    def evaluate(self, constraints: Sequence[Constraint], measurements: Mapping[str, float]) -> ConstraintEvaluation:
        results = [self.evaluate_one(constraint, measurements.get(constraint.metric)) for constraint in constraints]
        passed = sum(result.status == "PASS" for result in results)
        failed = sum(result.status == "FAIL" for result in results)
        not_evaluated = sum(result.status == "NOT_EVALUATED" for result in results)
        return ConstraintEvaluation(
            all_pass=bool(results) and passed == len(results),
            passed=passed,
            failed=failed,
            not_evaluated=not_evaluated,
            results=results,
        )

    def evaluate_one(self, constraint: Constraint, actual: float | None) -> ConstraintResult:
        if actual is None or not math.isfinite(actual):
            return ConstraintResult(
                constraint_id=constraint.id,
                status="NOT_EVALUATED",
                target=constraint.target,
                message=f"{constraint.metric} has not been measured.",
            )

        target = constraint.target
        if constraint.operator == "between":
            assert isinstance(target, tuple)
            passed = target[0] <= actual <= target[1]
        else:
            assert isinstance(target, float)
            if constraint.operator == "<":
                passed = actual < target
            elif constraint.operator == "<=":
                passed = actual <= target
            elif constraint.operator == ">":
                passed = actual > target
            elif constraint.operator == ">=":
                passed = actual >= target
            else:
                tolerance = constraint.tolerance if constraint.tolerance is not None else max(abs(target) * 0.01, 1e-9)
                passed = math.isclose(actual, target, abs_tol=tolerance, rel_tol=0)

        status = "PASS" if passed else "FAIL"
        return ConstraintResult(
            constraint_id=constraint.id,
            status=status,
            actual=actual,
            target=target,
            message=f"{constraint.metric} is {actual:.6g}; requirement {constraint.operator} {self._target_text(target)}: {status}.",
        )

    @staticmethod
    def _target_text(target: float | tuple[float, float]) -> str:
        if isinstance(target, tuple):
            return f"[{target[0]:.6g}, {target[1]:.6g}]"
        return f"{target:.6g}"
