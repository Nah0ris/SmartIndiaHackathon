# KIRTI — Camera-Based Fitness Assessment Prototype

**SIH PS25073 · SAI · Fitness & Sports**

Proof-of-concept for replacing manual fitness scoring at SAI KIRTI talent scouting
centres with computer vision. Athletes perform tests in front of a webcam; the
system counts reps / measures performance automatically via pose estimation.

## Supported Tests

| Test | Method |
|------|--------|
| **Sit-ups** | Tracks shoulder–hip–knee angle, counts reps via peak detection |
| **Vertical Jump** | Tracks hip Y-coordinate, measures flight time → `h = g·t²/8` |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server (seeds DB with 5 demo athletes on first run)
python run.py
```

Server runs at **http://localhost:8000**.  
API docs at **http://localhost:8000/docs** (Swagger UI).

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/templates` | Create a locked test template |
| `GET`  | `/api/templates` | List all templates |
| `GET`  | `/api/templates/{id}` | Get template by ID |
| `GET`  | `/api/athletes` | List all athletes |
| `GET`  | `/api/athletes/{id}` | Get athlete by ID |
| `POST` | `/api/session/start` | Start CV session (`situp` or `vertical_jump`) |
| `GET`  | `/api/session/frame` | Get latest annotated frame as base64 JPEG |
| `GET`  | `/api/session/status` | Poll rep count / jump state |
| `POST` | `/api/session/reset` | Reset engine for re-attempt |
| `POST` | `/api/session/stop` | Stop webcam + CV session |
| `POST` | `/api/submissions` | Record immutable result |
| `GET`  | `/api/submissions/{test_id}` | List submissions for a test |

## Seeded Athletes

| Name | Sport |
|------|-------|
| LeBron James | Basketball |
| Lionel Messi | Football |
| Sidharth Sivasankar | Athletics |
| Cristiano Ronaldo | Football |
| Lewis Hamilton | Motorsport |

## Architecture

```
Frontend (browser) ──REST──▶ FastAPI (api/) ──▶ CV Engine (engine/)
                                  │                   │
                                  ▼                   ▼
                             SQLite (db/)      MediaPipe + OpenCV
                                                  (webcam)
```

The frontend never touches MediaPipe or the webcam directly — it polls
`/api/session/status` for numbers and renders them.

## Threshold Tuning

The vertical jump engine has tunable parameters passed to `VerticalJump()`:

| Parameter | Default | Purpose |
|-----------|---------|--------|
| `takeoff_threshold` | 0.05 | How far below baseline (normalised coords) hip must drop to trigger takeoff. Increase if getting false takeoffs. |
| `landing_tolerance` | 0.02 | How close to baseline hip must return to count as landing. Increase for more lenient landing detection. |
| `calibration_frames` | 20 | Frames for baseline calibration. Increase for more stable baseline at cost of longer setup. |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Cannot open webcam" | Ensure no other app is using the camera. Try changing camera index in `_Session.start()`. |
| Model download fails | Delete `engine/pose_landmarker_lite.task` and restart — it will re-download. Check internet connectivity. |
| False takeoff triggers | Increase `takeoff_threshold` (e.g. 0.08). Ensure athlete stands still during calibration. |
| Jump height seems wrong | Check FPS is accurate (measured from webcam, not guessed). Bad FPS = wrong flight time = wrong height. |

## Deployment

### Local (Development)

```bash
pip install -r requirements.txt
python run.py
```

Server starts at **http://localhost:8000** with hot-reload disabled by default.  
Enable reload for dev: `set KIRTI_RELOAD=1` (Windows) or `export KIRTI_RELOAD=1` (Linux/Mac) before running.

### Local (Production)

```bash
pip install -r requirements.txt
set KIRTI_WORKERS=1
set KIRTI_PORT=8000
python run.py
```

> **Note:** Workers must stay at 1 because the CV session is in-process (shared memory). Multiple workers = multiple isolated sessions = broken state.

### Docker

```bash
# Build and run
docker compose up --build

# Or without compose
docker build -t kirti .
docker run -p 8000:8000 --device /dev/video0 kirti
```

> On Windows, Docker cannot pass through the webcam directly. Run natively on Windows or use WSL2 with USB passthrough.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `KIRTI_HOST` | `0.0.0.0` | Server bind address |
| `KIRTI_PORT` | `8000` | Server port |
| `KIRTI_WORKERS` | `1` | Uvicorn workers (keep at 1) |
| `KIRTI_RELOAD` | `0` | Hot reload (`1` to enable) |
| `KIRTI_CORS_ORIGINS` | `*` | Allowed origins (comma-separated) |

Copy `.env.example` to `.env` to set these persistently.

### Endpoints for Monitoring

| Path | Purpose |
|------|---------|
| `GET /` | API info + version |
| `GET /health` | Health check (returns `{"status": "ok"}`) |
| `GET /docs` | Swagger UI |
