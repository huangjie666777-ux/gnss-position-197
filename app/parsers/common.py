from __future__ import annotations

from datetime import datetime
import math


def fixed_float(text: str, *, file: str, line: int, column: int) -> float:
    value = text.strip()
    if not value:
        return math.nan
    try:
        number = float(value)
    except ValueError as exc:
        raise _error(f"non-numeric value {value!r}", file, line, column) from exc
    if not math.isfinite(number):
        raise _error(f"non-finite value {value!r}", file, line, column)
    return number


def fixed_int(text: str, *, file: str, line: int, column: int) -> int:
    value = text.strip()
    try:
        return int(value)
    except ValueError as exc:
        raise _error(f"non-integer value {value!r}", file, line, column) from exc


def require_slice(line: str, start: int, end: int, *, file: str, line_number: int, description: str) -> str:
    if len(line) < end:
        raise _error(
            f"truncated {description}: expected column {start + 1}..{end}, got {len(line)} characters",
            file,
            line_number,
            len(line) + 1,
        )
    return line[start:end]


def make_datetime(year: int, month: int, day: int, hour: int, minute: int, second: float, *, file: str, line: int):
    try:
        whole_second = int(second)
        return datetime(year, month, day, hour, minute, whole_second)
    except (ValueError, OverflowError) as exc:
        raise _error(f"invalid calendar date/time", file, line, 1) from exc


def epoch_seconds(dt: datetime, fractional_second: float = 0.0) -> float:
    from datetime import datetime as _dt

    start = _dt(2000, 1, 1)
    return (dt - start).total_seconds() + fractional_second


def _error(message: str, file: str, line: int, column: int):
    from ..errors import GNSSParseError

    return GNSSParseError(message, file=file, line=line, column=column)

