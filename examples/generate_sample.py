from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

C = 299792458.0
OMEGA_E = 7.2921151467e-5
ROOT = Path(__file__).resolve().parent
ACTUAL = np.array([-2148744.0, 4426641.0, 4044656.0])
INITIAL = ACTUAL + np.array([80.0, -60.0, 45.0])
CLOCK_BIAS = 1.2e-6
SATELLITE_CLOCK_BIAS = 10.0e-6
BASE = datetime(2024, 1, 1)
OBSERVATION = BASE + timedelta(seconds=3600)


def satellite_positions() -> np.ndarray:
    radius = 26_000_000.0
    directions = np.array([[1, 0, 0.5], [-1, 0, 0.5], [0, 1, -0.5], [0, -1, -0.5], [0.4, 0.4, 0.9]], dtype=float)
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    return ACTUAL + directions * radius


def earth_rotated(position: np.ndarray, travel_time: float) -> np.ndarray:
    angle = OMEGA_E * travel_time
    x, y, z = position
    return np.array([np.cos(angle) * x + np.sin(angle) * y, -np.sin(angle) * x + np.cos(angle) * y, z])


def rinex_header(label: str, content: str = "") -> str:
    return content.ljust(60) + label.ljust(20)


def write_sp3(positions: np.ndarray) -> None:
    start = OBSERVATION - timedelta(seconds=1350)
    lines = [
        f"#cP{start.year:4d}{start.month:3d}{start.day:3d}{start.hour:3d}{start.minute:3d} {float(start.second):11.7f} {8:7d}  0  0  GPS",
        "##  1  0.0  900 0.0 900.00000000000",
        "%c G  cc GPS ccc ccc ccc ccc ccc ccc ccc ccc                          ",
        "%f  1.25000000000  1.0250000000000  0.00000000000  1234.56789012345  ",
        "%i    0    0   12   18    0   0   0   0                        ",
        "+        5   G01  G02  G03  G04  G05  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0",
        "++        0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0    0",
        "/* Synthetic SP3-c sample                                        ",
    ]
    for index in range(8):
        epoch = start + timedelta(seconds=900 * index)
        lines.append(f"*  {epoch.year:4d}{epoch.month:3d}{epoch.day:3d}{epoch.hour:3d}{epoch.minute:3d} {float(epoch.second):11.7f}")
        for prn, position in enumerate(positions, start=1):
            coordinates = "".join(f"{coordinate / 1000.0:14.7f}" for coordinate in position)
            lines.append(f"PG{prn:02d}{coordinates}{SATELLITE_CLOCK_BIAS * 1_000_000:14.7f}")
    lines.append("%i    0    0    0    0    1    0    0    0   0                    ")
    (ROOT / "sample.sp3").write_text("\n".join(line[:80].ljust(80) for line in lines) + "\n", encoding="ascii")


def write_rinex(positions: np.ndarray) -> None:
    first_types = ["C1C", "L1C", "D1C", "S1C", "C1W", "L1W", "D1W", "S1W", "C2W", "L2W", "D2W", "S2W", "C2L"]
    all_types = first_types + ["L2L"]
    lines = [
        rinex_header("RINEX VERSION / TYPE", "     3.04           O                   G    "),
        rinex_header("PGM / RUN BY / DATE", "PYSAMPLE                              EXAMPLE"),
        rinex_header("COMMENT", "Synthetic two-epoch GPS example"),
        rinex_header("SYS / # / OBS TYPES", f"G {len(all_types):3d} " + "".join(f"{item:>4s}" for item in first_types)),
        rinex_header("SYS / # / OBS TYPES", "        " + "".join(f"{item:>4s}" for item in all_types[13:])),
        rinex_header("APPROX POSITION XYZ", f"{INITIAL[0]:14.3f}{INITIAL[1]:14.3f}{INITIAL[2]:14.3f}"),
        rinex_header("TIME OF FIRST OBS", f"  {OBSERVATION.year:4d}    {OBSERVATION.month:2d}    {OBSERVATION.day:2d}    {OBSERVATION.hour:2d}    {OBSERVATION.minute:2d}   {float(OBSERVATION.second):10.7f}     GPS"),
        rinex_header("RCV CLOCK OFFS APPL", "     0"),
        rinex_header("END OF HEADER"),
    ]
    for epoch_index in range(2):
        epoch = OBSERVATION + timedelta(seconds=30 * epoch_index)
        lines.append(f"> {epoch.year:4d} {epoch.month:2d} {epoch.day:2d} {epoch.hour:2d} {epoch.minute:2d} {float(epoch.second):11.7f}  0 {len(positions):3d}")
        for prn, position in enumerate(positions, start=1):
            travel = float(np.linalg.norm(position - ACTUAL)) / C
            rotated = earth_rotated(position, travel)
            pseudorange = float(np.linalg.norm(rotated - ACTUAL)) + C * (CLOCK_BIAS - SATELLITE_CLOCK_BIAS)
            fields = [f"{pseudorange:14.3f}  "] + [" " * 16] * 13
            lines.append(f"G{prn:02d}" + "".join(fields))
    lines = [line if len(line) >= 80 else line.ljust(80) for line in lines]
    (ROOT / "sample.rnx").write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    positions = satellite_positions()
    write_sp3(positions)
    write_rinex(positions)


if __name__ == "__main__":
    main()
