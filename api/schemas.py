"""Pydantic models for API request/response validation."""

from pydantic import BaseModel, Field


# ── Templates ─────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    sport: str = Field(..., examples=["Athletics"])
    test_type: str = Field(..., examples=["situp", "vertical_jump"])
    pass_criteria: dict = Field(
        ..., examples=[{"min_reps": 20}],
        description="Criteria dict, e.g. {'min_reps': 20} or {'min_height_cm': 40}",
    )


class TemplateResponse(BaseModel):
    id: str
    sport: str
    test_type: str
    pass_criteria: dict
    created_at: str
    locked: bool


# ── Athletes ──────────────────────────────────────────────────────────

class AthleteResponse(BaseModel):
    id: str
    name: str
    sport: str
    created_at: str


# ── Session ───────────────────────────────────────────────────────────

class SessionStart(BaseModel):
    test_type: str = Field(..., examples=["situp", "vertical_jump"])
    show_preview: bool = Field(False, description="If true, opens an OpenCV preview window on the server")


class SessionStatus(BaseModel):
    active: bool
    test_type: str | None = None
    rep_count: int | None = None
    jump_state: str | None = None
    jump_height_cm: float | None = None
    flight_time: float | None = None
    calibration_progress: float | None = None
    measurement_valid: bool | None = None


# ── Submissions ───────────────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    test_id: str
    athlete_id: str
    athlete_name: str
    result_value: float
    passed: bool


class SubmissionResponse(BaseModel):
    id: str
    test_id: str
    athlete_id: str
    athlete_name: str
    result_value: float
    passed: bool
    submitted_at: str
