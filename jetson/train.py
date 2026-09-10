"""Train the Transformer classifier from collected NPZ clips."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from config import DATA_DIR, DEFAULT_MODEL_PATH, NUM_FEATURES, SEQUENCE_LENGTH
from dataset import (
    SignDataset,
    compute_normalization,
    discover_samples,
    load_label_map,
    split_by_session,
)
from model import SignTransformer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train sign Transformer")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    return parser.parse_args()


def choose_device(value: str) -> torch.device:
    if value == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if value == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    if value == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS was requested but is unavailable")
    return torch.device(value)


def evaluate(model: nn.Module, loader: DataLoader, loss_fn: nn.Module, device: torch.device) -> tuple[float, float]:
    model.eval()
    total_loss = correct = total = 0
    with torch.inference_mode():
        for inputs, targets in loader:
            inputs, targets = inputs.to(device), targets.to(device)
            logits = model(inputs)
            total_loss += loss_fn(logits, targets).item() * targets.size(0)
            correct += (logits.argmax(dim=1) == targets).sum().item()
            total += targets.size(0)
    return total_loss / total, correct / total


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = choose_device(args.device)
    print(f"training device: {device}")

    paths = discover_samples(args.data_dir)
    label_map = load_label_map(args.data_dir)
    train_paths, val_paths = split_by_session(paths, args.validation_ratio, args.seed)
    mean, std = compute_normalization(train_paths)
    train_set = SignDataset(train_paths, label_map, mean, std, augment=True)
    val_set = SignDataset(val_paths, label_map, mean, std)
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=args.batch_size)

    model = SignTransformer(NUM_FEATURES, len(label_map)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    best_accuracy = -1.0
    args.output.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = seen = 0
        for inputs, targets in train_loader:
            inputs, targets = inputs.to(device), targets.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(inputs), targets)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            running_loss += loss.item() * targets.size(0)
            seen += targets.size(0)
        val_loss, val_accuracy = evaluate(model, val_loader, loss_fn, device)
        print(
            f"epoch={epoch:03d} train_loss={running_loss / seen:.4f} "
            f"val_loss={val_loss:.4f} val_accuracy={val_accuracy:.3f}"
        )
        if val_accuracy > best_accuracy:
            best_accuracy = val_accuracy
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "model_config": model.model_config,
                    "labels": [label for label, _ in sorted(label_map.items(), key=lambda item: item[1])],
                    "mean": torch.from_numpy(mean),
                    "std": torch.from_numpy(std),
                    "sequence_length": SEQUENCE_LENGTH,
                    "best_validation_accuracy": best_accuracy,
                },
                args.output,
            )
    print(f"best model saved to {args.output} (accuracy={best_accuracy:.3f})")


if __name__ == "__main__":
    main()
