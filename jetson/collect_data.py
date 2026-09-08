"""Interactive data recorder for the physical glove."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from config import BAUD_RATE, DATA_DIR, FEATURE_NAMES, SEQUENCE_LENGTH, SERIAL_PORT
from serial_reader import SensorSerialReader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect labeled glove sequences")
    parser.add_argument("--label", required=True, help="sign label, e.g. hello")
    parser.add_argument("--person", required=True, help="anonymous participant ID")
    parser.add_argument("--session", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--count", type=int, default=50, help="number of clips")
    parser.add_argument("--sequence-length", type=int, default=SEQUENCE_LENGTH)
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--baud", type=int, default=BAUD_RATE)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--countdown", type=float, default=2.0)
    parser.add_argument("--rest", type=float, default=1.0)
    return parser.parse_args()


def update_labels(data_dir: Path, label: str) -> None:
    path = data_dir / "labels.json"
    labels = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if label not in labels:
        labels.append(label)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(labels), ensure_ascii=False, indent=2), encoding="utf-8")


def collect_sequence(reader: SensorSerialReader, length: int) -> np.ndarray:
    samples = []
    while len(samples) < length:
        sample = reader.read()
        if sample is not None:
            samples.append(sample)
    return np.stack(samples).astype(np.float32)


def main() -> None:
    args = parse_args()
    if args.count <= 0 or args.sequence_length <= 0:
        raise ValueError("count and sequence-length must be positive")
    label_dir = args.data_dir / args.label
    label_dir.mkdir(parents=True, exist_ok=True)
    update_labels(args.data_dir, args.label)

    print(f"label={args.label}, person={args.person}, session={args.session}")
    print("각 샘플마다 준비 자세를 취하고 Enter를 누르세요. Ctrl+C로 중단합니다.")
    with SensorSerialReader(args.port, args.baud) as reader:
        index = 0
        while index < args.count:
            input(f"[{index + 1}/{args.count}] 준비되면 Enter: ")
            if args.countdown:
                print(f"{args.countdown:g}초 후 시작")
                time.sleep(args.countdown)
            print("동작 시작")
            sequence = collect_sequence(reader, args.sequence_length)
            accepted = input("정상 동작이었나요? [Y/n]: ").strip().lower()
            if accepted in {"n", "no", "아니오"}:
                print("폐기하고 같은 번호를 다시 수집합니다.")
                continue
            timestamp = datetime.now(timezone.utc).isoformat()
            filename = f"{args.person}_{args.session}_{index:04d}_{uuid.uuid4().hex[:8]}.npz"
            np.savez_compressed(
                label_dir / filename,
                sequence=sequence,
                label=np.asarray(args.label),
                person=np.asarray(args.person),
                session=np.asarray(args.session),
                recorded_at=np.asarray(timestamp),
                feature_names=np.asarray(FEATURE_NAMES),
            )
            print(f"저장: {filename}")
            index += 1
            if args.rest:
                time.sleep(args.rest)


if __name__ == "__main__":
    main()
