"""Read and validate newline-delimited sensor JSON from the ESP32."""

from __future__ import annotations

import json
import time
from typing import Iterator, Optional

import numpy as np
import serial

from config import BAUD_RATE, NUM_FEATURES, SERIAL_PORT, SERIAL_TIMEOUT


class SensorSerialReader:
    def __init__(
        self,
        port: str = SERIAL_PORT,
        baud_rate: int = BAUD_RATE,
        timeout: float = SERIAL_TIMEOUT,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None

    def open(self) -> "SensorSerialReader":
        if self._serial is None or not self._serial.is_open:
            self._serial = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            time.sleep(2.0)  # ESP32 can reset when the serial port is opened.
            self._serial.reset_input_buffer()
        return self

    def close(self) -> None:
        if self._serial is not None and self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> "SensorSerialReader":
        return self.open()

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def parse_line(line: str) -> Optional[np.ndarray]:
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        try:
            if line.startswith("{"):
                payload = json.loads(line)
                values = payload["flex"] + payload["acc"] + payload["gyro"]
            else:
                entries = dict(item.split(":", 1) for item in line.split())
                keys = (
                    "thumb", "index", "middle", "ring", "little",
                    "accX", "accY", "accZ", "gyroX", "gyroY", "gyroZ",
                )
                values = [float(entries[key]) for key in keys]
            vector = np.asarray(values, dtype=np.float32)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
        if vector.shape != (NUM_FEATURES,) or not np.isfinite(vector).all():
            return None
        return vector

    def read(self) -> Optional[np.ndarray]:
        if self._serial is None:
            raise RuntimeError("Serial reader is not open")
        raw = self._serial.readline()
        if not raw:
            return None
        return self.parse_line(raw.decode("utf-8", errors="ignore"))

    def samples(self) -> Iterator[np.ndarray]:
        while True:
            sample = self.read()
            if sample is not None:
                yield sample
