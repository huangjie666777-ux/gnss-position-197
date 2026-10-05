from __future__ import annotations

import math

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    longitude = math.atan2(y, x)
    p = math.hypot(x, y)
    latitude = math.atan2(z, p * (1.0 - WGS84_E2)) if p else math.copysign(math.pi / 2.0, z)
    height = 0.0
    for _ in range(16):
        sin_latitude = math.sin(latitude)
        prime_vertical = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_latitude * sin_latitude)
        height = p / math.cos(latitude) - prime_vertical if p else abs(z) - WGS84_A * math.sqrt(1.0 - WGS84_E2)
        next_latitude = latitude if p == 0 else math.atan2(z, p * (1.0 - WGS84_E2 * prime_vertical / (prime_vertical + height)))
        if abs(next_latitude - latitude) < 1e-13:
            latitude = next_latitude
            break
        latitude = next_latitude
    return math.degrees(latitude), math.degrees(longitude), height

