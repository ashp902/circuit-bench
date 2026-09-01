from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.ngspice
@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_ngspice_voltage_divider_spike() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/verify_ngspice.py"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "divider output: 2.500 V" in completed.stdout
    assert completed.stdout.rstrip().endswith("PASS")

