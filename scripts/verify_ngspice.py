#!/usr/bin/env python3
"""Prove that the local ngspice executable can simulate a voltage divider."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


NETLIST = """* 5 V voltage divider smoke test
V1 vin 0 DC 5
R1 vin out 1k
R2 out 0 1k
.control
op
print v(out)
quit
.endc
.end
"""
OUTPUT_PATTERN = re.compile(r"v\(out\)\s*=\s*([-+0-9.eE]+)", re.IGNORECASE)


def main() -> int:
    executable = os.environ.get("NGSPICE_BIN", "ngspice")
    resolved_executable = shutil.which(executable)
    if resolved_executable is None:
        print(f"ngspice: NOT FOUND ({executable})")
        return 1

    with tempfile.TemporaryDirectory(prefix="electronics-lab-ngspice-") as directory:
        workdir = Path(directory)
        netlist_path = workdir / "divider.cir"
        log_path = workdir / "ngspice.log"
        netlist_path.write_text(NETLIST, encoding="utf-8")

        try:
            completed = subprocess.run(
                [resolved_executable, "-b", "-o", str(log_path), str(netlist_path)],
                cwd=workdir,
                timeout=5,
                check=False,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            print("ngspice: TIMEOUT")
            return 1

        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        if completed.returncode != 0:
            print("ngspice: FAILED")
            print(log.strip() or completed.stderr.strip())
            return 1

    match = OUTPUT_PATTERN.search(log)
    if match is None:
        print("ngspice: FAILED (V(out) missing)")
        return 1

    output_voltage = float(match.group(1))
    print("ngspice: OK")
    print(f"divider output: {output_voltage:.3f} V")
    if abs(output_voltage - 2.5) > 0.01:
        print("FAIL")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

