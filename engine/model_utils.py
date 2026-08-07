"""Utility to ensure MediaPipe PoseLandmarker model bundle is downloaded."""

from pathlib import Path
import urllib.request

MODEL_PATH = Path(__file__).resolve().parent / "pose_landmarker_lite.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


def ensure_model_file() -> str:
    """Return absolute path to pose_landmarker_lite.task, downloading if missing or too small."""
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size <= 1_000_000:
        print(f"Model file at {MODEL_PATH} is too small. Deleting and re-downloading...")
        MODEL_PATH.unlink()

    if not MODEL_PATH.exists():
        print(f"Downloading pose_landmarker_lite.task model to {MODEL_PATH}...")
        try:
            urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))
        except Exception as e:
            print(f"Error downloading model: {e}")
            raise
            
        if not MODEL_PATH.exists() or MODEL_PATH.stat().st_size <= 1_000_000:
            raise RuntimeError("Downloaded model file is missing or too small (< 1 MB).")
            
        print("Model download complete.")
    return str(MODEL_PATH)
