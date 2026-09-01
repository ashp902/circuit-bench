#!/usr/bin/env python3
"""Run reproducible ngspice checks for the passive anti-aliasing filter."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from itertools import product
from pathlib import Path


R1 = 1_000.0
R2 = 100_000.0
C1_NOMINAL = 68e-9
C2_NOMINAL = 1e-9
C1_VALUES = [61.2e-9, 64.6e-9, 68e-9, 71.4e-9, 74.8e-9]
C2_VALUES = [0.9e-9, 0.95e-9, 1e-9, 1.05e-9, 1.1e-9]
GAIN_PATTERN = re.compile(r"vdb\(vout\)\s*=\s*([-+0-9.eE]+)", re.IGNORECASE)


def netlist(c1: float, c2: float) -> str:
    return f"""* Passive two-pole anti-aliasing low-pass filter
V1 vin 0 AC 1
R1 vin n2 {R1}
C1 n2 0 {c1}
R2 n2 vout {R2}
C2 vout 0 {c2}
.control
ac lin 1 500 500
print vdb(vout)
ac lin 1 10000 10000
print vdb(vout)
quit
.endc
.end
"""


def simulate(executable: str, c1: float, c2: float) -> tuple[float, float]:
    with tempfile.TemporaryDirectory(prefix="passive-filter-") as tmp:
        folder = Path(tmp)
        circuit = folder / "filter.cir"
        log = folder / "ngspice.log"
        circuit.write_text(netlist(c1, c2), encoding="utf-8")
        result = subprocess.run([executable, "-b", "-o", str(log), str(circuit)], check=False, timeout=10, text=True, capture_output=True)
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else result.stderr
    values = [float(value) for value in GAIN_PATTERN.findall(text)]
    if result.returncode or len(values) != 2:
        raise RuntimeError(f"ngspice failed for C1={c1}, C2={c2}: {text[-1000:]}")
    return values[0], values[1]


def main() -> int:
    executable = shutil.which("ngspice")
    if executable is None:
        print("ngspice not found", file=sys.stderr)
        return 1
    rows = [(c1, c2, *simulate(executable, c1, c2)) for c1, c2 in product(C1_VALUES, C2_VALUES)]
    nominal_500, nominal_10k = simulate(executable, C1_NOMINAL, C2_NOMINAL)
    min_500 = min(row[2] for row in rows)
    max_10k = max(row[3] for row in rows)
    print(f"NOMINAL 500_HZ_DB={nominal_500:.6f} 10_KHZ_DB={nominal_10k:.6f}")
    print(f"SWEEP 500_HZ_MIN_DB={min_500:.6f} 10_KHZ_MAX_DB={max_10k:.6f} COMBINATIONS={len(rows)}")
    for c1, c2, gain_500, gain_10k in rows:
        print(f"C1={c1 * 1e9:4.1f}nF C2={c2 * 1e9:4.2f}nF G500={gain_500:.6f}dB G10K={gain_10k:.6f}dB")
    return 0 if min_500 >= -0.75 and max_10k <= -25 else 2


if __name__ == "__main__":
    raise SystemExit(main())
