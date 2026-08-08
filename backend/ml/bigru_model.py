"""
BiGRU Bot Detector Model
Bidirectional GRU neural network for temporal analysis of mouse trajectories.
Identifies human motor control patterns vs bot linear movements.
"""

import torch
import torch.nn as nn


class BiGRUBotDetector(nn.Module):
    """
    Bidirectional GRU model for sequential bot detection.

    Architecture:
        Input(batch, seq_len, 6) → BiGRU×2 → Dropout → Dense → Sigmoid

    Input features per timestep:
        [x_norm, y_norm, t_norm, velocity_norm, acceleration_norm, jerk_norm]

    Output: Scalar probability (0.0 = human, 1.0 = bot)
    """

    def __init__(
        self,
        input_size: int = 6,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.3,
    ):
        super().__init__()

        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # Bidirectional GRU stack
        self.bigru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        # Dropout for regularization
        self.dropout = nn.Dropout(dropout)

        # Dense layers: BiGRU output is 2*hidden_size (forward + backward)
        self.fc1 = nn.Linear(hidden_size * 2, 64)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(64, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: Tensor of shape (batch, seq_len, input_size)

        Returns:
            Tensor of shape (batch, 1) with bot probability
        """
        # BiGRU: output shape (batch, seq_len, 2*hidden_size)
        gru_out, _ = self.bigru(x)

        # Take the last timestep output (captures full sequence context)
        last_output = gru_out[:, -1, :]  # (batch, 2*hidden_size)

        # Classification head
        out = self.dropout(last_output)
        out = self.fc1(out)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        out = self.sigmoid(out)

        return out


def create_model(**kwargs) -> BiGRUBotDetector:
    """Factory function to create a BiGRU model with default or custom params."""
    return BiGRUBotDetector(**kwargs)
