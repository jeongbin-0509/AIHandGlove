"""Dataset loading and train/validation splitting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from torch.utils.data import Dataset


def discover_samples(data_dir: Path) -> list[Path]:
    return sorted(data_dir.glob("*/*.npz"))


def load_label_map(data_dir: Path) -> dict[str, int]:
    path = data_dir / "labels.json"
    if path.exists():
        labels = json.loads(path.read_text(encoding="utf-8"))
    else:
        labels = sorted({p.parent.name for p in discover_samples(data_dir)})
    if not labels:
        raise ValueError(f"no labels found under {data_dir}")
    return {label: index for index, label in enumerate(labels)}


def split_by_session(
    paths: Sequence[Path], validation_ratio: float, seed: int
) -> tuple[list[Path], list[Path]]:
    """Keep recordings from the same session in only one split."""
    if not 0.0 < validation_ratio < 1.0:
        raise ValueError("validation_ratio must be between 0 and 1")
    rng = np.random.default_rng(seed)
    train: list[Path] = []
    validation: list[Path] = []
    labels = sorted({path.parent.name for path in paths})
    for label in labels:
        label_paths = [p for p in paths if p.parent.name == label]
        sessions: dict[str, list[Path]] = {}
        for path in label_paths:
            with np.load(path, allow_pickle=False) as sample:
                session = str(sample["session"].item()) if "session" in sample else path.stem
            sessions.setdefault(session, []).append(path)
        keys = list(sessions)
        rng.shuffle(keys)
        if len(keys) == 1:
            # A one-session dataset cannot be leakage-free; reserve individual clips.
            shuffled = list(label_paths)
            rng.shuffle(shuffled)
            n_val = max(1, int(round(len(shuffled) * validation_ratio)))
            validation.extend(shuffled[:n_val])
            train.extend(shuffled[n_val:])
        else:
            n_val = max(1, int(round(len(keys) * validation_ratio)))
            val_sessions = set(keys[:n_val])
            for session, session_paths in sessions.items():
                (validation if session in val_sessions else train).extend(session_paths)
    if not train or not validation:
        raise ValueError("not enough samples to create train/validation splits")
    return train, validation


def split_random_stratified(
    paths: Sequence[Path], validation_ratio: float, seed: int
) -> tuple[list[Path], list[Path]]:
    """Stratified clip split for a quick same-user demonstration model."""
    if not 0.0 < validation_ratio < 1.0:
        raise ValueError("validation_ratio must be between 0 and 1")
    rng = np.random.default_rng(seed)
    train: list[Path] = []
    validation: list[Path] = []
    for label in sorted({path.parent.name for path in paths}):
        label_paths = [path for path in paths if path.parent.name == label]
        rng.shuffle(label_paths)
        n_val = max(1, int(round(len(label_paths) * validation_ratio)))
        validation.extend(label_paths[:n_val])
        train.extend(label_paths[n_val:])
    if not train or not validation:
        raise ValueError("not enough samples to create train/validation splits")
    return train, validation


class SignDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    def __init__(
        self,
        paths: Sequence[Path],
        label_to_index: dict[str, int],
        mean: np.ndarray | None = None,
        std: np.ndarray | None = None,
        augment: bool = False,
    ) -> None:
        self.paths = list(paths)
        self.label_to_index = label_to_index
        self.mean = mean
        self.std = std
        self.augment = augment

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        path = self.paths[index]
        with np.load(path, allow_pickle=False) as sample:
            sequence = sample["sequence"].astype(np.float32)
        if self.mean is not None and self.std is not None:
            sequence = (sequence - self.mean) / self.std
        if self.augment:
            # Apply noise after normalization because the channels use
            # different physical units and value ranges.
            sequence = sequence + np.random.normal(0.0, 0.01, sequence.shape).astype(np.float32)
        label = self.label_to_index[path.parent.name]
        return torch.from_numpy(sequence), torch.tensor(label, dtype=torch.long)


def compute_normalization(paths: Sequence[Path]) -> tuple[np.ndarray, np.ndarray]:
    sequences = []
    for path in paths:
        with np.load(path, allow_pickle=False) as sample:
            sequences.append(sample["sequence"].astype(np.float32))
    merged = np.concatenate(sequences, axis=0)
    mean = merged.mean(axis=0, keepdims=True)
    std = merged.std(axis=0, keepdims=True)
    return mean.astype(np.float32), np.maximum(std, 1e-6).astype(np.float32)
