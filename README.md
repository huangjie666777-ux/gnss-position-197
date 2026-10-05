# GPS C1C Pseudorange Independent Check

Pure-backend FastAPI service for independently recomputing GPS receiver position and receiver clock bias from one uncompressed RINEX 3.04 observation file and one SP3-c position ephemeris.

## Scope

- GPS time and GPS satellites only; normal epochs (`0`) only.
- Uses the header-ordered GPS `C1C` field, including observation-type continuation records.
- Blank and zero pseudoranges are treated as missing.
- Unsupported formats, pre-applied receiver-clock correction, non-normal events, non-finite values, bad dates/identities, and truncation are rejected with file, line, and column where possible.
- SP3 coordinates are converted from kilometres to metres and clocks from microseconds to seconds; zero coordinates and missing clocks are detected.
- Transmit-time satellite positions use eight continuous 900 s nodes with Lagrange interpolation. Satellite clocks use adjacent-node linear interpolation without crossing missing values or extrapolation.
- Each epoch independently starts from the RINEX approximate position. At least four usable, full-rank satellites are required; failed epochs do not contaminate later epochs.
- Earth rotation during signal travel is compensated. No ionosphere, troposphere, relativistic, antenna, tide, multipath, or carrier-phase corrections are applied.
- At most 100 observation epochs are processed.

The reported RMS is the post-fit pseudorange residual RMS for that epoch, not a survey-grade accuracy guarantee. Geometry-only C1C results can be substantially affected by the omitted atmospheric and antenna effects.

## Run

```bash
.venv/bin/python examples/generate_sample.py
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Upload files:

```bash
curl -s http://127.0.0.1:8000/position \
  -F rinex_file=@examples/sample.rnx \
  -F sp3_file=@examples/sample.sp3 | python -m json.tool
```

Regenerate the synthetic two-epoch example at any time:

```bash
.venv/bin/python examples/generate_sample.py
```

## Validation

```bash
.venv/bin/python -m compileall app examples tests
.venv/bin/pytest -q
```

## Code Layout

- `app/parsers/rinex.py`: fixed-column RINEX 3.04 parsing and validation.
- `app/parsers/sp3.py`: SP3-c parsing, unit conversion, zero/missing data handling.
- `app/ephemeris.py`: eight-node Lagrange positions and linear satellite clocks.
- `app/positioning.py`: transmit-time iteration, Earth rotation, least squares, residuals, exclusion reasons.
- `app/coordinates.py`: ECEF to WGS84 latitude, longitude, and ellipsoidal height.
- `app/main.py`: HTTP upload endpoint and response schema.

