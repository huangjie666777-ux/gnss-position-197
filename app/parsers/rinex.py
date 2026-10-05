from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from .common import epoch_seconds, fixed_float, fixed_int, make_datetime, require_slice
from ..errors import GNSSParseError


@dataclass(frozen=True)
class Observation:
    prn: int
    c1c: float


@dataclass(frozen=True)
class EpochData:
    time: datetime
    second: float
    observations: tuple[Observation, ...]
    missing: tuple[int, ...]


@dataclass(frozen=True)
class RinexData:
    approximate_position: tuple[float, float, float]
    epochs: tuple[EpochData, ...]


def parse_rinex(text: str, filename: str, *, max_epochs: int = 100) -> RinexData:
    lines = text.splitlines()
    if not lines:
        raise GNSSParseError("empty RINEX observation file", file=filename, line=1, column=1)
    first = require_slice(lines[0], 0, 80, file=filename, line_number=1, description="RINEX header")
    version = fixed_float(first[0:9], file=filename, line=1, column=1)
    if abs(version - 3.04) > 1e-6:
        raise GNSSParseError(f"unsupported RINEX version {version:g}; only uncompressed RINEX 3.04 is supported", file=filename, line=1, column=1)
    if first[20:21].strip() != "O":
        raise GNSSParseError("unsupported RINEX file type; observation file required", file=filename, line=1, column=21)

    observation_types: dict[str, list[str]] = {}
    approximate: list[float] | None = None
    time_system: str | None = None
    clock_applied_line: int | None = None
    unsupported_correction_labels = {
        "IONOSPHERIC CORR",
        "TIME SYSTEM CORR",
        "SYS / DCBS APPLIED",
        "SYS / PCVS APPLIED",
        "SYS / SCALE OFST",
    }
    header_end_line = 0
    index = 0

    while index < len(lines):
        line_number = index + 1
        raw = lines[index]
        label = raw[60:80].strip() if len(raw) >= 60 else ""
        if label in unsupported_correction_labels:
            raise GNSSParseError(f"unsupported declared correction: {label}", file=filename, line=line_number, column=61)
        if label == "END OF HEADER":
            header_end_line = line_number
            break
        if label == "SYS / # / OBS TYPES":
            system = require_slice(raw, 0, 1, file=filename, line_number=line_number, description="satellite system")
            if not system:
                raise GNSSParseError("observation type continuation without an initial system", file=filename, line=line_number, column=1)
            count = fixed_int(require_slice(raw, 3, 6, file=filename, line_number=line_number, description="observation type count"), file=filename, line=line_number, column=4)
            if not 0 <= count <= 255:
                raise GNSSParseError("invalid observation type count", file=filename, line=line_number, column=4)
            types: list[str] = []
            while len(types) < count:
                current_number = index + 1
                current = lines[index]
                for local_index in range(min(13, count - len(types))):
                    start = 7 + local_index * 4
                    obs_type = require_slice(current, start, start + 4, file=filename, line_number=current_number, description="observation type").strip()
                    if not obs_type:
                        raise GNSSParseError("blank observation type", file=filename, line=current_number, column=start + 1)
                    types.append(obs_type)
                index += 1
                if len(types) < count:
                    if index >= len(lines) or lines[index][60:80].strip() != "SYS / # / OBS TYPES":
                        raise GNSSParseError("missing observation type header continuation", file=filename, line=current_number + 1, column=61)
                    continuation_system = require_slice(lines[index], 0, 1, file=filename, line_number=index + 1, description="satellite system")
                    if continuation_system.strip():
                        raise GNSSParseError("observation type continuation changed system", file=filename, line=index + 1, column=1)
            observation_types[system] = types
            continue
        if label == "APPROX POSITION XYZ":
            approximate = [
                fixed_float(require_slice(raw, 0, 14, file=filename, line_number=line_number, description="approximate X"), file=filename, line=line_number, column=1),
                fixed_float(require_slice(raw, 14, 28, file=filename, line_number=line_number, description="approximate Y"), file=filename, line=line_number, column=15),
                fixed_float(require_slice(raw, 28, 42, file=filename, line_number=line_number, description="approximate Z"), file=filename, line=line_number, column=29),
            ]
        elif label == "TIME OF FIRST OBS":
            time_system = require_slice(raw, 48, 52, file=filename, line_number=line_number, description="time system").strip()
        elif label == "RCV CLOCK OFFS APPL":
            if fixed_int(require_slice(raw, 0, 6, file=filename, line_number=line_number, description="receiver clock flag"), file=filename, line=line_number, column=1) != 0:
                clock_applied_line = line_number
        index += 1

    if not header_end_line:
        raise GNSSParseError("missing END OF HEADER", file=filename, line=len(lines), column=61)
    if time_system != "GPS":
        raise GNSSParseError(f"unsupported time system {time_system!r}; GPS is required", file=filename, line=1, column=49)
    gps_types = observation_types.get("G", [])
    if not gps_types:
        raise GNSSParseError("missing GPS SYS / # / OBS TYPES header", file=filename, line=1, column=1)
    if "C1C" not in gps_types:
        raise GNSSParseError("GPS C1C observation type is required", file=filename, line=1, column=8)
    if approximate is None or not all(math.isfinite(v) for v in approximate):
        raise GNSSParseError("finite APPROX POSITION XYZ is required", file=filename, line=1, column=1)
    if clock_applied_line is not None:
        raise GNSSParseError("receiver clock corrections must not be pre-applied", file=filename, line=clock_applied_line, column=1)

    c1c_index = gps_types.index("C1C")
    epochs: list[EpochData] = []
    index = header_end_line
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        line_number = index + 1
        line = lines[index]
        if require_slice(line, 0, 1, file=filename, line_number=line_number, description="epoch marker") != ">":
            raise GNSSParseError("unexpected data record marker", file=filename, line=line_number, column=1)
        year = fixed_int(require_slice(line, 2, 6, file=filename, line_number=line_number, description="year"), file=filename, line=line_number, column=3)
        month = fixed_int(require_slice(line, 7, 9, file=filename, line_number=line_number, description="month"), file=filename, line=line_number, column=8)
        day = fixed_int(require_slice(line, 10, 12, file=filename, line_number=line_number, description="day"), file=filename, line=line_number, column=11)
        hour = fixed_int(require_slice(line, 13, 15, file=filename, line_number=line_number, description="hour"), file=filename, line=line_number, column=14)
        minute = fixed_int(require_slice(line, 16, 18, file=filename, line_number=line_number, description="minute"), file=filename, line=line_number, column=17)
        second = fixed_float(require_slice(line, 19, 29, file=filename, line_number=line_number, description="second"), file=filename, line=line_number, column=20)
        if not 0 <= second < 61:
            raise GNSSParseError("invalid epoch second", file=filename, line=line_number, column=20)
        event_flag = fixed_int(require_slice(line, 32, 33, file=filename, line_number=line_number, description="epoch flag"), file=filename, line=line_number, column=33)
        if event_flag != 0:
            raise GNSSParseError(f"unsupported epoch event flag {event_flag}; only normal epochs are supported", file=filename, line=line_number, column=32)
        satellite_count = fixed_int(require_slice(line, 34, 37, file=filename, line_number=line_number, description="satellite count"), file=filename, line=line_number, column=35)
        if satellite_count <= 0:
            raise GNSSParseError("epoch contains no satellites", file=filename, line=line_number, column=33)
        dt = make_datetime(year, month, day, hour, minute, second, file=filename, line=line_number)
        index += 1
        observations: list[Observation] = []
        missing: list[int] = []
        seen: set[int] = set()
        for _ in range(satellite_count):
            if index >= len(lines):
                raise GNSSParseError("truncated satellite observation record", file=filename, line=line_number, column=1)
            sat_line_number = index + 1
            sat_line = lines[index]
            sat_id = require_slice(sat_line, 0, 3, file=filename, line_number=sat_line_number, description="satellite identifier")
            if sat_id[0] != "G":
                raise GNSSParseError(f"unsupported satellite {sat_id!r}; only GPS satellites are supported", file=filename, line=sat_line_number, column=1)
            prn = fixed_int(sat_id[1:3], file=filename, line=sat_line_number, column=2)
            if not 1 <= prn <= 32 or prn in seen:
                raise GNSSParseError(f"invalid or duplicate GPS satellite identity {sat_id!r}", file=filename, line=sat_line_number, column=2)
            seen.add(prn)
            field_start = 3 + c1c_index * 16
            value = fixed_float(require_slice(sat_line, field_start, field_start + 14, file=filename, line_number=sat_line_number, description="C1C pseudorange"), file=filename, line=sat_line_number, column=field_start + 1)
            if value > 0.0:
                observations.append(Observation(prn, value))
            else:
                missing.append(prn)
            index += 1
        if len(epochs) >= max_epochs:
            raise GNSSParseError(f"more than {max_epochs} epochs; limit is {max_epochs}", file=filename, line=line_number, column=1)
        epochs.append(EpochData(dt, epoch_seconds(dt, second - int(second)), tuple(observations), tuple(missing)))

    if not epochs:
        raise GNSSParseError("no normal observation epochs found", file=filename, line=1, column=1)
    return RinexData(tuple(approximate), tuple(epochs))
