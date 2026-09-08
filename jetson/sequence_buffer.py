"""Rolling window used by real-time inference."""

from collections import deque
from typing import Deque

import numpy as np

from config import NUM_FEATURES, SEQUENCE_LENGTH


class SequenceBuffer:
    def __init__(self, length: int = SEQUENCE_LENGTH, stride: int = 4) -> None:
        if length <= 0 or stride <= 0:
            raise ValueError("length and stride must be positive")
        self.length = length
        self.stride = stride
        self._samples: Deque[np.ndarray] = deque(maxlen=length)
        self._since_last_window = 0

    def clear(self) -> None:
        self._samples.clear()
        self._since_last_window = 0

    def append(self, sample: np.ndarray) -> None:
        sample = np.asarray(sample, dtype=np.float32)
        if sample.shape != (NUM_FEATURES,):
            raise ValueError(f"expected ({NUM_FEATURES},), got {sample.shape}")
        self._samples.append(sample)
        self._since_last_window += 1

    @property
    def ready(self) -> bool:
        return len(self._samples) == self.length and self._since_last_window >= self.stride

    def pop_window(self) -> np.ndarray:
        if not self.ready:
            raise RuntimeError("sequence is not ready")
        self._since_last_window = 0
        return np.stack(tuple(self._samples)).astype(np.float32, copy=False)
