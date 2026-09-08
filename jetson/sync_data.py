"""Download approved web samples from Render and save training NPZ files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

from config import DATA_DIR, FEATURE_NAMES, NUM_FEATURES, SEQUENCE_LENGTH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync approved glove samples")
    parser.add_argument("--api-url", default=os.environ.get("GLOVE_API_URL"))
    parser.add_argument("--token", default=os.environ.get("JETSON_API_TOKEN"))
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.api_url or not args.token:
        raise ValueError("GLOVE_API_URL and JETSON_API_TOKEN are required")

    request = Request(
        f"{args.api_url.rstrip('/')}/api/training-data",
        headers={"Authorization": f"Bearer {args.token}"},
    )
    with urlopen(request, timeout=60) as response:
        samples = json.load(response)["samples"]

    saved = skipped = 0
    for sample in samples:
        sequence = np.asarray(sample["sequence"], dtype=np.float32)
        if sequence.shape != (SEQUENCE_LENGTH, NUM_FEATURES):
            skipped += 1
            continue
        label_dir = args.data_dir / sample["label"]
        label_dir.mkdir(parents=True, exist_ok=True)
        path = label_dir / f"web_{sample['id']}.npz"
        if path.exists():
            skipped += 1
            continue
        np.savez_compressed(
            path,
            sequence=sequence,
            label=np.asarray(sample["label"]),
            person=np.asarray(sample["participant_id"]),
            session=np.asarray(sample["session_id"]),
            recorded_at=np.asarray(sample["created_at"]),
            feature_names=np.asarray(sample.get("feature_names") or FEATURE_NAMES),
        )
        saved += 1

    labels = sorted(path.name for path in args.data_dir.iterdir() if path.is_dir())
    (args.data_dir / "labels.json").write_text(
        json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"synced={saved} skipped={skipped}")


if __name__ == "__main__":
    main()
