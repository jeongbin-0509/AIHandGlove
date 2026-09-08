"""Run continuous real-time sign inference from the glove."""

from __future__ import annotations

import argparse
import os
from collections import deque
from pathlib import Path

from config import (
    BAUD_RATE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MODEL_PATH,
    DEFAULT_STABLE_WINDOWS,
    SERIAL_PORT,
)
from inference import SignPredictor
from sequence_buffer import SequenceBuffer
from serial_reader import SensorSerialReader
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real-time sign recognition")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--baud", type=int, default=BAUD_RATE)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--stable-windows", type=int, default=DEFAULT_STABLE_WINDOWS)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--server-url", default=os.environ.get("GLOVE_API_URL", ""))
    parser.add_argument("--api-token", default=os.environ.get("JETSON_API_TOKEN", ""))
    return parser.parse_args()


def publish_prediction(server_url: str, token: str, label: str, confidence: float) -> None:
    if not server_url or not token:
        return
    try:
        response = requests.post(
            f"{server_url.rstrip('/')}/api/predictions",
            headers={"Authorization": f"Bearer {token}"},
            json={"label": label, "confidence": confidence},
            timeout=3,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"웹 전송 실패: {error}")


def main() -> None:
    args = parse_args()
    predictor = SignPredictor(args.model, args.device)
    buffer = SequenceBuffer(predictor.sequence_length, args.stride)
    recent: deque[str] = deque(maxlen=args.stable_windows)
    last_emitted: str | None = None

    print("수어 인식 시작 (Ctrl+C로 종료)")
    with SensorSerialReader(args.port, args.baud) as reader:
        for sample in reader.samples():
            buffer.append(sample)
            if not buffer.ready:
                continue
            label, confidence, _ = predictor.predict(buffer.pop_window())
            if confidence < args.threshold:
                recent.clear()
                last_emitted = None
                continue
            recent.append(label)
            if len(recent) == recent.maxlen and len(set(recent)) == 1 and label != last_emitted:
                print(f"인식: {label} ({confidence:.1%})")
                publish_prediction(args.server_url, args.api_token, label, confidence)
                last_emitted = label


if __name__ == "__main__":
    main()
