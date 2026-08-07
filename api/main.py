"""FastAPI backend for the KIRTI fitness assessment prototype.

Exposes REST endpoints that the frontend consumes.  The CV engines
(situp counter, vertical jump) run in a background thread feeding off
the local webcam; the API just surfaces their current state.
"""

import base64
import os
import threading
import time
from contextlib import asynccontextmanager

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    AthleteResponse,
    SessionStart,
    SessionStatus,
    SubmissionCreate,
    SubmissionResponse,
    TemplateCreate,
    TemplateResponse,
)
from db.database import (
    create_submission,
    create_template,
    get_all_athletes,
    get_all_templates,
    get_athlete,
    get_submissions_for_test,
    get_template,
    init_db,
)
from engine.situp_counter import SitupCounter
from engine.vertical_jump import VerticalJump


# ======================================================================
# Session state (singleton — one webcam session at a time)
# ======================================================================

class _Session:
    """Mutable singleton holding the active CV session."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = False
        self.test_type: str | None = None
        self.engine: SitupCounter | VerticalJump | None = None
        self.cap: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.show_preview = False
        self._latest_frame = None

    def start(self, test_type: str, show_preview: bool = False) -> None:
        with self._lock:
            if self.active:
                raise RuntimeError("A session is already running — stop it first.")

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                raise RuntimeError("Cannot open webcam (index 0).")

            # Measure real FPS for the vertical-jump engine
            measured_fps = cap.get(cv2.CAP_PROP_FPS)
            if measured_fps <= 0:
                measured_fps = 30.0  # fallback

            if test_type == "situp":
                engine = SitupCounter()
            elif test_type == "vertical_jump":
                engine = VerticalJump(fps=measured_fps)
            else:
                cap.release()
                raise ValueError(f"Unknown test_type: {test_type}")

            self.active = True
            self.test_type = test_type
            self.engine = engine
            self.cap = cap
            self.show_preview = show_preview
            self._latest_frame = None
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        with self._lock:
            if self.cap:
                self.cap.release()
            cv2.destroyAllWindows()
            self.active = False
        # Keep engine alive so status can still be read after stop

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                break
            annotated = self.engine.process(frame)
            
            with self._lock:
                self._latest_frame = annotated

            if self.show_preview:
                cv2.imshow("KIRTI Assessment", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            else:
                time.sleep(0.01)
        # Auto-cleanup when loop exits naturally
        with self._lock:
            if self.cap and self.cap.isOpened():
                self.cap.release()
            cv2.destroyAllWindows()
            self.active = False


_session = _Session()


# ======================================================================
# App lifecycle
# ======================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    _session.stop()


app = FastAPI(
    title="KIRTI Fitness Assessment API",
    description="SIH PS25073 — Camera-based fitness testing prototype",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins = os.getenv("KIRTI_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================================
# Health / root
# ======================================================================

@app.get("/")
def api_root():
    return {
        "name": "KIRTI Fitness Assessment API",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
def api_health():
    return {"status": "ok"}


# ======================================================================
# Template endpoints
# ======================================================================

@app.post("/api/templates", response_model=TemplateResponse)
def api_create_template(body: TemplateCreate):
    return create_template(body.sport, body.test_type, body.pass_criteria)


@app.get("/api/templates", response_model=list[TemplateResponse])
def api_list_templates():
    return get_all_templates()


@app.get("/api/templates/{template_id}", response_model=TemplateResponse)
def api_get_template(template_id: str):
    t = get_template(template_id)
    if t is None:
        raise HTTPException(404, "Template not found")
    return t


# ======================================================================
# Athlete endpoints
# ======================================================================

@app.get("/api/athletes", response_model=list[AthleteResponse])
def api_list_athletes():
    return get_all_athletes()


@app.get("/api/athletes/{athlete_id}", response_model=AthleteResponse)
def api_get_athlete(athlete_id: str):
    a = get_athlete(athlete_id)
    if a is None:
        raise HTTPException(404, "Athlete not found")
    return a


# ======================================================================
# Session endpoints (CV engine control)
# ======================================================================

@app.post("/api/session/start")
def api_session_start(body: SessionStart):
    try:
        _session.start(body.test_type, show_preview=body.show_preview)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "started", "test_type": body.test_type, "show_preview": body.show_preview}


@app.post("/api/session/stop")
def api_session_stop():
    _session.stop()
    return {"status": "stopped"}


@app.get("/api/session/status", response_model=SessionStatus)
def api_session_status():
    with _session._lock:
        if not _session.engine:
            return SessionStatus(active=False)

        status = SessionStatus(active=_session.active, test_type=_session.test_type)

        if isinstance(_session.engine, SitupCounter):
            status.rep_count = _session.engine.get_count()
            status.calibration_progress = None
        elif isinstance(_session.engine, VerticalJump):
            status.jump_state = _session.engine.state.name
            status.jump_height_cm = _session.engine.jump_height_cm
            status.flight_time = getattr(_session.engine, 'flight_time', None)
            status.measurement_valid = getattr(_session.engine, 'measurement_valid', None)
            
            if _session.engine.state.name == "CALIBRATING":
                status.calibration_progress = min(1.0, len(_session.engine._calibration_ys) / _session.engine.calibration_frames)
            else:
                status.calibration_progress = 1.0

        return status


@app.post("/api/session/reset")
def api_session_reset():
    """Reset the current engine for another attempt without restarting the camera."""
    if not _session.engine:
        raise HTTPException(400, "No active session")
    _session.engine.reset()
    return {"status": "reset"}


@app.get("/api/session/frame")
def api_session_frame():
    if not _session.active or _session._latest_frame is None:
        raise HTTPException(404, "No active session or no frame available")
    with _session._lock:
        frame = _session._latest_frame.copy()
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return {"frame": base64.b64encode(buf).decode('ascii'), "format": "jpeg"}


# ======================================================================
# Submission endpoints
# ======================================================================

@app.post("/api/submissions", response_model=SubmissionResponse)
def api_create_submission(body: SubmissionCreate):
    # Validate template exists
    if get_template(body.test_id) is None:
        raise HTTPException(404, "Test template not found")
    # Validate athlete exists
    if get_athlete(body.athlete_id) is None:
        raise HTTPException(404, "Athlete not found")
    return create_submission(
        test_id=body.test_id,
        athlete_id=body.athlete_id,
        athlete_name=body.athlete_name,
        result_value=body.result_value,
        passed=body.passed,
    )


@app.get("/api/submissions/{test_id}", response_model=list[SubmissionResponse])
def api_get_submissions(test_id: str):
    return get_submissions_for_test(test_id)
