from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, File, HTTPException, UploadFile

from .ephemeris import Ephemeris
from .errors import GNSSParseError
from .parsers.rinex import parse_rinex
from .parsers.sp3 import parse_sp3
from .positioning import solve_epochs

app = FastAPI(title="Independent GPS Pseudorange Check", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/position")
async def position(rinex_file: UploadFile = File(...), sp3_file: UploadFile = File(...)):
    try:
        rinex_text = (await rinex_file.read()).decode("ascii")
        sp3_text = (await sp3_file.read()).decode("ascii")
        rinex = parse_rinex(rinex_text, rinex_file.filename or "observation.rnx", max_epochs=100)
        sp3 = parse_sp3(sp3_text, sp3_file.filename or "ephemeris.sp3")
        ephemeris = Ephemeris(sp3)
        epoch_results = solve_epochs(rinex, ephemeris)
    except (GNSSParseError, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "input_epochs": len(rinex.epochs),
        "epoch_limit": 100,
        "epochs": [asdict(result) for result in epoch_results],
        "corrections_applied": {
            "troposphere": False,
            "ionosphere": False,
            "carrier_phase": False,
            "receiver_clock": False,
            "earth_rotation": True,
        },
        "accuracy_boundary": "Geometry-only C1C single-point results exclude ionospheric, tropospheric, relativistic, antenna, multipath, tide, and carrier-phase corrections; RMS is observation fit RMS, not surveyed accuracy.",
    }

