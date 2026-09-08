"""Shared configuration for data collection, training and inference."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models"

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115_200
SERIAL_TIMEOUT = 1.0

SAMPLE_RATE_HZ = 20
SEQUENCE_LENGTH = 40  # 2 seconds at 20 Hz
FEATURE_NAMES = (
    "flex_thumb",
    "flex_index",
    "flex_middle",
    "flex_ring",
    "flex_little",
    "acc_x",
    "acc_y",
    "acc_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
)
NUM_FEATURES = len(FEATURE_NAMES)

DEFAULT_MODEL_PATH = MODEL_DIR / "sign_transformer.pt"
DEFAULT_CONFIDENCE_THRESHOLD = 0.70
DEFAULT_STABLE_WINDOWS = 3
