"""Compact Transformer encoder suitable for Jetson Nano inference."""

from __future__ import annotations

import math

import torch
from torch import nn


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_length: int = 512) -> None:
        super().__init__()
        positions = torch.arange(max_length).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2) * (-math.log(10_000.0) / d_model)
        )
        encoding = torch.zeros(1, max_length, d_model)
        encoding[0, :, 0::2] = torch.sin(positions * div_term)
        encoding[0, :, 1::2] = torch.cos(positions * div_term)
        self.register_buffer("encoding", encoding, persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.encoding[:, : x.size(1)]


class SignTransformer(nn.Module):
    def __init__(
        self,
        num_features: int,
        num_classes: int,
        d_model: int = 64,
        num_heads: int = 4,
        num_layers: int = 2,
        feedforward_dim: int = 128,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.model_config = {
            "num_features": num_features,
            "num_classes": num_classes,
            "d_model": d_model,
            "num_heads": num_heads,
            "num_layers": num_layers,
            "feedforward_dim": feedforward_dim,
            "dropout": dropout,
        }
        self.input_projection = nn.Linear(num_features, d_model)
        self.position = PositionalEncoding(d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=num_heads,
            dim_feedforward=feedforward_dim,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.norm = nn.LayerNorm(d_model)
        self.classifier = nn.Linear(d_model, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.input_projection(x)
        x = self.position(x)
        x = self.encoder(x)
        x = self.norm(x.mean(dim=1))
        return self.classifier(x)
