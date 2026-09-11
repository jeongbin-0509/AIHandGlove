"""Create clearly marked synthetic idle-motion clips from real none samples."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate augmented none clips")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--total", type=int, default=200, help="Desired total number of none clips")
    parser.add_argument("--seed", type=int, default=20260911)
    return parser.parse_args()


def augment(sequence: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    length, features = sequence.shape
    # Small time shift and smooth interpolation emulate timing differences.
    shift = int(rng.integers(-4, 5))
    shifted = np.roll(sequence, shift, axis=0)
    source_x = np.arange(length, dtype=np.float32)
    speed = float(rng.uniform(0.90, 1.10))
    sample_x = np.clip((source_x - length / 2) * speed + length / 2, 0, length - 1)
    warped = np.stack([np.interp(sample_x, source_x, shifted[:, i]) for i in range(features)], axis=1)

    channel_std = np.maximum(sequence.std(axis=0, keepdims=True), 1.0)
    noise = rng.normal(0, 0.035, sequence.shape) * channel_std
    scale = rng.normal(1.0, 0.015, (1, features))
    drift = np.linspace(-1, 1, length)[:, None] * rng.normal(0, 0.025, (1, features)) * channel_std
    result = warped * scale + noise + drift
    # Flex channels are ESP32 ADC readings and must stay in their physical range.
    result[:, :5] = np.clip(result[:, :5], 0, 4095)
    return result.astype(np.float32)


def main() -> None:
    args = parse_args()
    none_dir = args.data_dir / "none"
    none_dir.mkdir(parents=True, exist_ok=True)
    for old in none_dir.glob("synthetic_none_*.npz"):
        old.unlink()

    real_paths = sorted(p for p in none_dir.glob("*.npz") if not p.name.startswith("synthetic_none_"))
    if not real_paths:
        raise RuntimeError("At least one real none sample is required")
    amount = max(0, args.total - len(real_paths))
    rng = np.random.default_rng(args.seed)

    for index in range(amount):
        source = real_paths[index % len(real_paths)]
        with np.load(source, allow_pickle=False) as sample:
            sequence = augment(sample["sequence"].astype(np.float32), rng)
            feature_names = sample["feature_names"] if "feature_names" in sample else np.asarray([])
        np.savez_compressed(
            none_dir / f"synthetic_none_{index:04d}.npz",
            sequence=sequence,
            label=np.asarray("none"),
            person=np.asarray("synthetic"),
            session=np.asarray(f"synthetic_none_v1_{index // 20:02d}"),
            recorded_at=np.asarray("synthetic"),
            feature_names=feature_names,
            review_status=np.asarray("synthetic"),
            synthetic=np.asarray(True),
            source_sample=np.asarray(source.name),
        )
    print(f"real={len(real_paths)} synthetic={amount} total={len(real_paths) + amount}")


if __name__ == "__main__":
    main()
