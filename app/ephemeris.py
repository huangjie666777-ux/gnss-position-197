from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .parsers.sp3 import SP3Data


@dataclass(frozen=True)
class SatelliteState:
    position: np.ndarray
    clock: float


class Ephemeris:
    def __init__(self, sp3: SP3Data):
        self.times = np.array([epoch.second for epoch in sp3.epochs], dtype=float)
        self.epochs = sp3.epochs
        if len(self.times) >= 2:
            diffs = np.diff(self.times)
            if not np.allclose(diffs, 900.0, atol=1e-6):
                raise ValueError("SP3 nodes must be continuous 900 s GPS ephemeris nodes")

    def state_at(self, prn: int, transmit_time: float) -> SatelliteState:
        if len(self.times) < 8:
            raise ValueError("fewer than 8 SP3 nodes")
        if transmit_time < self.times[0] or transmit_time > self.times[-1]:
            raise ValueError("transmit time is outside SP3 interval")
        insertion = int(np.searchsorted(self.times, transmit_time, side="left"))
        start = min(max(insertion - 4, 0), len(self.times) - 8)
        stop = start + 8
        node_times = self.times[start:stop]
        positions: list[np.ndarray] = []
        for epoch in self.epochs[start:stop]:
            pos = epoch.positions.get(prn)
            if pos is None or any(not math.isfinite(v) for v in pos):
                raise ValueError("position missing or zero at interpolation node")
            positions.append(np.array(pos, dtype=float))
        position = _lagrange(node_times, np.vstack(positions), transmit_time)

        right = int(np.searchsorted(self.times, transmit_time, side="right"))
        left = right - 1
        if left < 0:
            left, right = 0, 1
        if right >= len(self.times):
            left, right = len(self.times) - 2, len(self.times) - 1
        if left < 0 or right >= len(self.times) or left == right:
            raise ValueError("cannot bracket transmit time for clock interpolation")
        clock_left = self.epochs[left].clocks.get(prn, math.nan)
        clock_right = self.epochs[right].clocks.get(prn, math.nan)
        if not math.isfinite(clock_left) or not math.isfinite(clock_right):
            raise ValueError("cannot linearly interpolate across missing satellite clock")
        fraction = (transmit_time - self.times[left]) / (self.times[right] - self.times[left])
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("satellite clock interpolation would extrapolate")
        clock = clock_left + fraction * (clock_right - clock_left)
        return SatelliteState(position, clock)


def _lagrange(times: np.ndarray, values: np.ndarray, target: float) -> np.ndarray:
    result = np.zeros(values.shape[1], dtype=float)
    for i, ti in enumerate(times):
        basis = 1.0
        for j, tj in enumerate(times):
            if i != j:
                basis *= (target - tj) / (ti - tj)
        result += basis * values[i]
    if not np.all(np.isfinite(result)):
        raise ValueError("non-finite Lagrange interpolation result")
    return result
