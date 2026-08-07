"""Sit-up repetition counter using MediaPipe PoseLandmarker API.

Counts sit-ups by tracking the torso-thigh angle (shoulder -> hip -> knee)
and detecting completed reps via peak detection on the angle signal.
"""

import cv2
import numpy as np
import mediapipe as mp
from scipy.signal import find_peaks

from engine.model_utils import ensure_model_file

# Pose landmark indices
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26

# Skeleton connections for visual overlay
POSE_CONNECTIONS = [
    (11, 12), (11, 23), (12, 24), (23, 24),
    (23, 25), (24, 26), (25, 27), (26, 28),
    (11, 13), (13, 15), (12, 14), (14, 16)
]


def _angle_between(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Compute the angle at point b formed by segments ba and bc, in degrees."""
    ba = a - b
    bc = c - b
    cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


class SitupCounter:
    """Counts sit-up reps from a live video feed using pose estimation.

    Parameters
    ----------
    min_angle : float
        Angle (degrees) at the crunch position (smallest torso-thigh angle).
    max_angle : float
        Angle (degrees) at the lying-flat position.
    peak_prominence : float
        Minimum prominence for scipy peak detection on the *inverted* angle signal.
    peak_distance : int
        Minimum number of frames between two detected peaks.
    """

    def __init__(
        self,
        min_angle: float = 55.0,
        max_angle: float = 160.0,
        peak_prominence: float = 20.0,
        peak_distance: int = 15,
    ):
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.peak_prominence = peak_prominence
        self.peak_distance = peak_distance

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

        self._angle_history: list[float] = []
        self._count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Run pose detection on *frame*, update rep count, return annotated frame."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self._landmarker.detect(mp_image)
        annotated = frame.copy()
        h, w, _ = frame.shape

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

            # Use LEFT side landmarks (indices 11=shoulder, 23=hip, 25=knee)
            left_shoulder = np.array([landmarks[LEFT_SHOULDER].x, landmarks[LEFT_SHOULDER].y])
            left_hip = np.array([landmarks[LEFT_HIP].x, landmarks[LEFT_HIP].y])
            left_knee = np.array([landmarks[LEFT_KNEE].x, landmarks[LEFT_KNEE].y])

            # Use RIGHT side landmarks
            right_shoulder = np.array([landmarks[RIGHT_SHOULDER].x, landmarks[RIGHT_SHOULDER].y])
            right_hip = np.array([landmarks[RIGHT_HIP].x, landmarks[RIGHT_HIP].y])
            right_knee = np.array([landmarks[RIGHT_KNEE].x, landmarks[RIGHT_KNEE].y])

            left_angle = _angle_between(left_shoulder, left_hip, left_knee)
            right_angle = _angle_between(right_shoulder, right_hip, right_knee)
            angle = (left_angle + right_angle) / 2.0
            self._angle_history.append(angle)
            self._update_count()

            # Visual feedback
            is_up = angle < self.min_angle + 20
            color = (0, 255, 0) if is_up else (0, 165, 255)
            state_text = "UP" if is_up else "DOWN"
            
            cv2.putText(
                annotated,
                f"Torso-Thigh Angle: {angle:.1f} deg | State: {state_text}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
            )

        # Rep count (always shown)
        cv2.putText(
            annotated,
            f"Sit-up Reps: {self._count}",
            (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
        )
        return annotated

    def get_count(self) -> int:
        """Return the current rep count."""
        return self._count

    def reset(self) -> None:
        """Reset counter and angle history for a new attempt."""
        self._angle_history.clear()
        self._count = 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _update_count(self) -> None:
        """Re-derive count from the full angle history via peak detection."""
        if len(self._angle_history) < self.peak_distance + 1:
            return
        # Invert so that crunches (low angle) become peaks
        inverted = -np.array(self._angle_history)
        peaks, _ = find_peaks(
            inverted,
            prominence=self.peak_prominence,
            distance=self.peak_distance,
        )
        self._count = len(peaks)
