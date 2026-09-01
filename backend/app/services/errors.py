from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CircuitError(Exception):
    code: str
    message: str
    recovery_hint: str | None = None

