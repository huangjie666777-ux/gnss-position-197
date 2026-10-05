from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from .common import fixed_float, fixed_int, make_datetime
from ..errors import GNSSParseError


@dataclass(frozen=True)
class SP3Epoch:
    time: datetime
    second: float
    positions: dict[int, tuple[float, float, float]]
    clocks: dict[int, float]


@dataclass(frozen=True)
class SP3Data:
    epochs: tuple[SP3Epoch, ...]


def parse_sp3(text: str, filename: str) -> SP3Data:
    lines = text.splitlines()
    if len(lines) < 2:
        raise GNSSParseError("empty SP3 file", file=filename, line=max(1, len(lines)), column=1)
    if not lines[0].startswith("#cP"):
        raise GNSSParseError("unsupported SP3 format; only position-mode SP3-c is supported", file=filename, line=1, column=1)

    epochs: list[SP3Epoch] = []
    current: SP3Epoch | None = None
    seen_satellites: set[int] = set()
    expected_epochs = fixed_int(lines[0][32:39], file=filename, line=1, column=33) if len(lines[0]) >= 39 else None

    for line_number0, raw in enumerate(lines[1:], start=2):
        record = raw[0:1]
        if record == "*":
            if len(raw) < 31:
                raise GNSSParseError(f"truncated SP3 epoch record: expected 31 columns, got {len(raw)}", file=filename, line=line_number0, column=len(raw) + 1)
            if current is not None:
                epochs.append(current)
            year = fixed_int(raw[2:7].strip() or " ", file=filename, line=line_number0, column=3)
            month = fixed_int(raw[8:11].strip(), file=filename, line=line_number0, column=9)
            day = fixed_int(raw[12:15].strip(), file=filename, line=line_number0, column=13)
            hour = fixed_int(raw[14:17].strip(), file=filename, line=line_number0, column=15)
            minute = fixed_int(raw[17:20].strip(), file=filename, line=line_number0, column=18)
            second = fixed_float(raw[20:31], file=filename, line=line_number0, column=21)
            dt = make_datetime(year, month, day, hour, minute, second, file=filename, line=line_number0)
            from .common import epoch_seconds

            current = SP3Epoch(dt, epoch_seconds(dt, second - int(second)), {}, {})
            seen_satellites = set()
        elif record == "P":
            if current is None:
                raise GNSSParseError("position record outside an SP3 epoch", file=filename, line=line_number0, column=1)
            if len(raw) < 60:
                raise GNSSParseError(f"truncated SP3 position record: expected 60 columns, got {len(raw)}", file=filename, line=line_number0, column=len(raw) + 1)
            sat = raw[1:4]
            if sat[0] != "G":
                continue
            prn = fixed_int(sat[1:3], file=filename, line=line_number0, column=2)
            if not 1 <= prn <= 32 or prn in seen_satellites:
                raise GNSSParseError(f"invalid or duplicate GPS satellite identity {sat!r}", file=filename, line=line_number0, column=2)
            seen_satellites.add(prn)
            values = [
                fixed_float(raw[start:start + 14], file=filename, line=line_number0, column=start + 1) * 1000.0
                for start in (4, 18, 32)
            ]
            if any(not math.isfinite(v) for v in values):
                raise GNSSParseError("non-finite SP3 coordinate", file=filename, line=line_number0, column=5)
            if all(v == 0.0 for v in values):
                current.positions[prn] = (math.nan, math.nan, math.nan)
            else:
                current.positions[prn] = tuple(values)  # type: ignore[assignment]
            clock = fixed_float(raw[46:60], file=filename, line=line_number0, column=47) * 1e-6
            current.clocks[prn] = clock if abs(clock) < 0.9 else math.nan
        elif record in {"+", "%", "/", "*", "#", "E"} or not raw.strip():
            continue
        elif record == "V":
            raise GNSSParseError("SP3 velocity records are not supported; position-mode P records are required", file=filename, line=line_number0, column=1)
        else:
            raise GNSSParseError(f"unsupported SP3 record {record!r}; only GPS P records are used", file=filename, line=line_number0, column=1)

    if current is not None:
        epochs.append(current)
    if not epochs:
        raise GNSSParseError("no SP3 epochs found", file=filename, line=1, column=1)
    if expected_epochs is not None and expected_epochs != len(epochs):
        raise GNSSParseError(f"SP3 header declares {expected_epochs} epochs but file contains {len(epochs)}", file=filename, line=1, column=33)
    times = [epoch.second for epoch in epochs]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise GNSSParseError("SP3 epochs must be strictly increasing", file=filename, line=1, column=1)
    return SP3Data(tuple(epochs))
