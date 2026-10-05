from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .coordinates import ecef_to_geodetic
from .ephemeris import Ephemeris
from .parsers.rinex import RinexData

SPEED_OF_LIGHT = 299792458.0
EARTH_ROTATION = 7.2921151467e-5


@dataclass
class SatelliteResult:
    prn: int
    used: bool
    residual: float | None = None
    reason: str | None = None


@dataclass
class EpochResult:
    time: str
    status: str
    x: float | None = None
    y: float | None = None
    z: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    height: float | None = None
    receiver_clock: float | None = None
    used_satellites: list[int] | None = None
    excluded_satellites: list[SatelliteResult] | None = None
    residuals: dict[str, float] | None = None
    rms: float | None = None
    reason: str | None = None


def solve_epochs(rinex: RinexData, ephemeris: Ephemeris) -> list[EpochResult]:
    return [_solve_epoch(epoch, ephemeris, rinex.approximate_position) for epoch in rinex.epochs]


def _solve_epoch(epoch, ephemeris: Ephemeris, initial_position: tuple[float, float, float]) -> EpochResult:
    result = EpochResult(time=epoch.time.isoformat() + "Z", status="rejected")
    excluded = [SatelliteResult(prn, False, reason="C1C is blank, zero, or otherwise missing") for prn in epoch.missing]
    pseudoranges = {obs.prn: obs.c1c for obs in epoch.observations}
    states = {}
    receiver = np.array(initial_position, dtype=float)
    receiver_clock = 0.0

    for prn, pseudorange in list(pseudoranges.items()):
        try:
            states[prn] = ephemeris.state_at(prn, epoch.second - pseudorange / SPEED_OF_LIGHT)
        except ValueError as exc:
            pseudoranges.pop(prn)
            excluded.append(SatelliteResult(prn, False, reason=str(exc)))

    def geometry(state):
        travel = max(0.0, float(np.linalg.norm(state.position - receiver)) / SPEED_OF_LIGHT)
        angle = EARTH_ROTATION * travel
        x, y = state.position[0], state.position[1]
        rotated = np.array([math.cos(angle) * x + math.sin(angle) * y, -math.sin(angle) * x + math.cos(angle) * y, state.position[2]])
        delta = receiver - rotated
        distance = float(np.linalg.norm(delta))
        return rotated, delta / distance, distance

    for _ in range(20):
        design_rows = []
        observed_minus_computed = []
        active = []
        for prn, pseudorange in list(pseudoranges.items()):
            try:
                transmit_time = epoch.second - pseudorange / SPEED_OF_LIGHT - states[prn].clock
                state = ephemeris.state_at(prn, transmit_time)
                states[prn] = state
                _, unit, geometric_range = geometry(state)
            except ValueError as exc:
                pseudoranges.pop(prn)
                excluded.append(SatelliteResult(prn, False, reason=str(exc)))
                continue
            predicted = geometric_range + SPEED_OF_LIGHT * (receiver_clock - state.clock)
            design_rows.append(np.array([unit[0], unit[1], unit[2], 1.0]))
            observed_minus_computed.append(pseudorange - predicted)
            active.append(prn)

        if len(active) < 4:
            result.reason = f"only {len(active)} valid satellites; at least four are required"
            result.excluded_satellites = excluded
            return result
        design = np.vstack(design_rows)
        if np.linalg.matrix_rank(design) < 4:
            result.reason = "satellite geometry is rank deficient"
            result.used_satellites = active
            result.excluded_satellites = excluded
            return result
        correction, *_ = np.linalg.lstsq(design, np.array(observed_minus_computed), rcond=None)
        receiver += correction[:3]
        receiver_clock += float(correction[3]) / SPEED_OF_LIGHT
        if float(np.linalg.norm(correction[:3])) < 1e-5 and abs(float(correction[3])) < 1e-5:
            break
    else:
        result.reason = "least-squares iteration did not converge in 20 iterations"
        result.excluded_satellites = excluded
        return result

    residuals = {}
    for prn in active:
        state = states[prn]
        _, _, geometric_range = geometry(state)
        predicted = geometric_range + SPEED_OF_LIGHT * (receiver_clock - state.clock)
        residuals[f"G{prn:02d}"] = float(pseudoranges[prn] - predicted)
    rms = math.sqrt(sum(value * value for value in residuals.values()) / len(residuals))
    latitude, longitude, height = ecef_to_geodetic(*receiver.tolist())
    result.status = "ok"
    result.x, result.y, result.z = map(float, receiver)
    result.latitude, result.longitude, result.height = latitude, longitude, height
    result.receiver_clock = receiver_clock
    result.used_satellites = active
    result.excluded_satellites = excluded
    result.residuals = residuals
    result.rms = rms
    return result
