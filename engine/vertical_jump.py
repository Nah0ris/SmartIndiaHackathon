"""Vertical jump height measurement using MediaPipe Pose estimation.

Measures jump height via flight-time projectile motion:
  h = (g * t^2) / 8

Tracks the athlete's average hip Y-coordinate through a 4-state state machine:
  CALIBRATING -> GROUNDED -> AIRBORNE -> DONE
"""

from enum import Enum, auto
import cv2
import numpy as np
import mediapipe as mp

from engine.model_utils import ensure_model_file

GRAVITY = 9.8  # m/s^2

LEFT_HIP = 23
RIGHT_HIP = 24

# Skeleton connections for visual overlay
POSE_CONNECTIONS = [
    (11, 12), (11, 23), (12, 24), (23, 24),
    (23, 25), (24, 26), (25, 27), (26, 28),
    (11, 13), (13, 15), (12, 14), (14, 16)
]


class JumpState(Enum):
    CALIBRATING = auto()
    GROUNDED = auto()
    AIRBORNE = auto()
    DONE = auto()


class VerticalJump:
    """Measure vertical jump height from a live video feed.

    Parameters
    ----------
    fps : float
        Frames per second of the video source. Must be measured from
        the actual capture device — **do not guess**.
    calibration_frames : int
        Number of frames to average during the CALIBRATING phase.
        The athlete must stand still during this window.
    takeoff_threshold : float
        How far *below* the baseline (in normalised image coords) the
        hip Y must drop to trigger takeoff. Smaller Y = higher up in image,
        so takeoff means ``hip_y < baseline - threshold``.
    landing_tolerance : float
        How close hip Y must return to the baseline to count as landing.
        Landing triggers when ``hip_y >= baseline - landing_tolerance``.
    """

    def __init__(
        self,
        fps: float = 30.0,
        calibration_frames: int = 20,
        takeoff_threshold: float = 0.05,
        landing_tolerance: float = 0.02,
    ):
        self.fps = fps
        self.calibration_frames = calibration_frames
        self.takeoff_threshold = takeoff_threshold
        self.landing_tolerance = landing_tolerance

        model_path = ensure_model_file()
        vision = mp.tasks.vision
        base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

        self._state = JumpState.CALIBRATING
        self._frame_idx = 0
        self._calibration_ys: list[float] = []
        self._baseline_y: float = 0.0
        self._takeoff_frame: int = 0
        self._landing_frame: int = 0
        self._jump_height_cm: float | None = None
        self._takeoff_confirm_count: int = 0
        self._landing_confirm_count: int = 0
        self._smooth_buffer: list[float] = []
        self._flight_time: float | None = None
        self._measurement_valid: bool | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> JumpState:
        return self._state

    @property
    def jump_height_cm(self) -> float | None:
        return self._jump_height_cm

    @property
    def flight_time(self) -> float | None:
        return self._flight_time

    @property
    def measurement_valid(self) -> bool | None:
        return self._measurement_valid

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Process one BGR frame: detect pose, advance state machine,
        draw overlays, and return the annotated frame."""
        self._frame_idx += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self._landmarker.detect(mp_image)
        annotated = frame.copy()
        h, w, _ = frame.shape

        hip_y: float | None = None

        if results.pose_landmarks and len(results.pose_landmarks) > 0:
            landmarks = results.pose_landmarks[0]

            # Draw skeleton
            points = {}
            for idx, lm in enumerate(landmarks):
                cx, cy = int(lm.x * w), int(lm.y * h)
                points[idx] = (cx, cy)
                cv2.circle(annotated, (cx, cy), 4, (0, 255, 0), -1)

            for p1, p2 in POSE_CONNECTIONS:
                if p1 in points and p2 in points:
                    cv2.line(annotated, points[p1], points[p2], (255, 200, 0), 2)

            if landmarks[LEFT_HIP].visibility >= 0.5 and landmarks[RIGHT_HIP].visibility >= 0.5:
                # Average LEFT_HIP (23) and RIGHT_HIP (24) for stability
                hip_y = (landmarks[LEFT_HIP].y + landmarks[RIGHT_HIP].y) / 2.0
            else:
                hip_y = None

        # ---- State machine ------------------------------------------
        if hip_y is not None:
            self._advance(hip_y)

        # ---- HUD overlay --------------------------------------------
        self._draw_hud(annotated, hip_y)
        return annotated

    def reset(self) -> None:
        """Reset for another jump attempt."""
        self._state = JumpState.CALIBRATING
        self._frame_idx = 0
        self._calibration_ys.clear()
        self._baseline_y = 0.0
        self._takeoff_frame = 0
        self._landing_frame = 0
        self._jump_height_cm = None
        self._takeoff_confirm_count = 0
        self._landing_confirm_count = 0
        self._smooth_buffer.clear()
        self._flight_time = None
        self._measurement_valid = None

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _advance(self, hip_y: float) -> None:
        self._smooth_buffer.append(hip_y)
        if len(self._smooth_buffer) > 3:
            self._smooth_buffer.pop(0)
        smoothed_hip_y = float(np.mean(self._smooth_buffer))

        if self._state == JumpState.CALIBRATING:
            self._calibration_ys.append(smoothed_hip_y)
            if len(self._calibration_ys) >= self.calibration_frames:
                self._baseline_y = float(np.median(self._calibration_ys))
                self._state = JumpState.GROUNDED

        elif self._state == JumpState.GROUNDED:
            # Takeoff: hip rises above baseline by threshold
            # (smaller Y = higher in image coords)
            if smoothed_hip_y < self._baseline_y - self.takeoff_threshold:
                self._takeoff_confirm_count += 1
                if self._takeoff_confirm_count >= 3:
                    self._takeoff_frame = self._frame_idx
                    self._state = JumpState.AIRBORNE
                    self._takeoff_confirm_count = 0
            else:
                self._takeoff_confirm_count = 0

        elif self._state == JumpState.AIRBORNE:
            # Landing: hip returns near baseline
            if smoothed_hip_y >= self._baseline_y - self.landing_tolerance:
                self._landing_confirm_count += 1
                if self._landing_confirm_count >= 2:
                    self._landing_frame = self._frame_idx
                    self._compute_height()
                    self._state = JumpState.DONE
                    self._landing_confirm_count = 0
            else:
                self._landing_confirm_count = 0

        # DONE — no transitions, height is locked.

    def _compute_height(self) -> None:
        flight_time = (self._landing_frame - self._takeoff_frame) / self.fps
        if flight_time > 1.5:
            flight_time = 1.5
            self._measurement_valid = False
        else:
            self._measurement_valid = True
            
        self._flight_time = flight_time
        # h = g * t^2 / 8 (projectile motion, symmetric flight)
        self._jump_height_cm = round((GRAVITY * (flight_time ** 2) / 8) * 100, 1)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_hud(self, frame: np.ndarray, hip_y: float | None) -> None:
        state_colors = {
            JumpState.CALIBRATING: (255, 200, 0),   # cyan/yellow
            JumpState.GROUNDED: (0, 255, 255),       # yellow
            JumpState.AIRBORNE: (0, 165, 255),       # orange
            JumpState.DONE: (0, 255, 0),             # green
        }
        color = state_colors[self._state]
        label = self._state.name

        cv2.putText(frame, f"State: {label}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        if hip_y is not None:
            cv2.putText(frame, f"Hip Y: {hip_y:.4f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        if self._state == JumpState.CALIBRATING:
            progress = len(self._calibration_ys)
            cv2.putText(frame, f"Calibrating... {progress}/{self.calibration_frames}",
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)
        elif self._state == JumpState.GROUNDED:
            cv2.putText(frame, "Stand still, then JUMP!",
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        elif self._state == JumpState.DONE and self._jump_height_cm is not None:
            cv2.putText(frame, f"Jump Height: {self._jump_height_cm} cm",
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            if self._flight_time is not None:
                cv2.putText(frame, f"Flight Time: {self._flight_time:.2f} s",
                            (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            if self._measurement_valid is False:
                cv2.putText(frame, "MEASUREMENT CAPPED",
                            (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                            
        if self._state != JumpState.CALIBRATING and self._baseline_y > 0.0:
            h, w, _ = frame.shape
            baseline_pixel_y = int(self._baseline_y * h)
            cv2.line(frame, (0, baseline_pixel_y), (w, baseline_pixel_y), (0, 0, 255), 1)
