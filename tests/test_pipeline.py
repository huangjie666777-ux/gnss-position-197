from pathlib import Path

from fastapi.testclient import TestClient

from app.errors import GNSSParseError
from app.main import app
from app.parsers.rinex import parse_rinex
from app.parsers.sp3 import parse_sp3
from app.ephemeris import Ephemeris
from app.positioning import solve_epochs


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_pipeline():
    rinex = parse_rinex((ROOT / "examples/sample.rnx").read_text(), "sample.rnx")
    sp3 = parse_sp3((ROOT / "examples/sample.sp3").read_text(), "sample.sp3")
    results = solve_epochs(rinex, Ephemeris(sp3))
    assert len(results) == 2
    assert all(result.status == "ok" for result in results)
    assert all(result.used_satellites == [1, 2, 3, 4, 5] for result in results)
    assert all(result.rms < 0.001 for result in results)
    assert all(abs(result.x + 2148744.0) < 0.01 for result in results)
    assert all(abs(result.y - 4426641.0) < 0.01 for result in results)
    assert all(abs(result.z - 4044656.0) < 0.01 for result in results)
    assert all(abs(result.receiver_clock - 1.2e-6) < 1e-9 for result in results)


def test_truncation_error_has_location():
    text = (ROOT / "examples/sample.rnx").read_text().splitlines()[0][:10]
    try:
        parse_rinex(text + "\n", "bad.rnx")
    except GNSSParseError as exc:
        assert exc.line == 1
        assert exc.column == 11
    else:
        raise AssertionError("truncation must be rejected")


def test_http_position():
    with TestClient(app) as client:
        response = client.post(
            "/position",
            files={
                "rinex_file": ("sample.rnx", (ROOT / "examples/sample.rnx").read_bytes(), "application/octet-stream"),
                "sp3_file": ("sample.sp3", (ROOT / "examples/sample.sp3").read_bytes(), "application/octet-stream"),
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["input_epochs"] == 2
    assert data["epochs"][0]["status"] == "ok"

