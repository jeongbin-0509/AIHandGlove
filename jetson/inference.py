"""Model checkpoint loading and single-window prediction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from model import SignTransformer


class SignPredictor:
    def __init__(self, checkpoint_path: Path, device: str = "auto") -> None:
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = torch.device(device)
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.labels: list[str] = checkpoint["labels"]
        self.mean = checkpoint["mean"].to(self.device)
        self.std = checkpoint["std"].to(self.device)
        self.sequence_length = int(checkpoint["sequence_length"])
        self.model = SignTransformer(**checkpoint["model_config"]).to(self.device)
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()

    def predict(self, sequence: np.ndarray) -> tuple[str, float, np.ndarray]:
        sequence = np.asarray(sequence, dtype=np.float32)
        expected = (self.sequence_length, self.mean.shape[-1])
        if sequence.shape != expected:
            raise ValueError(f"expected sequence shape {expected}, got {sequence.shape}")
        inputs = torch.from_numpy(sequence).unsqueeze(0).to(self.device)
        inputs = (inputs - self.mean) / self.std
        with torch.inference_mode():
            probabilities = self.model(inputs).softmax(dim=1)[0]
        confidence, index = probabilities.max(dim=0)
        return (
            self.labels[index.item()],
            confidence.item(),
            probabilities.cpu().numpy(),
        )
